"""
AdEngineAI — Researcher Agent
================================
Framework: LangGraph (stateful, checkpointed pipeline)

Pipeline nodes:
    1. scrape      — fetch product page + reviews
    2. analyze     — extract sentiment from reviews
    3. synthesize  — Claude/Groq call → structured ResearchResult
    4. competitor  — Meta Ad Library snapshot (non-fatal if it fails)

Each node writes to ResearchState and passes it forward.
Any node can fail — the pipeline always reaches synthesize with whatever data it has.

Used by: orchestrator/graph.py
Input:   product_url, optional brand_dna dict
Output:  ResearchResult dataclass
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, TypedDict

from config.llm import get_llm_config
from config.llm_client import complete_json
from mcp_tools.scraper import ScraperTool, ScrapedProduct
from researcher.prompts import SYNTHESIS_SYSTEM, build_synthesis_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class ResearchResult:
    product_name: str
    product_url: str
    product_category: str
    pain_points: list[str]
    selling_points: list[str]
    social_proof: list[str]
    target_audience: str
    price_point: str
    key_differentiator: str
    confidence_score: float
    confidence_notes: str
    competitor_hooks: list[str] = field(default_factory=list)
    scrape_warnings: list[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        """True if we have enough data to generate scripts."""
        return bool(
            self.product_name
            and len(self.pain_points) >= 2
            and len(self.selling_points) >= 2
        )


# ---------------------------------------------------------------------------
# Internal pipeline state — only used inside this agent
# ---------------------------------------------------------------------------

class ResearchState(TypedDict):
    # Inputs
    product_url: str
    brand_tone: str
    brand_audience: str

    # Filled by each node
    scraped: Optional[ScrapedProduct]
    sentiment: dict                    # {pain_points, selling_points, social_proof}
    competitor_hooks: list[str]

    # Final output
    result: Optional[ResearchResult]

    # Error tracking — non-fatal, pipeline always continues
    warnings: list[str]


# ---------------------------------------------------------------------------
# Researcher Agent
# ---------------------------------------------------------------------------

class ResearcherAgent:
    """
    Runs the full research pipeline for a product URL.

    Usage:
        agent = ResearcherAgent()
        result = await agent.run(
            product_url="https://example.com/product",
            brand_tone="bold and direct",
            brand_audience="fitness enthusiasts 25-35",
        )
    """

    def __init__(self, scraper: Optional[ScraperTool] = None):
        self.scraper = scraper or ScraperTool()
        self.llm_cfg = get_llm_config("researcher")
        self._graph = self._build_graph()

    async def run(
        self,
        product_url: str,
        brand_tone: str = "",
        brand_audience: str = "",
    ) -> ResearchResult:
        """
        Runs the full pipeline. Always returns a ResearchResult.
        Never raises — errors are captured in result.scrape_warnings.
        """
        logger.info(f"Researcher starting: {product_url}")

        initial: ResearchState = {
            "product_url": product_url,
            "brand_tone": brand_tone,
            "brand_audience": brand_audience,
            "scraped": None,
            "sentiment": {},
            "competitor_hooks": [],
            "result": None,
            "warnings": [],
        }

        final = await self._graph.ainvoke(initial)

        result: Optional[ResearchResult] = final.get("result")
        if result is not None:
            logger.info(
                f"Research complete — confidence: {result.confidence_score:.2f} "
                f"| warnings: {len(final['warnings'])}"
            )
            return result

        # Should never reach here — synthesize always produces a result
        logger.error("Researcher pipeline produced no result — returning minimal fallback")
        return self._minimal_fallback(product_url, ["Pipeline produced no result"])

    # ------------------------------------------------------------------
    # Node 1 — Scrape
    # ------------------------------------------------------------------

    async def _node_scrape(self, state: ResearchState) -> ResearchState:
        logger.info("Node 1/4: scrape")
        try:
            scraped = await self.scraper.scrape(state["product_url"])
            warnings = list(state["warnings"])
            if scraped.error:
                warnings.append(f"Scrape warning: {scraped.error}")
            return {**state, "scraped": scraped, "warnings": warnings}
        except Exception as e:
            logger.error(f"Node scrape failed: {e}")
            return {
                **state,
                "scraped": ScrapedProduct(url=state["product_url"], error=str(e)),
                "warnings": state["warnings"] + [f"Scrape failed: {e}"],
            }

    # ------------------------------------------------------------------
    # Node 2 — Analyze sentiment from reviews
    # ------------------------------------------------------------------

    async def _node_analyze(self, state: ResearchState) -> ResearchState:
        logger.info("Node 2/4: analyze")
        try:
            scraped = state.get("scraped")
            reviews = scraped.reviews if scraped else []

            if not reviews:
                logger.warning("No reviews found — skipping sentiment analysis")
                return {**state, "sentiment": {}}

            sentiment = self._extract_sentiment(reviews)
            logger.info(
                f"Sentiment: {len(sentiment.get('pain_points', []))} pain points, "
                f"{len(sentiment.get('selling_points', []))} selling points"
            )
            return {**state, "sentiment": sentiment}

        except Exception as e:
            logger.error(f"Node analyze failed: {e}")
            return {
                **state,
                "sentiment": {},
                "warnings": state["warnings"] + [f"Sentiment analysis failed: {e}"],
            }

    # ------------------------------------------------------------------
    # Node 3 — Synthesize with LLM
    # ------------------------------------------------------------------

    async def _node_synthesize(self, state: ResearchState) -> ResearchState:
        logger.info("Node 3/4: synthesize")
        try:
            scraped: ScrapedProduct = state.get("scraped") or ScrapedProduct(
                url=state["product_url"]
            )

            user_prompt = build_synthesis_prompt(
                url=scraped.url,
                title=scraped.title,
                description=scraped.description,
                price=scraped.price,
                reviews=scraped.reviews,
                brand_tone=state.get("brand_tone", ""),
                brand_audience=state.get("brand_audience", ""),
            )

            logger.info(f"Calling LLM: {self.llm_cfg.model}")
            synthesis = await complete_json(self.llm_cfg, SYNTHESIS_SYSTEM, user_prompt)

            result = ResearchResult(
                product_name=synthesis.get("product_name", scraped.title),
                product_url=scraped.url,
                product_category=synthesis.get("product_category", ""),
                pain_points=synthesis.get("pain_points", []),
                selling_points=synthesis.get("selling_points", []),
                social_proof=synthesis.get("social_proof", []),
                target_audience=synthesis.get("target_audience", ""),
                price_point=synthesis.get("price_point", scraped.price),
                key_differentiator=synthesis.get("key_differentiator", ""),
                confidence_score=float(synthesis.get("confidence_score", 0.5)),
                confidence_notes=synthesis.get("confidence_notes", ""),
                competitor_hooks=state.get("competitor_hooks", []),
                scrape_warnings=state.get("warnings", []),
            )

            return {**state, "result": result}

        except Exception as e:
            logger.error(f"Node synthesize failed: {e}")
            fallback = self._minimal_fallback(
                state["product_url"],
                state["warnings"] + [f"Synthesis failed: {e}"],
            )
            return {**state, "result": fallback}

    # ------------------------------------------------------------------
    # Node 4 — Competitor snapshot (non-fatal)
    # ------------------------------------------------------------------

    async def _node_competitor(self, state: ResearchState) -> ResearchState:
        """
        MVP version — scrapes Meta Ad Library for competitor hooks.
        Fails silently: if this node errors, the pipeline still completes.
        Full competitor scanner comes in Tier 3.
        """
        logger.info("Node 4/4: competitor snapshot")
        try:
            scraped = state.get("scraped")
            if not scraped or not scraped.title:
                return state

            # Extract keywords from product title for ad library search
            keywords = self._extract_keywords(scraped.title)
            logger.info(f"Competitor search keywords: {keywords}")

            # Placeholder — actual Meta Ad Library scraping in Tier 3
            # The scraper.scrape() call and hook extraction goes here
            competitor_hooks: list[str] = []

            return {**state, "competitor_hooks": competitor_hooks}

        except Exception as e:
            logger.warning(f"Competitor snapshot failed (non-fatal): {e}")
            return {
                **state,
                "warnings": state["warnings"] + [f"Competitor snapshot skipped: {e}"],
            }

    # ------------------------------------------------------------------
    # LangGraph graph definition
    # ------------------------------------------------------------------

    def _build_graph(self):
        try:
            from langgraph.graph import StateGraph, END

            graph = StateGraph(ResearchState)

            graph.add_node("scrape",      self._node_scrape)
            graph.add_node("analyze",     self._node_analyze)
            graph.add_node("competitor",  self._node_competitor)
            graph.add_node("synthesize",  self._node_synthesize)

            graph.set_entry_point("scrape")
            graph.add_edge("scrape",     "analyze")
            graph.add_edge("analyze",    "competitor")
            graph.add_edge("competitor", "synthesize")
            graph.add_edge("synthesize", END)

            return graph.compile()

        except ImportError:
            logger.warning("langgraph not installed — using sequential fallback")
            return _SequentialFallback(self)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_sentiment(self, reviews: list[str]) -> dict:
        """
        Lightweight pre-processing on reviews before the LLM synthesis call.
        Separates positive and negative signals so the prompt is cleaner.
        """
        positive_words = {
            "love", "amazing", "perfect", "best", "great", "excellent",
            "works", "finally", "recommend", "worth", "changed", "incredible",
        }
        negative_words = {
            "but", "however", "wish", "problem", "disappointed", "expected",
            "unfortunately", "issue", "waste", "doesn't", "didn't", "poor",
        }

        pain_candidates: list[str] = []
        selling_candidates: list[str] = []
        social_proof: list[str] = []

        for review in reviews:
            lower = review.lower()
            pos = sum(1 for w in positive_words if w in lower)
            neg = sum(1 for w in negative_words if w in lower)

            sentences = re.split(r"[.!?]+", review)
            for s in sentences:
                s = s.strip()
                if len(s) < 20 or len(s) > 300:
                    continue
                if neg > pos:
                    pain_candidates.append(s)
                elif pos > neg:
                    selling_candidates.append(s)
                    # Short punchy positive lines make good social proof
                    if len(s) < 100:
                        social_proof.append(f'"{s}"')

        return {
            "pain_points": list(dict.fromkeys(pain_candidates))[:8],
            "selling_points": list(dict.fromkeys(selling_candidates))[:8],
            "social_proof": list(dict.fromkeys(social_proof))[:5],
        }

    @staticmethod
    def _extract_keywords(title: str) -> list[str]:
        stop_words = {
            "the", "a", "an", "and", "or", "for", "with",
            "in", "on", "at", "to", "of", "by", "from",
        }
        words = re.findall(r"\b[a-zA-Z]{3,}\b", title)
        return [w.lower() for w in words if w.lower() not in stop_words][:5]

    @staticmethod
    def _minimal_fallback(url: str, warnings: list[str]) -> ResearchResult:
        """Last-resort result when everything fails. Pipeline never crashes."""
        return ResearchResult(
            product_name=url,
            product_url=url,
            product_category="",
            pain_points=[],
            selling_points=[],
            social_proof=[],
            target_audience="",
            price_point="",
            key_differentiator="",
            confidence_score=0.0,
            confidence_notes="Research failed — all data missing",
            scrape_warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Sequential fallback — used when langgraph is not installed
# ---------------------------------------------------------------------------

class _SequentialFallback:
    """Runs nodes sequentially without LangGraph. Same logic, no checkpointing."""

    def __init__(self, agent: ResearcherAgent):
        self.agent = agent

    async def ainvoke(self, state: ResearchState) -> ResearchState:
        state = await self.agent._node_scrape(state)
        state = await self.agent._node_analyze(state)
        state = await self.agent._node_competitor(state)
        state = await self.agent._node_synthesize(state)
        return state