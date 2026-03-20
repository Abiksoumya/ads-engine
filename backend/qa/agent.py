"""
AdEngineAI — QA Agent
=======================
Framework: AutoGen (self-correcting review loop)

Why AutoGen here?
    QA is a generate → critique → fix loop.
    If a video fails QA, we need to flag it for re-render with a reason.
    AutoGen's iterative pattern handles this natively.

What it does:
    Takes list[RenderResult] → reviews each against QA rubric
    → returns list[QAResult] with pass/fail + issues per video

Used by: orchestrator/agent.py
Input:   list[RenderResult] from Production Crew
Output:  list[QAResult]
"""

from email.mime import audio
import logging
from dataclasses import dataclass, field
from typing import Optional

from config.llm import get_llm_config
from config.llm_client import complete_json
from production.crew import RenderResult
from qa.rubric import (
    QA_SYSTEM, RULES_BY_CODE, build_qa_prompt,
    QARule
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class QAResult:
    hook_type: str
    passed: bool
    issues: list[str] = field(default_factory=list)
    severity: str = "none"             # "none" | "warning" | "fatal"
    recommendation: str = ""
    rerender_required: bool = False

    @property
    def is_publishable(self) -> bool:
        """True if video can be published — passes or only has warnings."""
        return self.severity != "fatal"


# ---------------------------------------------------------------------------
# QA Agent
# ---------------------------------------------------------------------------

class QAAgent:
    """
    Reviews all 5 render results against the quality rubric.

    Usage:
        agent = QAAgent()
        results = await agent.review(render_results, confidence_score=0.85)
    """

    def __init__(self):
        self.llm_cfg = get_llm_config("qa")

    async def review(
        self,
        render_results: list[RenderResult],
        confidence_score: float = 1.0,
    ) -> list[QAResult]:
        """
        Reviews all render results.
        Returns QAResult for each — always same length as input.
        Never raises.
        """
        logger.info(
            f"QA Agent reviewing {len(render_results)} renders "
            f"| model: {self.llm_cfg.model}"
        )

        # Run rule-based checks first — fast, no LLM needed
        rule_results = [
            self._rule_based_check(r, confidence_score)
            for r in render_results
        ]

        # For any that passed rule checks, run LLM review for deeper analysis
        final_results: list[QAResult] = []
        for render, rule_result in zip(render_results, rule_results):
            if rule_result.severity == "fatal":
                # Already failed — no need for LLM review
                final_results.append(rule_result)
                logger.warning(
                    f"QA FATAL: {render.hook_type} — {rule_result.issues}"
                )
            else:
                # Run LLM review for deeper check
                llm_result = await self._llm_review(render, confidence_score)
                # Merge: keep fatal from either, combine issues
                merged = self._merge_results(rule_result, llm_result)
                final_results.append(merged)
                logger.info(
                    f"QA {'PASS' if merged.passed else 'WARN'}: "
                    f"{render.hook_type} — {merged.severity}"
                )

        passed = sum(1 for r in final_results if r.passed)
        publishable = sum(1 for r in final_results if r.is_publishable)
        logger.info(
            f"QA complete — {passed}/5 passed | {publishable}/5 publishable"
        )

        return final_results

    # ------------------------------------------------------------------
    # Rule-based checks — instant, no LLM
    # ------------------------------------------------------------------

    def _rule_based_check(
        self, render: RenderResult, confidence_score: float
    ) -> QAResult:
        """
        Fast rule-based QA — catches obvious failures instantly.
        No LLM call needed for these.
        """
        issues: list[str] = []
        severity = "none"
        rerender = False

        # Fatal checks
        if not render.audio:
            issues.append(RULES_BY_CODE["AUDIO_MISSING"].description)
            severity = "fatal"
            rerender = True

        elif render.audio.duration_secs < 1.0 and not render.audio.is_mock:
            issues.append(RULES_BY_CODE["DURATION_TOO_SHORT"].description)
            severity = "fatal"
            rerender = True

        if render.errors:
            issues.append(f"{RULES_BY_CODE['RENDER_FAILED'].description}: {render.errors[0]}")
            severity = "fatal"
            rerender = True

        if not render.video_9x16:
            issues.append(RULES_BY_CODE["VIDEO_EMPTY"].description)
            severity = "fatal"
            rerender = True

        # Warning checks — only if not already fatal
        if severity != "fatal":
            if render.audio and render.audio.is_mock:
                issues.append(RULES_BY_CODE["MOCK_VIDEO"].description)
                severity = "warning"

            if confidence_score < 0.5:
                issues.append(RULES_BY_CODE["LOW_CONFIDENCE"].description)
                severity = "warning" if severity == "none" else severity
            audio = render.audio
            audio_dur = audio.duration_secs if audio is not None else 0
            if audio is not None and audio_dur > 0 and not audio.is_mock:
                if audio_dur < 15 or audio_dur > 90:
                    issues.append(RULES_BY_CODE["DURATION_OFF"].description)
                    severity = "warning" if severity == "none" else severity

        passed = severity != "fatal"

        return QAResult(
            hook_type=render.hook_type,
            passed=passed,
            issues=issues,
            severity=severity,
            rerender_required=rerender,
            recommendation=(
                "Re-render required" if rerender
                else "Fix before publishing" if severity == "warning"
                else "Approved"
            ),
        )

    # ------------------------------------------------------------------
    # LLM review — deeper quality analysis
    # ------------------------------------------------------------------

    async def _llm_review(
        self, render: RenderResult, confidence_score: float
    ) -> QAResult:
        """
        LLM-based QA review for deeper analysis.
        Falls back to rule-based result if LLM fails.
        """
        try:
            audio = render.audio
            video = render.video_9x16

            prompt = build_qa_prompt(
                hook_type=render.hook_type,
                audio_available=audio is not None,
                audio_is_mock=audio.is_mock if audio else True,
                audio_duration=audio.duration_secs if audio else 0.0,
                video_available=video is not None,
                video_is_mock=video.is_mock if video else True,
                video_url=video.video_url if video else "",
                render_errors=render.errors,
                confidence_score=confidence_score,
            )

            result = await complete_json(self.llm_cfg, QA_SYSTEM, prompt)

            issues = result.get("issues", [])
            severity = result.get("severity", "none")
            passed = result.get("passed", True)
            recommendation = result.get("recommendation", "Approved")

            return QAResult(
                hook_type=render.hook_type,
                passed=passed,
                issues=issues,
                severity=severity,
                recommendation=recommendation,
                rerender_required=severity == "fatal",
            )

        except Exception as e:
            logger.warning(f"LLM QA review failed for {render.hook_type}: {e}")
            # Return a passing result — don't block the pipeline
            return QAResult(
                hook_type=render.hook_type,
                passed=True,
                issues=[f"LLM review skipped: {e}"],
                severity="warning",
                recommendation="LLM review unavailable — manual check recommended",
            )

    # ------------------------------------------------------------------
    # Merge rule-based + LLM results
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_results(rule: QAResult, llm: QAResult) -> QAResult:
        """
        Merges rule-based and LLM QA results.
        Fatal from either source = fatal overall.
        Issues are combined and deduplicated.
        """
        # Severity priority: fatal > warning > none
        severity_rank = {"fatal": 2, "warning": 1, "none": 0}
        final_severity = (
            rule.severity
            if severity_rank[rule.severity] >= severity_rank[llm.severity]
            else llm.severity
        )

        all_issues = list(dict.fromkeys(rule.issues + llm.issues))
        passed = final_severity != "fatal"
        rerender = rule.rerender_required or llm.rerender_required

        return QAResult(
            hook_type=rule.hook_type,
            passed=passed,
            issues=all_issues,
            severity=final_severity,
            recommendation=rule.recommendation if not passed else llm.recommendation,
            rerender_required=rerender,
        )