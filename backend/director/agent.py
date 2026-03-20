"""
AdEngineAI — Director Agent
==============================
Framework: Claude API direct (no LangGraph needed here)

Why no framework?
    This is a single structured-output LLM call.
    No state machine, no tool calls, no multi-step loop needed.
    Adding LangGraph here would be pure overhead.

What it does:
    Takes ResearchResult → writes 5 complete hook scripts → returns list[Script]

Each Script contains:
    - Full 60-second voiceover script
    - Hook Score Explainer (why this hook converts)
    - Per-platform captions (Instagram, TikTok, LinkedIn)
    - Meta/LinkedIn ad headline + description
    - Hashtag set

Used by: orchestrator/graph.py
Input:   ResearchResult + optional brand context
Output:  list[Script] (always 5 scripts)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from config.llm import get_llm_config
from config.llm_client import complete_json
from researcher.agent import ResearchResult
from director.prompts import DIRECTOR_SYSTEM, build_director_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class HookScore:
    """
    Explains WHY a hook should convert — shown alongside each script card in the UI.
    Helps users understand the strategy, not just the output.
    """
    score: int                  # 0-100
    primary_trigger: str        # e.g. "loss aversion", "curiosity gap", "social proof"
    reasoning: str              # 1-2 sentences in plain English
    best_platform: str          # "instagram" | "tiktok" | "linkedin" | "facebook"


@dataclass
class Script:
    hook_type: str              # "problem"|"secret"|"social_proof"|"visual_first"|"emotional"
    hook_line: str              # opening 3-5 words — the scroll-stopper
    script: str                 # full 60-second voiceover
    hook_score: HookScore

    # Ad copy
    ad_headline: str            # 40 chars — Meta/LinkedIn
    ad_description: str         # 125 chars — Meta/LinkedIn

    # Per-platform captions
    caption_instagram: str
    caption_tiktok: str
    caption_linkedin: str

    hashtags: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.script.split())

    @property
    def is_valid(self) -> bool:
        """Basic validation — script should be close to 60 seconds (150-160 words)."""
        return (
            bool(self.hook_line)
            and bool(self.script)
            and 120 <= self.word_count <= 200  # some tolerance either side
        )


# ---------------------------------------------------------------------------
# Director Agent
# ---------------------------------------------------------------------------

class DirectorAgent:
    """
    Writes 5 hook scripts from a ResearchResult.

    Usage:
        agent = DirectorAgent()
        scripts = await agent.run(
            research=research_result,
            brand_tone="bold and direct",
            brand_audience="fitness enthusiasts 25-35",
        )
    """

    # Expected hook types — always in this order
    HOOK_TYPES = ["problem", "secret", "social_proof", "visual_first", "emotional"]

    def __init__(self):
        self.llm_cfg = get_llm_config("director")

    async def run(
        self,
        research: ResearchResult,
        brand_tone: str = "",
        brand_audience: str = "",
    ) -> list[Script]:
        """
        Generates 5 hook scripts from research intelligence.
        Always returns exactly 5 scripts — uses fallbacks if LLM output is malformed.
        Never raises.
        """
        logger.info(
            f"Director starting — product: {research.product_name} "
            f"| model: {self.llm_cfg.model}"
        )

        try:
            user_prompt = build_director_prompt(
                product_name=research.product_name,
                product_category=research.product_category,
                pain_points=research.pain_points,
                selling_points=research.selling_points,
                social_proof=research.social_proof,
                target_audience=research.target_audience,
                key_differentiator=research.key_differentiator,
                price_point=research.price_point,
                brand_tone=brand_tone,
                brand_audience=brand_audience,
                competitor_hooks=research.competitor_hooks,
            )

            logger.info(f"Calling LLM: {self.llm_cfg.model}")
            raw = await complete_json(self.llm_cfg, DIRECTOR_SYSTEM, user_prompt)
            if not isinstance(raw, list):
                raise ValueError(f"LLM returned {type(raw).__name__}, expected list")


            scripts = self._parse_scripts(raw)
            scripts = self._ensure_five(scripts, research)

            valid = sum(1 for s in scripts if s.is_valid)
            logger.info(
                f"Director complete — {len(scripts)} scripts generated "
                f"({valid} valid, avg words: "
                f"{sum(s.word_count for s in scripts) // len(scripts)})"
            )

            return scripts

        except Exception as e:
            logger.error(f"Director failed: {e}")
            return self._fallback_scripts(research)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_scripts(self, raw: list) -> list[Script]:
        """Parses raw LLM JSON output into Script dataclasses."""
        scripts: list[Script] = []

        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                script = self._parse_single(item)
                scripts.append(script)
            except Exception as e:
                logger.warning(f"Skipping malformed script item: {e}")
                continue

        return scripts

    def _parse_single(self, item: dict) -> Script:
        """Parses a single script dict into a Script dataclass."""
        hook_score_raw = item.get("hook_score", {})

        hook_score = HookScore(
            score=int(hook_score_raw.get("score", 50)),
            primary_trigger=hook_score_raw.get("primary_trigger", "unknown"),
            reasoning=hook_score_raw.get("reasoning", ""),
            best_platform=hook_score_raw.get("best_platform", "instagram"),
        )

        return Script(
            hook_type=item.get("hook_type", "problem"),
            hook_line=item.get("hook_line", ""),
            script=item.get("script", ""),
            hook_score=hook_score,
            ad_headline=item.get("ad_headline", "")[:40],
            ad_description=item.get("ad_description", "")[:125],
            caption_instagram=item.get("caption_instagram", ""),
            caption_tiktok=item.get("caption_tiktok", ""),
            caption_linkedin=item.get("caption_linkedin", ""),
            hashtags=item.get("hashtags", [])[:20],
        )

    # ------------------------------------------------------------------
    # Ensure exactly 5 scripts — one per hook type
    # ------------------------------------------------------------------

    def _ensure_five(
        self, scripts: list[Script], research: ResearchResult
    ) -> list[Script]:
        """
        Guarantees exactly 5 scripts — one per hook type.
        If LLM returned fewer, fills gaps with fallbacks.
        If LLM returned more, keeps the best one per hook type.
        """
        by_type: dict[str, Script] = {}

        for script in scripts:
            hook = script.hook_type
            if hook not in by_type:
                by_type[hook] = script
            else:
                # Keep whichever has the higher hook score
                if script.hook_score.score > by_type[hook].hook_score.score:
                    by_type[hook] = script

        # Fill missing hook types with fallbacks
        for hook_type in self.HOOK_TYPES:
            if hook_type not in by_type:
                logger.warning(f"Missing hook type '{hook_type}' — using fallback")
                by_type[hook_type] = self._fallback_single(hook_type, research)

        # Return in correct order
        return [by_type[h] for h in self.HOOK_TYPES]

    # ------------------------------------------------------------------
    # Fallbacks — used when LLM fails or returns incomplete output
    # ------------------------------------------------------------------

    def _fallback_scripts(self, research: ResearchResult) -> list[Script]:
        """Returns 5 minimal fallback scripts when the LLM call fails entirely."""
        logger.warning("Using fallback scripts — LLM call failed")
        return [self._fallback_single(h, research) for h in self.HOOK_TYPES]

    def _fallback_single(self, hook_type: str, research: ResearchResult) -> Script:
        """Minimal script for a single hook type."""
        name = research.product_name
        pain = research.pain_points[0] if research.pain_points else "your problem"
        benefit = research.selling_points[0] if research.selling_points else "real results"

        hook_lines = {
            "problem":      f"Still dealing with {pain[:30]}?",
            "secret":       f"The real reason {pain[:25]}...",
            "social_proof": f"Thousands already switched to {name}.",
            "visual_first": f"Watch what {name} does in 3 weeks.",
            "emotional":    f"You deserve better than {pain[:25]}.",
        }

        fallback_script = (
            f"{hook_lines.get(hook_type, 'This changes everything.')} "
            f"If you've been struggling, you're not alone. "
            f"Most people don't realise that {pain}. "
            f"That's exactly why {name} was created. "
            f"It delivers {benefit}. "
            f"The difference is real — and it shows within weeks. "
            f"Thousands of people have already made the switch. "
            f"Don't keep settling for less. "
            f"Try {name} today — link in bio."
        )

        return Script(
            hook_type=hook_type,
            hook_line=hook_lines.get(hook_type, "This changes everything."),
            script=fallback_script,
            hook_score=HookScore(
                score=50,
                primary_trigger="generic",
                reasoning="Fallback script — LLM generation failed. Regenerate for better results.",
                best_platform="instagram",
            ),
            ad_headline=f"Try {name[:30]} Today",
            ad_description=f"{benefit[:125]}",
            caption_instagram=f"Real results with {name}. Link in bio.",
            caption_tiktok=f"{name} — see the difference.",
            caption_linkedin=f"Discover how {name} delivers {benefit}.",
            hashtags=["#ad", "#sponsored", f"#{name.lower().replace(' ', '')}"],
        )