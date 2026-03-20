"""
AdEngineAI — Orchestrator Tests
==================================
Unit tests: mocked agents, no API keys needed.
Integration test: full pipeline — real Groq, real URL.

Run unit tests:
    pytest tests/test_orchestrator.py -v -k "not integration"

Run full pipeline integration test:
    pytest tests/test_orchestrator.py -v -m integration -s
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from researcher.agent import ResearchResult
from director.agent import Script, HookScore


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESEARCH = ResearchResult(
    product_name="SuperGlow Vitamin C Serum",
    product_url="https://example.com/superglow",
    product_category="skincare",
    pain_points=["Dark spots", "Greasy serums", "Expensive treatments"],
    selling_points=["Works in 3 weeks", "Lightweight", "Dermatologist tested"],
    social_proof=['"Amazing results!"'],
    target_audience="Women 28-45",
    price_point="$49.99",
    key_differentiator="Clinical grade vitamin C",
    confidence_score=0.85,
    confidence_notes="Good data",
)

SAMPLE_HOOK_SCORE = HookScore(
    score=87,
    primary_trigger="loss aversion",
    reasoning="Strong hook for this audience",
    best_platform="instagram",
)

def make_sample_scripts() -> list[Script]:
    hook_types = ["problem", "secret", "social_proof", "visual_first", "emotional"]
    return [
        Script(
            hook_type=h,
            hook_line=f"Hook for {h}",
            script=" ".join(["word"] * 150),
            hook_score=HookScore(
                score=80 + i * 2,
                primary_trigger="test",
                reasoning="test reasoning",
                best_platform="instagram",
            ),
            ad_headline=f"Headline {h[:20]}",
            ad_description="Supporting copy here",
            caption_instagram=f"Instagram caption for {h}",
            caption_tiktok=f"TikTok caption for {h}",
            caption_linkedin=f"LinkedIn caption for {h}",
            hashtags=["#skincare", "#test"],
        )
        for i, h in enumerate(hook_types)
    ]


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestOrchestrator:

    def _make_orchestrator(self, research=None, scripts=None):
        """Creates Orchestrator with mocked agents."""
        from orchestrator.agent import Orchestrator
        from researcher.agent import ResearcherAgent
        from director.agent import DirectorAgent

        mock_researcher = MagicMock(spec=ResearcherAgent)
        mock_researcher.run = AsyncMock(return_value=research or SAMPLE_RESEARCH)

        mock_director = MagicMock(spec=DirectorAgent)
        mock_director.run = AsyncMock(return_value=scripts or make_sample_scripts())

        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test"}):
            return Orchestrator(
                researcher=mock_researcher,
                director=mock_director,
            )

    @pytest.mark.asyncio
    async def test_returns_pipeline_result(self):
        from orchestrator.agent import PipelineResult
        orchestrator = self._make_orchestrator()
        result = await orchestrator.run("https://example.com/product")
        assert isinstance(result, PipelineResult)

    @pytest.mark.asyncio
    async def test_result_has_five_scripts(self):
        orchestrator = self._make_orchestrator()
        result = await orchestrator.run("https://example.com/product")
        assert len(result.scripts) == 5

    @pytest.mark.asyncio
    async def test_result_has_research(self):
        orchestrator = self._make_orchestrator()
        result = await orchestrator.run("https://example.com/product")
        assert result.research is not None
        assert result.research.product_name == "SuperGlow Vitamin C Serum"

    @pytest.mark.asyncio
    async def test_status_is_scripts_ready(self):
        orchestrator = self._make_orchestrator()
        result = await orchestrator.run("https://example.com/product")
        assert result.status == "scripts_ready"

    @pytest.mark.asyncio
    async def test_is_usable_true_with_five_scripts(self):
        orchestrator = self._make_orchestrator()
        result = await orchestrator.run("https://example.com/product")
        assert result.is_usable is True

    @pytest.mark.asyncio
    async def test_best_script_returns_highest_score(self):
        orchestrator = self._make_orchestrator()
        result = await orchestrator.run("https://example.com/product")
        best = result.best_script
        assert best is not None
        assert best.hook_score.score == max(
            s.hook_score.score for s in result.scripts
        )

    @pytest.mark.asyncio
    async def test_progress_callback_is_called(self):
        progress_calls: list[tuple] = []

        async def capture_progress(job_id, percent, message):
            progress_calls.append((job_id, percent, message))

        from orchestrator.agent import Orchestrator
        from researcher.agent import ResearcherAgent
        from director.agent import DirectorAgent

        mock_researcher = MagicMock(spec=ResearcherAgent)
        mock_researcher.run = AsyncMock(return_value=SAMPLE_RESEARCH)
        mock_director = MagicMock(spec=DirectorAgent)
        mock_director.run = AsyncMock(return_value=make_sample_scripts())

        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test"}):
            orchestrator = Orchestrator(
                progress_callback=capture_progress,
                researcher=mock_researcher,
                director=mock_director,
            )

        await orchestrator.run("https://example.com/product", job_id="test-job")

        assert len(progress_calls) > 0
        job_ids = [c[0] for c in progress_calls]
        assert all(j == "test-job" for j in job_ids)
        percents = [c[1] for c in progress_calls]
        assert percents == sorted(percents)   # progress only goes forward

    @pytest.mark.asyncio
    async def test_pipeline_fails_fast_when_research_fails(self):
        from orchestrator.agent import Orchestrator
        from researcher.agent import ResearcherAgent
        from director.agent import DirectorAgent

        mock_researcher = MagicMock(spec=ResearcherAgent)
        mock_researcher.run = AsyncMock(side_effect=Exception("Scrape timeout"))

        mock_director = MagicMock(spec=DirectorAgent)
        mock_director.run = AsyncMock(return_value=make_sample_scripts())

        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test"}):
            orchestrator = Orchestrator(
                researcher=mock_researcher,
                director=mock_director,
            )

        result = await orchestrator.run("https://example.com/product")

        assert result.status == "failed"
        assert len(result.errors) > 0
        # Director should NOT have been called
        mock_director.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_brand_context_passed_to_both_agents(self):
        from orchestrator.agent import Orchestrator
        from researcher.agent import ResearcherAgent
        from director.agent import DirectorAgent

        mock_researcher = MagicMock(spec=ResearcherAgent)
        mock_researcher.run = AsyncMock(return_value=SAMPLE_RESEARCH)
        mock_director = MagicMock(spec=DirectorAgent)
        mock_director.run = AsyncMock(return_value=make_sample_scripts())

        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test"}):
            orchestrator = Orchestrator(
                researcher=mock_researcher,
                director=mock_director,
            )

        await orchestrator.run(
            "https://example.com/product",
            brand_tone="bold and direct",
            brand_audience="fitness enthusiasts",
        )

        # Check researcher received brand context
        researcher_call = mock_researcher.run.call_args
        assert researcher_call.kwargs.get("brand_tone") == "bold and direct"
        assert researcher_call.kwargs.get("brand_audience") == "fitness enthusiasts"

        # Check director received brand context
        director_call = mock_director.run.call_args
        assert director_call.kwargs.get("brand_tone") == "bold and direct"
        assert director_call.kwargs.get("brand_audience") == "fitness enthusiasts"

    @pytest.mark.asyncio
    async def test_result_has_no_errors_on_success(self):
        orchestrator = self._make_orchestrator()
        result = await orchestrator.run("https://example.com/product")
        assert result.errors == []


# ---------------------------------------------------------------------------
# Integration test — full pipeline, real Groq, real URL
# Run: pytest tests/test_orchestrator.py -v -m integration -s
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestOrchestratorIntegration:

    @pytest.mark.asyncio
    async def test_full_pipeline_url_to_scripts(self):
        """
        Full pipeline: URL → Research → 5 Scripts
        Requires: GROQ_API_KEY in .env + network access
        Takes ~30-60 seconds (research + director)
        """
        from orchestrator.agent import Orchestrator

        progress_log: list[str] = []

        async def log_progress(job_id: str, percent: int, message: str):
            entry = f"[{percent:3d}%] {message}"
            progress_log.append(entry)
            print(f"\n{entry}")

        orchestrator = Orchestrator(progress_callback=log_progress)

        result = await orchestrator.run(
            product_url="https://www.allbirds.com/products/mens-tree-runners",
            job_id="integration-test",
            brand_tone="sustainable and confident",
            brand_audience="eco-conscious consumers 25-40",
        )

        print("\n" + "="*60)
        print(f"STATUS:   {result.status}")
        print(f"PRODUCT:  {result.research.product_name if result.research else 'N/A'}")
        print(f"SCRIPTS:  {len(result.scripts)}")
        print(f"ERRORS:   {result.errors}")
        print(f"WARNINGS: {len(result.warnings)}")

        if result.best_script:
            best = result.best_script
            print(f"\nBEST SCRIPT:")
            print(f"  Hook type: {best.hook_type}")
            print(f"  Hook line: {best.hook_line}")
            print(f"  Score:     {best.hook_score.score}/100")
            print(f"  Trigger:   {best.hook_score.primary_trigger}")
            print(f"  Platform:  {best.hook_score.best_platform}")
            print(f"  Words:     {best.word_count}")

        print("\nPROGRESS LOG:")
        for entry in progress_log:
            print(f"  {entry}")

        assert result.is_usable, f"Pipeline failed: {result.errors}"
        assert result.research is not None
        assert len(result.scripts) == 5
        assert result.status == "scripts_ready"