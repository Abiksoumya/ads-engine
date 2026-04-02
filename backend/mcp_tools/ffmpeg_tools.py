"""
AdEngineAI — FFmpeg Video Stitcher
=====================================
Combines Kling video scenes + ElevenLabs audio
into a final polished video ad.

Pipeline:
  1. Download all scene clips from URLs
  2. Download voiceover audio
  3. Concatenate video clips
  4. Mix voiceover over video
  5. Burn hook text overlay on scene 1
  6. Burn CTA text overlay on last scene
  7. Burn subtitles if enabled
  8. Upload final video to Cloudinary
  9. Return final video URL

Used by:
  tasks/render_tasks.py
  production/crew.py
"""

import asyncio
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class StitchResult:
    """Result of FFmpeg stitching operation."""
    video_url: str              # Cloudinary URL of final video
    duration_secs: float
    aspect_ratio: str
    file_size_bytes: int = 0
    is_mock: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return bool(self.video_url) and not self.error


# ---------------------------------------------------------------------------
# FFmpeg Stitcher
# ---------------------------------------------------------------------------

class FFmpegStitcher:
    """
    Stitches video scenes + audio into a final video.

    Usage:
        stitcher = FFmpegStitcher()

        result = await stitcher.stitch(
            scene_urls=["https://kling.com/scene1.mp4", ...],
            audio_url="https://elevenlabs.com/voice.mp3",
            hook_text="Your feet are on fire by 3pm",
            cta_text="Shop now — free returns",
            subtitles=True,
            aspect_ratio="9:16",
        )

        print(result.video_url)  # Cloudinary URL
    """

    def __init__(self):
        self.cloudinary_configured = all([
            os.getenv("CLOUDINARY_CLOUD_NAME"),
            os.getenv("CLOUDINARY_API_KEY"),
            os.getenv("CLOUDINARY_API_SECRET"),
        ])

    # ------------------------------------------------------------------
    # Main stitch method
    # ------------------------------------------------------------------

    async def stitch(
        self,
        scene_urls: list[str],
        audio_url: str,
        hook_text: str,
        cta_text: str,
        aspect_ratio: str = "9:16",
        subtitles: bool = False,
        voiceover_script: Optional[str] = None,
    ) -> StitchResult:
        """
        Main entry point. Downloads, processes, stitches, uploads.

        Args:
            scene_urls: list of Kling video clip URLs in order
            audio_url: ElevenLabs voiceover MP3/WAV URL
            hook_text: text overlay for first scene
            cta_text: text overlay for last scene
            aspect_ratio: 9:16 / 1:1 / 16:9
            subtitles: burn subtitles into video
            voiceover_script: script text for subtitle generation

        Returns:
            StitchResult with final Cloudinary URL
        """
        # Filter out empty/None URLs
        valid_urls = [u for u in scene_urls if u]

        if not valid_urls:
            return StitchResult(
                video_url="",
                duration_secs=0,
                aspect_ratio=aspect_ratio,
                error="No valid scene URLs provided",
            )

        # Use temp directory for all intermediate files
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            try:
                # Step 1 — Download all files
                scene_paths = await self._download_scenes(valid_urls, tmp)
                audio_path = await self._download_file(audio_url, tmp, "audio.mp3")

                if not scene_paths:
                    raise ValueError("Failed to download any scene clips")

                # Step 2 — Concatenate scenes
                concat_path = tmp / "concat.mp4"
                await self._concatenate_scenes(scene_paths, concat_path)

                # Step 3 — Mix audio + video
                mixed_path = tmp / "mixed.mp4"
                await self._mix_audio(concat_path, audio_path, mixed_path)

                # Step 4 — Add text overlays
                overlaid_path = tmp / "overlaid.mp4"
                await self._add_text_overlays(
                    mixed_path,
                    overlaid_path,
                    hook_text=hook_text,
                    cta_text=cta_text,
                    total_scenes=len(scene_paths),
                    scene_duration=10,
                )

                # Step 5 — Add subtitles if requested
                final_path = tmp / "final.mp4"
                if subtitles and voiceover_script:
                    await self._add_subtitles(
                        overlaid_path,
                        final_path,
                        script=voiceover_script,
                    )
                else:
                    # Just copy overlaid as final
                    import shutil
                    shutil.copy(overlaid_path, final_path)

                # Step 6 — Upload to Cloudinary
                file_size = final_path.stat().st_size
                video_url = await self._upload_to_cloudinary(final_path)

                total_duration = len(scene_paths) * 10.0

                logger.info(
                    f"Stitch complete: {len(scene_paths)} scenes, "
                    f"{total_duration}s, {file_size} bytes → {video_url[:60]}..."
                )

                return StitchResult(
                    video_url=video_url,
                    duration_secs=total_duration,
                    aspect_ratio=aspect_ratio,
                    file_size_bytes=file_size,
                    is_mock=False,
                )

            except Exception as e:
                logger.error(f"FFmpeg stitch failed: {e}")
                return StitchResult(
                    video_url="",
                    duration_secs=0,
                    aspect_ratio=aspect_ratio,
                    error=str(e),
                )

    # ------------------------------------------------------------------
    # Download helpers
    # ------------------------------------------------------------------

    async def _download_scenes(
        self,
        urls: list[str],
        tmp: Path,
    ) -> list[Path]:
        """Downloads all scene clips concurrently."""
        tasks = [
            self._download_file(url, tmp, f"scene_{i+1}.mp4")
            for i, url in enumerate(urls)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        paths = []
        for i, r in enumerate(results):
            if isinstance(r, Path) and r.exists():
                paths.append(r)
            else:
                logger.warning(f"Scene {i+1} download failed: {r}")
        return paths

    async def _download_file(
        self,
        url: str,
        tmp: Path,
        filename: str,
    ) -> Path:
        """Downloads a single file to temp directory."""
        dest = tmp / filename
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            dest.write_bytes(response.content)
        logger.debug(f"Downloaded {filename} ({dest.stat().st_size} bytes)")
        return dest

    # ------------------------------------------------------------------
    # FFmpeg operations
    # ------------------------------------------------------------------

    async def _concatenate_scenes(
        self,
        scene_paths: list[Path],
        output: Path,
    ) -> None:
        """Concatenates video clips in order using FFmpeg concat demuxer."""
        import ffmpeg

        if len(scene_paths) == 1:
            # Only one scene — just copy it
            import shutil
            shutil.copy(scene_paths[0], output)
            return

        # Write concat list file
        concat_list = output.parent / "concat_list.txt"
        with open(concat_list, "w") as f:
            for path in scene_paths:
                f.write(f"file '{path}'\n")

        cmd = (
            ffmpeg
            .input(str(concat_list), format="concat", safe=0)
            .output(
                str(output),
                c="copy",
                movflags="+faststart",
            )
            .overwrite_output()
        )

        await self._run_ffmpeg(cmd)
        logger.debug(f"Concatenated {len(scene_paths)} scenes → {output.name}")

    async def _mix_audio(
        self,
        video_path: Path,
        audio_path: Path,
        output: Path,
    ) -> None:
        """Mixes voiceover audio over video, replacing original audio."""
        import ffmpeg

        video_input = ffmpeg.input(str(video_path))
        audio_input = ffmpeg.input(str(audio_path))

        cmd = (
            ffmpeg
            .output(
                video_input.video,
                audio_input.audio,
                str(output),
                vcodec="copy",
                acodec="aac",
                audio_bitrate="192k",
                shortest=None,          # stop when shortest stream ends
                movflags="+faststart",
            )
            .overwrite_output()
        )

        await self._run_ffmpeg(cmd)
        logger.debug(f"Mixed audio → {output.name}")

    async def _add_text_overlays(
        self,
        video_path: Path,
        output: Path,
        hook_text: str,
        cta_text: str,
        total_scenes: int,
        scene_duration: int = 10,
    ) -> None:
        """
        Burns text overlays:
          - Hook text on first scene (0 to scene_duration)
          - CTA text on last scene
        """
        import ffmpeg

        total_duration = total_scenes * scene_duration
        cta_start = (total_scenes - 1) * scene_duration

        # Clean text for FFmpeg (escape special chars)
        hook_clean = self._escape_ffmpeg_text(hook_text)
        cta_clean = self._escape_ffmpeg_text(cta_text)

        # Build drawtext filters
        drawtext_filters = []

        if hook_text:
            drawtext_filters.append(
                f"drawtext=text='{hook_clean}'"
                f":fontsize=48"
                f":fontcolor=white"
                f":borderw=3"
                f":bordercolor=black"
                f":x=(w-text_w)/2"
                f":y=h*0.15"
                f":enable='between(t,0,{scene_duration})'"
                f":font=Arial"
            )

        if cta_text:
            drawtext_filters.append(
                f"drawtext=text='{cta_clean}'"
                f":fontsize=42"
                f":fontcolor=white"
                f":borderw=3"
                f":bordercolor=black"
                f":x=(w-text_w)/2"
                f":y=h*0.82"
                f":enable='between(t,{cta_start},{total_duration})'"
                f":font=Arial"
            )

        if not drawtext_filters:
            import shutil
            shutil.copy(video_path, output)
            return

        vf = ",".join(drawtext_filters)

        cmd = (
            ffmpeg
            .input(str(video_path))
            .output(
                str(output),
                vf=vf,
                acodec="copy",
                movflags="+faststart",
            )
            .overwrite_output()
        )

        await self._run_ffmpeg(cmd)
        logger.debug(f"Text overlays added → {output.name}")

    async def _add_subtitles(
        self,
        video_path: Path,
        output: Path,
        script: str,
    ) -> None:
        """
        Burns auto-generated subtitles from voiceover script.
        Creates a simple SRT file and burns it in.
        """
        import ffmpeg

        # Generate simple SRT from script
        srt_path = video_path.parent / "subtitles.srt"
        self._generate_srt(script, srt_path)

        cmd = (
            ffmpeg
            .input(str(video_path))
            .output(
                str(output),
                vf=f"subtitles={srt_path}:force_style='FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2'",
                acodec="copy",
                movflags="+faststart",
            )
            .overwrite_output()
        )

        await self._run_ffmpeg(cmd)
        logger.debug(f"Subtitles added → {output.name}")

    # ------------------------------------------------------------------
    # Upload to Cloudinary
    # ------------------------------------------------------------------

    async def _upload_to_cloudinary(self, video_path: Path) -> str:
        """Uploads final video to Cloudinary and returns URL."""
        if not self.cloudinary_configured:
            logger.warning("Cloudinary not configured — returning local path")
            return f"file://{video_path}"

        try:
            import cloudinary
            import cloudinary.uploader

            cloudinary.config(
                cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
                api_key=os.getenv("CLOUDINARY_API_KEY"),
                api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            )

            public_id = f"adengineai/videos/{uuid.uuid4().hex}"

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: cloudinary.uploader.upload(
                    str(video_path),
                    resource_type="video",
                    public_id=public_id,
                    overwrite=True,
                    eager=[{"quality": "auto", "fetch_format": "mp4"}],
                )
            )

            url = result.get("secure_url", "")
            logger.info(f"Uploaded to Cloudinary: {url[:60]}...")
            return url

        except Exception as e:
            logger.error(f"Cloudinary upload failed: {e}")
            raise

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    async def _run_ffmpeg(self, cmd) -> None:
        """Runs FFmpeg command asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: cmd.run(
                capture_stdout=True,
                capture_stderr=True,
                quiet=True,
            )
        )

    @staticmethod
    def _escape_ffmpeg_text(text: str) -> str:
        """Escapes special characters for FFmpeg drawtext filter."""
        if not text:
            return ""
        return (
            text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )

    @staticmethod
    def _generate_srt(script: str, srt_path: Path) -> None:
        """
        Generates a simple SRT subtitle file from script text.
        Splits script into chunks and distributes evenly over video duration.
        """
        words = script.split()
        if not words:
            srt_path.write_text("")
            return

        # Split into chunks of ~8 words each
        chunk_size = 8
        chunks = [
            " ".join(words[i:i + chunk_size])
            for i in range(0, len(words), chunk_size)
        ]

        # Estimate duration per chunk
        total_duration = 60  # assume 60s max
        chunk_duration = total_duration / len(chunks)

        srt_lines = []
        for i, chunk in enumerate(chunks):
            start = i * chunk_duration
            end = start + chunk_duration - 0.5

            start_ts = _seconds_to_srt_timestamp(start)
            end_ts = _seconds_to_srt_timestamp(end)

            srt_lines.append(f"{i + 1}")
            srt_lines.append(f"{start_ts} --> {end_ts}")
            srt_lines.append(chunk)
            srt_lines.append("")

        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")


def _seconds_to_srt_timestamp(seconds: float) -> str:
    """Converts seconds to SRT timestamp format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"