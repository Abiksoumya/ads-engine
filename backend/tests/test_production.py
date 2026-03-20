"""
AdEngineAI — Production Crew Tests
=====================================
Unit tests: mock tools, no API keys needed.
Integration test: real ElevenLabs audio + mock video.

Run unit tests:
    pytest tests/test_production.py -v -k "not integration"

Run integration (real ElevenLabs):
    pytest tests/test_production.py -v -m integration -s
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from director.agent import Script, HookScore
from mcp_tools.elevenlabs_tools import AudioResult
from mcp_tools.did_tools import VideoResult as DIDVideoResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_hook_score(score: int = 85) -> HookScore:
    return HookScore(
        score=score,
        primary_trigger="loss aversion",
        reasoning="Strong hook",
        best_platform="instagram",
    )

def make_script(hook_type: str) -> Script:
    return Script(
        hook_type=hook_type,
        hook_line=f"Hook for {hook_type}",
        script=" ".join(["word"] * 150),
        hook_score=make_hook_score(),
        ad_headline="Test Headline",
        ad_description="Test description",
        caption_instagram="Instagram caption",
        caption_tiktok="TikTok caption",
        caption_linkedin="LinkedIn caption",
        hashtags=["#test"],
    )

FIVE_SCRIPTS = [
    make_script(h)
    for h in ["problem", "secret", "social_proof", "visual_first", "emotional"]
]

MOCK_AUDIO = AudioResult(
    hook_type="problem",
    audio_url="https://mock-audio.com/problem.mp3",
    audio_bytes=b"mock_bytes",
    voice_id="test-voice",
    duration_secs=58.0,
    is_mock=True,
)

MOCK_VIDEO = DIDVideoResult(
    hook_type="problem",
    video_url="https://mock-video.com/problem_9x16.mp4",
    thumbnail_url="https://mock-video.com/problem_thumb.jpg",
    duration_secs=60.0,
    aspect_ratio="9x16",
    provider="mock",
    is_mock=True,
)


# ---------------------------------------------------------------------------
# ElevenLabs tool tests
# ---------------------------------------------------------------------------

class TestElevenLabsTool:

    @pytest.mark.asyncio
    async def test_mock_mode_when_no_api_key(self):
        from mcp_tools.elevenlabs_tools import ElevenLabsTool
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}, clear=False):
            tool = ElevenLabsTool(api_key="")
            tool._mock = True   # force mock mode explicitly
            result = await tool.generate("test script", "problem")
        assert result.is_mock is True

    @pytest.mark.asyncio
    async def test_returns_audio_result(self):
        from mcp_tools.elevenlabs_tools import ElevenLabsTool
        tool = ElevenLabsTool(api_key="")
        result = await tool.generate("test script", "problem")
        assert result.hook_type == "problem"
        assert result.duration_secs > 0

    @pytest.mark.asyncio
    async def test_batch_returns_correct_count(self):
        from mcp_tools.elevenlabs_tools import ElevenLabsTool
        tool = ElevenLabsTool(api_key="")
        scripts = [("script text", h) for h in
                   ["problem", "secret", "social_proof", "visual_first", "emotional"]]
        results = await tool.generate_batch(scripts)
        assert len(results) == 5

    def test_duration_estimate(self):
        from mcp_tools.elevenlabs_tools import ElevenLabsTool
        # 150 words at 2.5 words/sec = 60 seconds
        duration = ElevenLabsTool._estimate_duration(" ".join(["word"] * 150))
        assert abs(duration - 60.0) < 1.0

    @pytest.mark.asyncio
    async def test_never_raises_on_api_failure(self):
        from mcp_tools.elevenlabs_tools import ElevenLabsTool
        import httpx

        tool = ElevenLabsTool(api_key="bad-key")
        tool._mock = False  # force real path

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Connection failed")
            )
            result = await tool.generate("test", "problem")

        assert result.error is not None
        assert result.is_mock is True


# ---------------------------------------------------------------------------
# D-ID tool tests
# ---------------------------------------------------------------------------

class TestDIDTool:

    @pytest.mark.asyncio
    async def test_mock_mode(self):
        from mcp_tools.did_tools import DIDTool
        tool = DIDTool(api_key="mock")
        result = await tool.generate_video("https://audio.mp3", "problem", "9x16")
        assert result.is_mock is True
        assert result.success is True
        assert "9x16" in result.video_url

    @pytest.mark.asyncio
    async def test_generate_all_ratios_returns_three(self):
        from mcp_tools.did_tools import DIDTool
        tool = DIDTool(api_key="mock")
        results = await tool.generate_all_ratios("https://audio.mp3", "problem")
        assert set(results.keys()) == {"9x16", "1x1", "16x9"}

    @pytest.mark.asyncio
    async def test_all_ratio_videos_succeed_in_mock(self):
        from mcp_tools.did_tools import DIDTool
        tool = DIDTool(api_key="mock")
        results = await tool.generate_all_ratios("https://audio.mp3", "emotional")
        for ratio, video in results.items():
            assert video.success, f"Video failed for ratio {ratio}"

    @pytest.mark.asyncio
    async def test_never_raises_on_api_failure(self):
        from mcp_tools.did_tools import DIDTool
        tool = DIDTool(api_key="real-key-that-fails")
        tool._mock = False

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("API error")
            )
            result = await tool.generate_video("https://audio.mp3", "problem")

        assert result.error is not None


# ---------------------------------------------------------------------------
# Production Crew tests
# ---------------------------------------------------------------------------

class TestProductionCrew:

    def _make_crew(self):
        with patch.dict(os.environ, {
            "VIDEO_ENV": "mock",
            "STORAGE_ENV": "development",
            "CLOUDINARY_CLOUD_NAME": "test",
            "CLOUDINARY_API_KEY": "test",
            "CLOUDINARY_API_SECRET": "test",
        }):
            from production.crew import ProductionCrew
            return ProductionCrew(campaign_id="test-campaign-123")

    @pytest.mark.asyncio
    async def test_render_returns_five_results(self):
        crew = self._make_crew()
        results = await crew.render(FIVE_SCRIPTS)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_results_in_same_order_as_scripts(self):
        crew = self._make_crew()
        results = await crew.render(FIVE_SCRIPTS)
        for script, result in zip(FIVE_SCRIPTS, results):
            assert result.hook_type == script.hook_type

    @pytest.mark.asyncio
    async def test_all_results_have_audio(self):
        crew = self._make_crew()
        results = await crew.render(FIVE_SCRIPTS)
        for result in results:
            assert result.audio is not None

    @pytest.mark.asyncio
    async def test_all_results_have_videos(self):
        crew = self._make_crew()
        results = await crew.render(FIVE_SCRIPTS)
        for result in results:
            assert result.video_9x16 is not None
            assert result.video_1x1 is not None
            assert result.video_16x9 is not None

    @pytest.mark.asyncio
    async def test_mock_renders_succeed(self):
        crew = self._make_crew()
        results = await crew.render(FIVE_SCRIPTS)
        for result in results:
            assert result.success is True
            assert result.is_mock is True

    @pytest.mark.asyncio
    async def test_best_video_url_returns_string(self):
        crew = self._make_crew()
        results = await crew.render(FIVE_SCRIPTS)
        for result in results:
            url = result.best_video_url()
            assert isinstance(url, str)
            assert url != ""

    @pytest.mark.asyncio
    async def test_render_result_has_script(self):
        crew = self._make_crew()
        results = await crew.render(FIVE_SCRIPTS)
        for script, result in zip(FIVE_SCRIPTS, results):
            assert result.script.hook_line == script.hook_line


# ---------------------------------------------------------------------------
# Integration test — real ElevenLabs audio + mock video
# Run: pytest tests/test_production.py -v -m integration -s
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestProductionIntegration:

    @pytest.mark.asyncio
    async def test_real_elevenlabs_audio_generation(self):
        """
        Generates real audio with ElevenLabs for all 5 scripts.
        Requires: ELEVENLABS_API_KEY in .env
        """
        from mcp_tools.elevenlabs_tools import ElevenLabsTool

        api_key = os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            pytest.skip("ELEVENLABS_API_KEY not set")

        tool = ElevenLabsTool(api_key=api_key)
        script_text = (
            "Still seeing that same dark spot staring back in every selfie? "
            "You've tried everything. Nothing works. "
            "Here's what most brands won't tell you — "
            "the vitamin C in most drugstore serums degrades before it reaches your skin. "
            "SuperGlow uses clinical-grade formula that actually absorbs. "
            "Dark spots visibly fade within three weeks. "
            "47,000 women have already made the switch. "
            "Try SuperGlow today — link in bio."
        )

        result = await tool.generate(script_text, "problem", "professional")

        print(f"\nAudio generated:")
        print(f"  Hook type:   {result.hook_type}")
        print(f"  Duration:    {result.duration_secs:.1f}s")
        print(f"  Size:        {len(result.audio_bytes)} bytes")
        print(f"  Mock:        {result.is_mock}")
        print(f"  Error:       {result.error}")

        assert result.success
        assert not result.is_mock
        assert len(result.audio_bytes) > 1000
        assert result.duration_secs > 10

    @pytest.mark.asyncio
    async def test_full_production_crew_with_real_audio(self):
        """
        Full Production Crew run with real ElevenLabs + mock video.
        Requires: ELEVENLABS_API_KEY in .env
        """
        api_key = os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            pytest.skip("ELEVENLABS_API_KEY not set")

        with patch.dict(os.environ, {
            "VIDEO_ENV": "mock",
            "STORAGE_ENV": "development",
            "CLOUDINARY_CLOUD_NAME": "test",
            "CLOUDINARY_API_KEY": "test",
            "CLOUDINARY_API_SECRET": "test",
            "ELEVENLABS_API_KEY": api_key,
        }):
            from production.crew import ProductionCrew
            crew = ProductionCrew(campaign_id="integration-test")

        results = await crew.render(FIVE_SCRIPTS[:2])  # only 2 to save credits

        print(f"\nProduction Crew results:")
        for result in results:
            print(f"\n  Hook: {result.hook_type}")
            if result.audio:
                print(f"  Audio: {'real' if not result.audio.is_mock else 'mock'} "
                    f"({result.audio.duration_secs:.1f}s)")
            print(f"  Video: {result.best_video_url()}")
            print(f"  Success: {result.success}")
            print(f"  Errors: {result.errors}")

        assert all(r.success for r in results)