"""
AdEngineAI — Video Brief Model
================================
Stores the visual director's output — how each video should look.

One VideoBrief per script (campaign flow)
One VideoBrief per creation (video creator flow)

User can edit the brief before rendering.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, ForeignKey, Text, JSON, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class BriefStatus(str, Enum):
    DRAFT = "draft"           # just generated, not approved
    APPROVED = "approved"     # user reviewed and approved
    RENDERING = "rendering"   # Kling generating scenes
    COMPLETE = "complete"     # final video ready
    FAILED = "failed"         # something went wrong


class VideoBrief(Base):
    """
    Video brief — the visual director's plan for a video.

    Contains:
    - Overall settings (tone, palette, pacing)
    - Scene-by-scene breakdown with Kling prompts
    - Status tracking

    Linked to either:
    - script_id (campaign flow — product ad)
    - creation_id (video creator flow — any video)
    """
    __tablename__ = "video_briefs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # --- Source (one of these will be set) ---
    script_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scripts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    creation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("video_creations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # --- Overall video settings ---
    tone = Column(String(100), nullable=False, default="professional")
    color_palette = Column(String(100), nullable=False, default="vibrant")
    pacing = Column(String(20), nullable=False, default="medium")
    music_mood = Column(String(50), nullable=False, default="none")
    voiceover_script = Column(Text, nullable=True)

    # --- Structure ---
    scene_count = Column(Integer, nullable=False, default=3)
    duration_secs = Column(Integer, nullable=False, default=30)
    aspect_ratio = Column(String(10), nullable=False, default="9:16")
    subtitles = Column(Boolean, nullable=False, default=False)

    # --- Scenes (JSON array of scene dicts) ---
    # Each scene: {scene_number, duration, background, action,
    #              color_mood, camera, text_overlay,
    #              use_product_image, product_image_url, kling_prompt}
    scenes = Column(JSON, nullable=False, default=list)

    # --- Status ---
    status = Column(
        SAEnum(BriefStatus, name="brief_status_enum"),
        nullable=False,
        default=BriefStatus.DRAFT,
        index=True,
    )
    error_message = Column(Text, nullable=True)

    # --- Final video URLs (after rendering) ---
    final_video_url = Column(String(500), nullable=True)
    final_video_9x16 = Column(String(500), nullable=True)
    final_video_1x1 = Column(String(500), nullable=True)
    final_video_16x9 = Column(String(500), nullable=True)

    # --- Timestamps ---
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    rendered_at = Column(DateTime(timezone=True), nullable=True)

    # --- Relationships ---
    script = relationship("Script", back_populates="video_brief", lazy="select")
    creation = relationship("VideoCreation", back_populates="video_brief", lazy="select")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "script_id": str(self.script_id) if self.script_id is not None else None,
            "creation_id": str(self.creation_id) if self.creation_id is not None else None,
            "tone": self.tone,
            "color_palette": self.color_palette,
            "pacing": self.pacing,
            "music_mood": self.music_mood,
            "voiceover_script": self.voiceover_script,
            "scene_count": self.scene_count,
            "duration_secs": self.duration_secs,
            "aspect_ratio": self.aspect_ratio,
            "subtitles": self.subtitles,
            "scenes": self.scenes or [],
            "status": self.status.value if self.status is not None else "draft",
            "error_message": self.error_message,
            "final_video_url": self.final_video_url,
            "final_video_9x16": self.final_video_9x16,
            "final_video_1x1": self.final_video_1x1,
            "final_video_16x9": self.final_video_16x9,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
"updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
"rendered_at": self.rendered_at.isoformat() if self.rendered_at is not None else None
        }