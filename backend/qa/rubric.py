"""
AdEngineAI — QA Rubric
========================
All quality rules live here.
Agent logic never contains raw rule strings.

To add/change quality rules: edit this file only.
Agent code stays untouched.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class QARule:
    code: str           # e.g. "AUDIO_MISSING"
    severity: str       # "fatal" | "warning"
    description: str    # shown to user
    auto_rerender: bool # if True, trigger automatic re-render


# ---------------------------------------------------------------------------
# All QA rules
# ---------------------------------------------------------------------------

RULES = [
    # Fatal — video cannot be used
    QARule("AUDIO_MISSING",      "fatal",   "No audio detected in video",                    True),
    QARule("VIDEO_EMPTY",        "fatal",   "Video file is empty or corrupted",              True),
    QARule("RENDER_FAILED",      "fatal",   "Video render returned an error",                True),
    QARule("DURATION_TOO_SHORT", "fatal",   "Video is under 10 seconds",                     True),

    # Warnings — video is usable but not ideal
    QARule("DURATION_OFF",       "warning", "Video duration is far from 60 seconds",         False),
    QARule("MOCK_VIDEO",         "warning", "Video is a mock — no real render performed",    False),
    QARule("UPLOAD_FAILED",      "warning", "Video could not be uploaded to storage",        False),
    QARule("LOW_CONFIDENCE",     "warning", "Research confidence was below 50%",             False),
]

RULES_BY_CODE = {r.code: r for r in RULES}


# ---------------------------------------------------------------------------
# QA system prompt
# ---------------------------------------------------------------------------

QA_SYSTEM = """You are a quality assurance specialist for AI-generated video ads.

Your job is to review render results and identify issues that would prevent
a video from being used in a real ad campaign.

Be strict but fair. A video with minor imperfections is still usable.
A video with missing audio or a failed render is not.

Always respond with valid JSON only. No markdown, no explanation."""


QA_SCHEMA = """{
  "hook_type": "string",
  "passed": true,
  "issues": [],
  "severity": "none | warning | fatal",
  "recommendation": "string — one sentence: approved | fix X before publishing | re-render required"
}"""


def build_qa_prompt(
    hook_type: str,
    audio_available: bool,
    audio_is_mock: bool,
    audio_duration: float,
    video_available: bool,
    video_is_mock: bool,
    video_url: str,
    render_errors: list[str],
    confidence_score: float,
) -> str:
    lines = [
        f"=== QA REVIEW: {hook_type.upper()} HOOK ===",
        "",
        "RENDER REPORT:",
        f"  Audio available:  {audio_available}",
        f"  Audio is mock:    {audio_is_mock}",
        f"  Audio duration:   {audio_duration:.1f}s",
        f"  Video available:  {video_available}",
        f"  Video is mock:    {video_is_mock}",
        f"  Video URL:        {video_url or 'none'}",
        f"  Render errors:    {render_errors or 'none'}",
        f"  Research confidence: {confidence_score:.0%}",
        "",
        "QUALITY RULES:",
        "  - FAIL if audio is missing or zero duration",
        "  - FAIL if video render returned errors",
        "  - WARN if video is mock (no real render)",
        "  - WARN if audio duration is under 15s or over 90s",
        "  - WARN if research confidence is below 50%",
        "  - PASS everything else",
        "",
        f"Return JSON matching this schema:\n{QA_SCHEMA}",
    ]
    return "\n".join(lines)