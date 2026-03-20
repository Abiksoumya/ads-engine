"""
AdEngineAI — Orchestrator Agent
==================================
Framework: LangGraph (master state machine)

Wires all agents into a single pipeline:
    researcher → director → production → qa → publisher

Current state (Week 2):
    researcher  ✅ fully implemented
    director    ✅ fully implemented
    production  🔲 stub — Week 3
    qa          🔲 stub — Week 3
    publisher   🔲 stub — Week 4

Usage:
    orchestrator = Orchestrator()
    result = await orchestrator.run(
        product_url="https://example.com/product",
        brand_tone="bold and direct",
        brand_audience="fitness enthusiasts 25-35",
        publish_platforms=[],   # empty = download only
    )
    # result.scripts → list[Script] (5 hooks)
    # result.status  → "scripts_ready" | "complete" | "failed"
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict, Callable, Awaitable

from researcher.agent import ResearcherAgent, ResearchResult
from director.agent import DirectorAgent, Script

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline state — passed between every node in the LangGraph graph
# ---------------------------------------------------------------------------

class PipelineState(TypedDict):
    # Inputs
    product_url: str
    brand_tone: str
    brand_audience: str
    publish_platforms: list[str]   # ["meta", "instagram", "tiktok", "linkedin"]
    download_only: bool
    ugc_mode: bool

    # Filled by each agent
    research: Optional[ResearchResult]
    scripts: list[Script]
    videos: list[dict]             # filled by Production Crew (Week 3)
    qa_passed: list[str]           # video ids that passed QA (Week 3)
    publish_results: list[dict]    # filled by Publisher (Week 4)

    # Pipeline control
    job_id: str
    status: str                    # current pipeline stage
    errors: list[str]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Pipeline result — what callers get back
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    job_id: str
    status: str                          # "scripts_ready"|"videos_ready"|"published"|"failed"
    research: Optional[ResearchResult]
    scripts: list[Script] = field(default_factory=list)
    videos: list[dict] = field(default_factory=list)
    publish_results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        return len(self.scripts) == 5

    @property
    def best_script(self) -> Optional[Script]:
        """Returns the highest-scored script."""
        if not self.scripts:
            return None
        return max(self.scripts, key=lambda s: s.hook_score.score)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """
    Master pipeline — runs all agents in sequence.

    Progress callback: async fn(job_id, percent, message)
    Used to push WebSocket updates to the user in real time.
    When building APIs (later), pass the WebSocket notifier here.
    For now, defaults to logging only.
    """

    def __init__(
        self,
        progress_callback: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
        researcher: Optional[ResearcherAgent] = None,
        director: Optional[DirectorAgent] = None,
    ):
        self.researcher = researcher or ResearcherAgent()
        self.director = director or DirectorAgent()
        self.progress_callback = progress_callback or self._log_progress
        self._graph = self._build_graph()

    async def run(
        self,
        product_url: str,
        job_id: str = "local",
        brand_tone: str = "",
        brand_audience: str = "",
        publish_platforms: Optional[list[str]] = None,
        download_only: bool = True,
        ugc_mode: bool = False,
    ) -> PipelineResult:
        """
        Runs the full pipeline from URL to scripts (and later to videos).
        Always returns a PipelineResult — never raises.
        """
        logger.info(f"Orchestrator starting — job: {job_id} | url: {product_url}")

        initial: PipelineState = {
            "product_url": product_url,
            "brand_tone": brand_tone,
            "brand_audience": brand_audience,
            "publish_platforms": publish_platforms or [],
            "download_only": download_only,
            "ugc_mode": ugc_mode,
            "research": None,
            "scripts": [],
            "videos": [],
            "qa_passed": [],
            "publish_results": [],
            "job_id": job_id,
            "status": "starting",
            "errors": [],
            "warnings": [],
        }

        final = await self._graph.ainvoke(initial)

        return PipelineResult(
            job_id=final["job_id"],
            status=final["status"],
            research=final.get("research"),
            scripts=final.get("scripts", []),
            videos=final.get("videos", []),
            publish_results=final.get("publish_results", []),
            errors=final.get("errors", []),
            warnings=final.get("warnings", []),
        )

    # ------------------------------------------------------------------
    # Node 1 — Research
    # ------------------------------------------------------------------

    async def _node_research(self, state: PipelineState) -> PipelineState:
        await self.progress_callback(state["job_id"], 5, "Researching your product...")
        logger.info(f"Pipeline node: research | job: {state['job_id']}")

        try:
            research = await self.researcher.run(
                product_url=state["product_url"],
                brand_tone=state["brand_tone"],
                brand_audience=state["brand_audience"],
            )

            await self.progress_callback(
                state["job_id"], 25,
                f"Research complete — {len(research.pain_points)} insights found "
                f"(confidence: {research.confidence_score:.0%})"
            )

            return {
                **state,
                "research": research,
                "status": "researched",
                "warnings": state["warnings"] + research.scrape_warnings,
            }

        except Exception as e:
            logger.error(f"Research node failed: {e}")
            return {
                **state,
                "status": "failed",
                "errors": state["errors"] + [f"Research failed: {e}"],
            }

    # ------------------------------------------------------------------
    # Node 2 — Director
    # ------------------------------------------------------------------

    async def _node_director(self, state: PipelineState) -> PipelineState:
        await self.progress_callback(state["job_id"], 30, "Writing 5 hook scripts...")
        logger.info(f"Pipeline node: director | job: {state['job_id']}")

        try:
            research = state.get("research")
            if not research:
                raise ValueError("No research result available for Director")

            scripts = await self.director.run(
                research=research,
                brand_tone=state["brand_tone"],
                brand_audience=state["brand_audience"],
            )

            await self.progress_callback(
                state["job_id"], 50,
                f"Scripts ready — best hook: "
                f"'{max(scripts, key=lambda s: s.hook_score.score).hook_line}' "
                f"({max(scripts, key=lambda s: s.hook_score.score).hook_score.score}/100)"
            )

            return {
                **state,
                "scripts": scripts,
                "status": "scripts_ready",
            }

        except Exception as e:
            logger.error(f"Director node failed: {e}")
            return {
                **state,
                "status": "failed",
                "errors": state["errors"] + [f"Director failed: {e}"],
            }

    # ------------------------------------------------------------------
    # Node 3 — Production Crew (stub — Week 3)
    # ------------------------------------------------------------------

    async def _node_production(self, state: PipelineState) -> PipelineState:
        await self.progress_callback(state["job_id"], 55, "Rendering videos...")
        logger.info(f"Pipeline node: production (stub) | job: {state['job_id']}")

        # Week 3: CrewAI parallel rendering with HeyGen + ElevenLabs
        # For now: returns scripts_ready status so pipeline can be tested end-to-end
        return {
            **state,
            "status": "scripts_ready",   # will become "videos_ready" in Week 3
        }

    # ------------------------------------------------------------------
    # Node 4 — QA Agent (stub — Week 3)
    # ------------------------------------------------------------------

    async def _node_qa(self, state: PipelineState) -> PipelineState:
        await self.progress_callback(state["job_id"], 90, "Quality checking videos...")
        logger.info(f"Pipeline node: qa | job: {state['job_id']}")
        try:
            from qa.agent import QAAgent
            from production.crew import RenderResult

            agent = QAAgent()

            # confidence_score — safe access
            research = state.get("research")
            confidence = research.confidence_score if research is not None else 1.0

            # videos — ensure correct type
            raw_videos = state.get("videos", [])
            render_results: list[RenderResult] = [
                v for v in raw_videos if isinstance(v, RenderResult)
            ]

            qa_results = await agent.review(render_results, confidence)
            publishable = sum(1 for r in qa_results if r.is_publishable)

            await self.progress_callback(
                state["job_id"], 92,
                f"QA complete — {publishable}/{len(qa_results)} publishable"
            )
            return {**state, "status": "scripts_ready"}

        except Exception as e:
            logger.error(f"QA node failed: {e}")
            return {
                **state,
                "warnings": state["warnings"] + [f"QA failed: {e}"],
            }

    # ------------------------------------------------------------------
    # Node 5 — Publisher (stub — Week 4)
    # ------------------------------------------------------------------

    async def _node_publisher(self, state: PipelineState) -> PipelineState:
        await self.progress_callback(state["job_id"], 95, "Publishing to platforms...")
        logger.info(f"Pipeline node: publisher (stub) | job: {state['job_id']}")

        # Week 4: AutoGen publisher posts to Meta, TikTok, LinkedIn
        return {**state, "status": "published"}

    # ------------------------------------------------------------------
    # Routing — after QA, decide publish or done
    # ------------------------------------------------------------------

    def _route_after_qa(self, state: PipelineState) -> str:
        if state.get("download_only"):
            return "done"
        if state.get("publish_platforms"):
            return "publish"
        return "done"

    def _route_after_research(self, state: PipelineState) -> str:
        """Skip remaining nodes if research failed."""
        if state.get("status") == "failed":
            return "failed"
        return "continue"

    # ------------------------------------------------------------------
    # LangGraph graph definition
    # ------------------------------------------------------------------

    def _build_graph(self) -> Any:
        try:
            from langgraph.graph import StateGraph, END

            graph = StateGraph(PipelineState)

            graph.add_node("run_research",   self._node_research)
            graph.add_node("run_director",   self._node_director)
            graph.add_node("run_production", self._node_production)
            graph.add_node("run_qa",         self._node_qa)
            graph.add_node("run_publisher",  self._node_publisher)

            graph.set_entry_point("run_research")

            graph.add_conditional_edges(
                "run_research",
                self._route_after_research,
                {
                    "continue": "run_director",
                    "failed":   END,
                }
            )

            graph.add_edge("run_director",   "run_production")
            graph.add_edge("run_production", "run_qa")

            graph.add_conditional_edges(
                "run_qa",
                self._route_after_qa,
                {
                    "publish": "run_publisher",
                    "done":    END,
                }
            )

            graph.add_edge("run_publisher", END)

            compiled = graph.compile()
            logger.info("LangGraph compiled successfully")
            return compiled

        except Exception as e:
            logger.warning(f"LangGraph failed ({e}) — using sequential fallback")
            return _SequentialFallback(self)

    # ------------------------------------------------------------------
    # Default progress callback — logs instead of WebSocket
    # ------------------------------------------------------------------

    @staticmethod
    async def _log_progress(job_id: str, percent: int, message: str) -> None:
        logger.info(f"[{job_id}] {percent:3d}% — {message}")


# ---------------------------------------------------------------------------
# Sequential fallback — when langgraph is not installed
# ---------------------------------------------------------------------------

class _SequentialFallback:

    def __init__(self, orchestrator: Orchestrator):
        self.o = orchestrator

    async def ainvoke(self, state: PipelineState) -> PipelineState:
        state = await self.o._node_research(state)
        if state["status"] == "failed":
            return state
        state = await self.o._node_director(state)
        state = await self.o._node_production(state)
        state = await self.o._node_qa(state)
        if not state.get("download_only") and state.get("publish_platforms"):
            state = await self.o._node_publisher(state)
        return state