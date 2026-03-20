"""
AdEngineAI — QA Agent Tests
==============================
Unit tests: no API keys needed — uses mock render results.
Integration test: real LLM review.

Run unit tests:
    pytest tests/test_qa.py -v -k "not integration"

Run integration:
    pytest tests/test_qa.py -v -m integration -s
"""

import os
import pytest
from unittest.mock import AsyncMock, patch

from director.agent import Script, HookScore
from mcp_tools.elevenlabs_tools import AudioResult
from mcp_tools.did_tools import VideoResult as DIDVideoResult
from production.crew import RenderResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_script(hook_type: str) -> Script:
    return Script(
        hook_type=hook_type,
        hook_line=f"Hook for {hook_type}",
        script=" ".join(["word"] * 150),
        hook_score=HookScore(85, "loss aversion", "Strong", "instagram"),
        ad_headline="Test Headline",
        ad_description="Test desc",
        caption_instagram="ig",
        caption_tiktok="tt",
        caption_linkedin="li",
        hashtags=["#test"],
    )

def make_good_render(hook_type: str) -> RenderResult:
    """A fully successful render result."""
    audio = AudioResult(
        hook_type=hook_type,
        audio_url=f"https://cloudinary.com/{hook_type}.mp3",
        audio_bytes=b"real_audio",
        voice_id="test-voice",
        duration_secs=58.0,
        is_mock=False,
    )
    video = DIDVideoResult(
        hook_type=hook_type,
        video_url=f"https://d-id.com/{hook_type}_9x16.mp4",
        thumbnail_url=f"https://d-id.com/{hook_type}_thumb.jpg",
        duration_secs=60.0,
        aspect_ratio="9x16",
        provider="did",
        is_mock=False,
    )
    return RenderResult(
        hook_type=hook_type,
        script=make_script(hook_type),
        audio=audio,
        video_9x16=video,
        video_1x1=video,
        video_16x9=video,
    )

def make_mock_render(hook_type: str) -> RenderResult:
    """A mock render — audio and video are fake."""
    audio = AudioResult(
        hook_type=hook_type,
        audio_url=f"https://mock-audio.com/{hook_type}.mp3",
        audio_bytes=b"mock",
        voice_id="mock",
        duration_secs=60.0,
        is_mock=True,
    )
    video = DIDVideoResult(
        hook_type=hook_type,
        video_url=f"https://mock-video.com/{hook_type}_9x16.mp4",
        thumbnail_url="",
        duration_secs=60.0,
        aspect_ratio="9x16",
        provider="mock",
        is_mock=True,
    )
    return RenderResult(
        hook_type=hook_type,
        script=make_script(hook_type),
        audio=audio,
        video_9x16=video,
        video_1x1=video,
        video_16x9=video,
    )

def make_failed_render(hook_type: str) -> RenderResult:
    """A render that failed completely."""
    return RenderResult(
        hook_type=hook_type,
        script=make_script(hook_type),
        audio=None,
        video_9x16=None,
        errors=[f"D-ID render failed for {hook_type}"],
    )

FIVE_GOOD_RENDERS = [
    make_good_render(h)
    for h in ["problem", "secret", "social_proof", "visual_first", "emotional"]
]

FIVE_MOCK_RENDERS = [
    make_mock_render(h)
    for h in ["problem", "secret", "social_proof", "visual_first", "emotional"]
]

SAMPLE_LLM_QA = {
    "hook_type": "problem",
    "passed": True,
    "issues": [],
    "severity": "none",
    "recommendation": "Approved",
}


# ---------------------------------------------------------------------------
# Rule-based QA tests (no LLM)
# ---------------------------------------------------------------------------

class TestQARuleBased:

    def _make_agent(self):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test"}):
            from qa.agent import QAAgent
            return QAAgent()

    def test_good_render_passes(self):
        agent = self._make_agent()
        result = agent._rule_based_check(make_good_render("problem"), 0.85)
        assert result.passed is True
        assert result.severity == "none"

    def test_failed_render_is_fatal(self):
        agent = self._make_agent()
        result = agent._rule_based_check(make_failed_render("problem"), 0.85)
        assert result.passed is False
        assert result.severity == "fatal"
        assert result.rerender_required is True

    def test_mock_render_is_warning(self):
        agent = self._make_agent()
        result = agent._rule_based_check(make_mock_render("problem"), 0.85)
        assert result.passed is True
        assert result.severity == "warning"
        assert result.rerender_required is False

    def test_missing_audio_is_fatal(self):
        agent = self._make_agent()
        render = make_good_render("problem")
        render.audio = None
        result = agent._rule_based_check(render, 0.85)
        assert result.severity == "fatal"
        assert result.rerender_required is True

    def test_low_confidence_is_warning(self):
        agent = self._make_agent()
        result = agent._rule_based_check(make_good_render("problem"), 0.3)
        assert result.severity == "warning"
        assert result.passed is True

    def test_is_publishable_for_warning(self):
        from qa.agent import QAResult
        result = QAResult(
            hook_type="problem",
            passed=True,
            severity="warning",
        )
        assert result.is_publishable is True

    def test_is_not_publishable_for_fatal(self):
        from qa.agent import QAResult
        result = QAResult(
            hook_type="problem",
            passed=False,
            severity="fatal",
        )
        assert result.is_publishable is False


