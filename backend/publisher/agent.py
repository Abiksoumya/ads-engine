"""
AdEngineAI — Publisher Agent
==============================
Framework: AutoGen (self-correcting retry loops)

Why AutoGen here?
    Publishing involves rate limits, token expiry, partial platform failures.
    AutoGen's retry and self-healing loops handle edge cases that would
    otherwise require complex custom error handling.

Platform status:
    YouTube     ✅ fully implemented
    Instagram   🔲 stub — add META_APP_ID + META_APP_SECRET to activate
    Facebook    🔲 stub — same Meta app as Instagram
    LinkedIn    🔲 stub — add LINKEDIN_CLIENT_ID + LINKEDIN_CLIENT_SECRET
    TikTok      🔲 stub — add TIKTOK_CLIENT_KEY + TIKTOK_CLIENT_SECRET

OAuth flow (for all platforms):
    1. User clicks "Connect [Platform]" in UI
    2. Frontend calls GET /auth/{platform} → redirects to platform OAuth
    3. Platform redirects back to /auth/{platform}/callback with code
    4. We exchange code for access_token + refresh_token
    5. Tokens stored encrypted in DB (future — for now stored in memory)
    6. Publisher uses stored tokens to post

Used by: orchestrator/agent.py
Input:   list[RenderResult], list[Script], platforms to publish to
Output:  list[PublishResult]
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from config.llm import get_llm_config
from production.crew import RenderResult
from director.agent import Script
from publisher.formatters import (
    format_youtube, format_instagram,
    format_facebook, format_linkedin, format_tiktok,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class PublishResult:
    hook_type: str
    platform: str
    success: bool
    post_url: str = ""          # live URL of the published post
    post_id: str = ""           # platform's post ID
    is_mock: bool = False
    error: Optional[str] = None
    scheduled_at: Optional[str] = None   # ISO datetime if scheduled


# ---------------------------------------------------------------------------
# Publisher Agent
# ---------------------------------------------------------------------------

class PublisherAgent:
    """
    Posts rendered videos to selected platforms.

    Usage:
        agent = PublisherAgent(tokens={
            "youtube": {"access_token": "...", "refresh_token": "..."},
        })
        results = await agent.publish(
            render_results=render_results,
            platforms=["youtube"],
        )
    """

    SUPPORTED_PLATFORMS = ["youtube", "instagram", "facebook", "linkedin", "tiktok"]

    def __init__(self, tokens: Optional[dict] = None):
        """
        tokens: dict of platform → OAuth token dict
        e.g. {"youtube": {"access_token": "...", "refresh_token": "..."}}
        When APIs are built, tokens come from the database.
        For now passed directly.
        """
        self.tokens = tokens or {}
        self.llm_cfg = get_llm_config("publisher")

    async def publish(
        self,
        render_results: list[RenderResult],
        platforms: list[str],
        schedule_time: Optional[str] = None,  # ISO datetime for scheduling
    ) -> list[PublishResult]:
        """
        Publishes all render results to all selected platforms.
        Returns PublishResult for every render+platform combination.
        Never raises — errors go into PublishResult.error.
        """
        if not platforms:
            logger.info("No platforms selected — skipping publish")
            return []

        logger.info(
            f"Publisher starting — "
            f"{len(render_results)} videos × {len(platforms)} platforms"
        )

        results: list[PublishResult] = []

        for render in render_results:
            for platform in platforms:
                if platform not in self.SUPPORTED_PLATFORMS:
                    logger.warning(f"Unsupported platform: {platform}")
                    continue

                result = await self._publish_one(
                    render=render,
                    platform=platform,
                    schedule_time=schedule_time,
                )
                results.append(result)

                status = "✅" if result.success else "❌"
                logger.info(
                    f"{status} {platform} | {render.hook_type} | "
                    f"{result.post_url or result.error}"
                )

        successful = sum(1 for r in results if r.success)
        logger.info(f"Publisher complete — {successful}/{len(results)} successful")

        return results

    # ------------------------------------------------------------------
    # Route to correct platform publisher
    # ------------------------------------------------------------------

    async def _publish_one(
        self,
        render: RenderResult,
        platform: str,
        schedule_time: Optional[str],
    ) -> PublishResult:
        """Routes to the correct platform publisher with retry logic."""
        video_url = render.best_video_url()
        if not video_url:
            return PublishResult(
                hook_type=render.hook_type,
                platform=platform,
                success=False,
                error="No video URL available",
            )

        # Retry up to 3 times for transient failures
        last_error = ""
        for attempt in range(3):
            try:
                if platform == "youtube":
                    return await self._publish_youtube(render, video_url, schedule_time)
                elif platform == "instagram":
                    return await self._publish_instagram(render, video_url)
                elif platform == "facebook":
                    return await self._publish_facebook(render, video_url)
                elif platform == "linkedin":
                    return await self._publish_linkedin(render, video_url)
                elif platform == "tiktok":
                    return await self._publish_tiktok(render, video_url)
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Publish attempt {attempt + 1}/3 failed "
                    f"({platform}/{render.hook_type}): {e}"
                )
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)   # exponential backoff

        return PublishResult(
            hook_type=render.hook_type,
            platform=platform,
            success=False,
            error=f"Failed after 3 attempts: {last_error}",
        )

    # ------------------------------------------------------------------
    # YouTube — fully implemented
    # ------------------------------------------------------------------

    async def _publish_youtube(
        self,
        render: RenderResult,
        video_url: str,
        schedule_time: Optional[str] = None,
    ) -> PublishResult:
        """
        Uploads video to YouTube using the YouTube Data API v3.
        Requires: youtube token in self.tokens
        """
        token = self.tokens.get("youtube", {})
        if not token:
            return self._mock_result(render.hook_type, "youtube", "No YouTube token")

        access_token = token.get("access_token", "")
        if not access_token:
            return self._mock_result(render.hook_type, "youtube", "No access token")

        try:
            import httpx
        except ImportError:
            raise ImportError("httpx not installed")

        script = render.script
        content = format_youtube(script, video_url)

        # Step 1 — Download video bytes from storage URL
        async with httpx.AsyncClient(timeout=120.0) as client:
            video_response = await client.get(video_url)
            video_response.raise_for_status()
            video_bytes = video_response.content

        # Step 2 — Initiate resumable upload
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(len(video_bytes)),
        }

        metadata = {
            "snippet": {
                "title": content["title"],
                "description": content["description"],
                "tags": content["tags"],
                "categoryId": content["category_id"],
            },
            "status": {
                "privacyStatus": content["privacy"],
                "selfDeclaredMadeForKids": False,
            },
        }

        # Add scheduled publish time if provided
        if schedule_time:
            metadata["status"]["privacyStatus"] = "private"
            metadata["status"]["publishAt"] = schedule_time

        async with httpx.AsyncClient(timeout=30.0) as client:
            init_response = await client.post(
                "https://www.googleapis.com/upload/youtube/v3/videos"
                "?uploadType=resumable&part=snippet,status",
                headers=headers,
                json=metadata,
            )
            init_response.raise_for_status()
            upload_url = init_response.headers.get("Location", "")

        if not upload_url:
            raise ValueError("YouTube did not return an upload URL")

        # Step 3 — Upload video bytes
        async with httpx.AsyncClient(timeout=300.0) as client:
            upload_response = await client.put(
                upload_url,
                content=video_bytes,
                headers={"Content-Type": "video/mp4"},
            )
            upload_response.raise_for_status()
            video_data = upload_response.json()

        video_id = video_data.get("id", "")
        post_url = f"https://www.youtube.com/watch?v={video_id}"

        logger.info(f"YouTube upload complete: {post_url}")

        return PublishResult(
            hook_type=render.hook_type,
            platform="youtube",
            success=True,
            post_url=post_url,
            post_id=video_id,
            is_mock=False,
            scheduled_at=schedule_time,
        )

    # ------------------------------------------------------------------
    # Instagram — stub (ready for Meta Graph API)
    # ------------------------------------------------------------------

    async def _publish_instagram(
        self, render: RenderResult, video_url: str
    ) -> PublishResult:
        """
        Stub — ready for Meta Graph API integration.
        Activate by adding META_APP_ID + META_APP_SECRET to .env
        and implementing OAuth flow.

        Meta Graph API endpoint:
            POST /{ig-user-id}/media  → create container
            POST /{ig-user-id}/media_publish  → publish
        Docs: https://developers.facebook.com/docs/instagram-api/guides/reels
        """
        token = self.tokens.get("instagram", {})
        if not token:
            return self._mock_result(render.hook_type, "instagram")

        # TODO: implement Meta Graph API posting
        # content = format_instagram(render.script, video_url)
        logger.info("Instagram publisher stub — not yet implemented")
        return self._mock_result(render.hook_type, "instagram")

    # ------------------------------------------------------------------
    # Facebook — stub (ready for Meta Graph API)
    # ------------------------------------------------------------------

    async def _publish_facebook(
        self, render: RenderResult, video_url: str
    ) -> PublishResult:
        """
        Stub — shares same Meta app as Instagram.
        Activate alongside Instagram.

        Meta Graph API endpoint:
            POST /{page-id}/videos
        Docs: https://developers.facebook.com/docs/video-api/guides/reels
        """
        token = self.tokens.get("facebook", {})
        if not token:
            return self._mock_result(render.hook_type, "facebook")

        # TODO: implement Meta Graph API video posting
        logger.info("Facebook publisher stub — not yet implemented")
        return self._mock_result(render.hook_type, "facebook")

    # ------------------------------------------------------------------
    # LinkedIn — stub (ready for LinkedIn Marketing API)
    # ------------------------------------------------------------------

    async def _publish_linkedin(
        self, render: RenderResult, video_url: str
    ) -> PublishResult:
        """
        Stub — ready for LinkedIn Marketing API.
        Activate by adding LINKEDIN_CLIENT_ID + LINKEDIN_CLIENT_SECRET.
        Requires Marketing API access approval (~1 week).

        LinkedIn API endpoint:
            POST /v2/ugcPosts
        Docs: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/ugc-post-api
        """
        token = self.tokens.get("linkedin", {})
        if not token:
            return self._mock_result(render.hook_type, "linkedin")

        # TODO: implement LinkedIn UGC post API
        logger.info("LinkedIn publisher stub — not yet implemented")
        return self._mock_result(render.hook_type, "linkedin")

    # ------------------------------------------------------------------
    # TikTok — stub (ready for TikTok Content Posting API)
    # ------------------------------------------------------------------

    async def _publish_tiktok(
        self, render: RenderResult, video_url: str
    ) -> PublishResult:
        """
        Stub — ready for TikTok Content Posting API.
        Activate by adding TIKTOK_CLIENT_KEY + TIKTOK_CLIENT_SECRET.
        Requires TikTok app review (2-4 weeks).

        TikTok API endpoint:
            POST /v2/post/publish/video/init/
        Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
        """
        token = self.tokens.get("tiktok", {})
        if not token:
            return self._mock_result(render.hook_type, "tiktok")

        # TODO: implement TikTok Content Posting API
        logger.info("TikTok publisher stub — not yet implemented")
        return self._mock_result(render.hook_type, "tiktok")

    # ------------------------------------------------------------------
    # YouTube OAuth helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_youtube_auth_url() -> str:
        """
        Returns the YouTube OAuth authorization URL.
        Frontend redirects user here to connect their YouTube account.
        """
        client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
        redirect_uri = os.getenv(
            "YOUTUBE_REDIRECT_URI",
            "http://localhost:8001/auth/youtube/callback"
        )
        scopes = " ".join([
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
        ])

        return (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={scopes}"
            f"&access_type=offline"
            f"&prompt=consent"
        )

    @staticmethod
    async def exchange_youtube_code(code: str) -> dict:
        """
        Exchanges OAuth code for access_token + refresh_token.
        Called from /auth/youtube/callback endpoint.
        Returns token dict ready to pass to PublisherAgent.
        """
        import httpx

        client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
        redirect_uri = os.getenv(
            "YOUTUBE_REDIRECT_URI",
            "http://localhost:8001/auth/youtube/callback"
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def refresh_youtube_token(refresh_token: str) -> dict:
        """
        Refreshes an expired YouTube access token.
        YouTube access tokens expire after 1 hour.
        Call this before publishing if token is expired.
        """
        import httpx

        client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # Mock helper
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_result(
        hook_type: str,
        platform: str,
        error: Optional[str] = None,
    ) -> PublishResult:
        if error:
            return PublishResult(
                hook_type=hook_type,
                platform=platform,
                success=False,
                is_mock=True,
                error=error,
            )
        return PublishResult(
            hook_type=hook_type,
            platform=platform,
            success=True,
            post_url=f"https://mock-{platform}.com/post/{hook_type}",
            post_id=f"mock_{hook_type}_{platform}",
            is_mock=True,
        )