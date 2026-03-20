"""
AdEngineAI — Publisher Agent Tests
=====================================
Unit tests: mock tokens, no real API calls.
Integration test: real YouTube OAuth flow.

Run unit tests:
    pytest tests/test_publisher.py -v -k "not integration"

Run integration (requires real YouTube token):
    pytest tests/test_publisher.py -v -m integration -s
"""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

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
        ad_headline="Dark Spots Gone in 3 Weeks",
        ad_description="Clinical grade vitamin C that actually works.",
        caption_instagram="Instagram caption here #skincare",
        caption_tiktok="TikTok caption here",
        caption_linkedin="LinkedIn professional caption here.",
        hashtags=["#skincare", "#vitaminc", "#darkspots", "#glowup", "#beauty"],
    )

def make_render(hook_type: str, video_url: str = "") -> RenderResult:
    audio = AudioResult(
        hook_type=hook_type,
        audio_url="https://cloudinary.com/audio.mp3",
        audio_bytes=b"audio",
        voice_id="test",
        duration_secs=58.0,
        is_mock=False,
    )
    url = video_url or f"https://d-id.com/{hook_type}_9x16.mp4"
    video = DIDVideoResult(
        hook_type=hook_type,
        video_url=url,
        thumbnail_url="",
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

FIVE_RENDERS = [
    make_render(h)
    for h in ["problem", "secret", "social_proof", "visual_first", "emotional"]
]

MOCK_YOUTUBE_TOKEN = {
    "access_token": "mock_access_token",
    "refresh_token": "mock_refresh_token",
    "token_type": "Bearer",
    "expires_in": 3600,
}


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------

class TestFormatters:

    def test_youtube_format(self):
        from publisher.formatters import format_youtube
        script = make_script("problem")
        content = format_youtube(script, "https://video.mp4")
        assert content["title"] == "Dark Spots Gone in 3 Weeks"
        assert "word" in content["description"]
        assert isinstance(content["tags"], list)
        assert content["privacy"] == "public"
        assert len(content["title"]) <= 100

    def test_instagram_format(self):
        from publisher.formatters import format_instagram
        script = make_script("problem")
        content = format_instagram(script, "https://video.mp4")
        assert "caption" in content
        assert len(content["caption"]) <= 2200
        assert content["media_type"] == "REELS"

    def test_linkedin_format(self):
        from publisher.formatters import format_linkedin
        script = make_script("problem")
        content = format_linkedin(script, "https://video.mp4")
        assert "text" in content
        assert len(content["text"]) <= 3000
        assert content["visibility"] == "PUBLIC"

    def test_tiktok_format(self):
        from publisher.formatters import format_tiktok
        script = make_script("problem")
        content = format_tiktok(script, "https://video.mp4")
        assert "caption" in content
        assert len(content["caption"]) <= 2200

    def test_facebook_format(self):
        from publisher.formatters import format_facebook
        script = make_script("problem")
        content = format_facebook(script, "https://video.mp4")
        assert "description" in content
        assert "title" in content


# ---------------------------------------------------------------------------
# Publisher Agent unit tests
# ---------------------------------------------------------------------------

class TestPublisherAgent:

    def _make_agent(self, tokens=None):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test"}):
            from publisher.agent import PublisherAgent
            return PublisherAgent(tokens=tokens or {})

    @pytest.mark.asyncio
    async def test_no_platforms_returns_empty(self):
        agent = self._make_agent()
        results = await agent.publish(FIVE_RENDERS, platforms=[])
        assert results == []

    @pytest.mark.asyncio
    async def test_mock_publish_without_tokens(self):
        agent = self._make_agent(tokens={})
        results = await agent.publish(
            FIVE_RENDERS[:1],
            platforms=["youtube"],
        )
        assert len(results) == 1
        assert results[0].platform == "youtube"
        assert results[0].is_mock is True

    @pytest.mark.asyncio
    async def test_publish_returns_result_per_render_per_platform(self):
        agent = self._make_agent()
        results = await agent.publish(
            FIVE_RENDERS,
            platforms=["youtube", "instagram"],
        )
        # 5 renders × 2 platforms = 10 results
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_unsupported_platform_skipped(self):
        agent = self._make_agent()
        results = await agent.publish(
            FIVE_RENDERS[:1],
            platforms=["snapchat"],  # not supported
        )
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_mock_stubs_for_instagram(self):
        agent = self._make_agent(tokens={})
        results = await agent.publish(FIVE_RENDERS[:1], platforms=["instagram"])
        assert results[0].platform == "instagram"
        assert results[0].is_mock is True

    @pytest.mark.asyncio
    async def test_mock_stubs_for_linkedin(self):
        agent = self._make_agent(tokens={})
        results = await agent.publish(FIVE_RENDERS[:1], platforms=["linkedin"])
        assert results[0].platform == "linkedin"
        assert results[0].is_mock is True

    @pytest.mark.asyncio
    async def test_mock_stubs_for_tiktok(self):
        agent = self._make_agent(tokens={})
        results = await agent.publish(FIVE_RENDERS[:1], platforms=["tiktok"])
        assert results[0].platform == "tiktok"
        assert results[0].is_mock is True

    @pytest.mark.asyncio
    async def test_never_raises(self):
        agent = self._make_agent()
        # Even with a completely broken render
        broken = make_render("problem", video_url="")
        broken.video_9x16 = None
        broken.video_1x1 = None
        broken.video_16x9 = None
        results = await agent.publish([broken], platforms=["youtube"])
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error is not None

    @pytest.mark.asyncio
    async def test_scheduled_publish(self):
        agent = self._make_agent(tokens={})
        results = await agent.publish(
            FIVE_RENDERS[:1],
            platforms=["youtube"],
            schedule_time="2026-04-01T10:00:00Z",
        )
        assert len(results) == 1

    def test_youtube_auth_url_contains_required_params(self):
        with patch.dict(os.environ, {
            "YOUTUBE_CLIENT_ID": "test-client-id",
            "YOUTUBE_REDIRECT_URI": "http://localhost:8001/auth/youtube/callback",
        }):
            from publisher.agent import PublisherAgent
            url = PublisherAgent.get_youtube_auth_url()
            assert "test-client-id" in url
            assert "youtube.upload" in url
            assert "youtube.readonly" in url
            assert "offline" in url
            assert "consent" in url

    @pytest.mark.asyncio
    async def test_all_platforms_publish(self):
        agent = self._make_agent(tokens={})
        results = await agent.publish(
            FIVE_RENDERS[:1],
            platforms=["youtube", "instagram", "facebook", "linkedin", "tiktok"],
        )
        assert len(results) == 5
        platforms_published = {r.platform for r in results}
        assert platforms_published == {
            "youtube", "instagram", "facebook", "linkedin", "tiktok"
        }


# ---------------------------------------------------------------------------
# Integration test — real YouTube upload
# Run: pytest tests/test_publisher.py -v -m integration -s
# NOTE: Requires a real YouTube OAuth token.
# Get one by running the OAuth flow manually first.
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPublisherIntegration:

    @pytest.mark.asyncio
    async def test_youtube_auth_url_generation(self):
        """
        Tests that YouTube auth URL is correctly generated.
        Does NOT require a real token — just checks the URL format.
        """
        from publisher.agent import PublisherAgent

        url = PublisherAgent.get_youtube_auth_url()
        print(f"\nYouTube OAuth URL:\n{url}")
        print("\nOpen this URL in a browser to get an OAuth code.")
        print("Then exchange it with PublisherAgent.exchange_youtube_code(code)")

        assert "accounts.google.com" in url
        assert "youtube.upload" in url
        assert os.getenv("YOUTUBE_CLIENT_ID", "") in url

    @pytest.mark.asyncio
    async def test_youtube_upload_with_mock_video(self):
        """
        Tests YouTube upload with a real token but a public test video.
        Requires: YOUTUBE_ACCESS_TOKEN set in .env (get via OAuth flow)
        """
        access_token = os.getenv("YOUTUBE_ACCESS_TOKEN", "")
        if not access_token:
            pytest.skip(
                "YOUTUBE_ACCESS_TOKEN not set. "
                "Run OAuth flow first to get a token."
            )

        from publisher.agent import PublisherAgent

        agent = PublisherAgent(tokens={
            "youtube": {"access_token": access_token}
        })

        # Use a small public test video
        test_render = make_render(
            "problem",
            video_url="https://www.w3schools.com/html/mov_bbb.mp4"
        )

        results = await agent.publish([test_render], platforms=["youtube"])

        print(f"\nYouTube publish result:")
        print(f"  Success:  {results[0].success}")
        print(f"  Post URL: {results[0].post_url}")
        print(f"  Error:    {results[0].error}")

        assert len(results) == 1