# ---------------------------------------------------------------------------
# Full QA Agent tests
# ---------------------------------------------------------------------------

class TestQAAgent:

    def _make_agent(self):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test"}):
            from qa.agent import QAAgent
            return QAAgent()

    @pytest.mark.asyncio
    async def test_review_returns_five_results(self):
        agent = self._make_agent()
        with patch.object(agent, "_llm_review", new=AsyncMock(
            return_value=__import__("qa.agent", fromlist=["QAResult"]).QAResult(
                hook_type="problem", passed=True, severity="none",
                recommendation="Approved"
            )
        )):
            results = await agent.review(FIVE_MOCK_RENDERS)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_results_match_hook_types(self):
        agent = self._make_agent()
        with patch("qa.agent.complete_json", new=AsyncMock(return_value=SAMPLE_LLM_QA)):
            results = await agent.review(FIVE_MOCK_RENDERS)
        types = [r.hook_type for r in results]
        assert types == ["problem", "secret", "social_proof", "visual_first", "emotional"]

    @pytest.mark.asyncio
    async def test_fatal_skips_llm_review(self):
        from qa.agent import QAAgent, QAResult  # add QAResult here
        from production.crew import RenderResult as RR

        agent = QAAgent()
        failed_renders = [make_failed_render(h) for h in
                        ["problem", "secret", "social_proof", "visual_first", "emotional"]]

        llm_called = []
        original_llm = agent._llm_review

        async def track_llm(render: RR, confidence_score: float) -> QAResult:
            llm_called.append(render.hook_type)
            return await original_llm(render, confidence_score)

        agent._llm_review = track_llm  # type: ignore[method-assign]
        with patch("qa.agent.complete_json", new=AsyncMock(return_value=SAMPLE_LLM_QA)):
            results = await agent.review(failed_renders)

        assert len(llm_called) == 0
        assert all(r.severity == "fatal" for r in results)

    @pytest.mark.asyncio
    async def test_never_raises(self):
        agent = self._make_agent()
        with patch("qa.agent.complete_json", new=AsyncMock(side_effect=Exception("LLM down"))):
            results = await agent.review(FIVE_MOCK_RENDERS)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_merge_keeps_worst_severity(self):
        from qa.agent import QAAgent, QAResult
        agent = QAAgent.__new__(QAAgent)

        rule = QAResult("problem", True, ["mock video"], "warning")
        llm = QAResult("problem", True, [], "none", "Approved")
        merged = agent._merge_results(rule, llm)

        assert merged.severity == "warning"
        assert "mock video" in merged.issues

    @pytest.mark.asyncio
    async def test_merge_fatal_overrides_warning(self):
        from qa.agent import QAAgent, QAResult
        agent = QAAgent.__new__(QAAgent)

        rule = QAResult("problem", False, ["render failed"], "fatal", rerender_required=True)
        llm = QAResult("problem", True, [], "warning", "Fix before publishing")
        merged = agent._merge_results(rule, llm)

        assert merged.severity == "fatal"
        assert merged.passed is False
        assert merged.rerender_required is True


# ---------------------------------------------------------------------------
# Integration test — real LLM QA review
# Run: pytest tests/test_qa.py -v -m integration -s
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestQAIntegration:

    @pytest.mark.asyncio
    async def test_qa_review_with_real_llm(self):
        """
        Real LLM QA review of mock renders.
        Requires: GROQ_API_KEY in .env
        """
        from qa.agent import QAAgent

        agent = QAAgent()
        results = await agent.review(FIVE_MOCK_RENDERS, confidence_score=0.85)

        print("\n" + "="*60)
        print("QA REVIEW RESULTS")
        print("="*60)
        for result in results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"\n{status} {result.hook_type.upper()}")
            print(f"  Severity:       {result.severity}")
            print(f"  Issues:         {result.issues or 'none'}")
            print(f"  Publishable:    {result.is_publishable}")
            print(f"  Recommendation: {result.recommendation}")
            print(f"  Re-render:      {result.rerender_required}")

        assert len(results) == 5
        publishable = sum(1 for r in results if r.is_publishable)
        print(f"\nPublishable: {publishable}/5")