"""
AdEngineAI — Video Creation Model
====================================
Stores user-created videos from the Video Creator flow (/create page).

Flow 2 (Video Creator):
  User types description → AI generates script + brief → user edits → renders

Different from Campaign (Flow 1) which starts with a product URL.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Column, String, Integer, Boolean,
    DateTime, ForeignKey, Text, JSON,
    Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class CreationStatus(str, Enum):
    PENDING = "pending"           # just created
    GENERATING_BRIEF = "generating_brief"  # visual director running
    BRIEF_READY = "brief_ready"   # brief generated, waiting for user
    APPROVED = "approved"         # user approved brief
    RENDERING = "rendering"       # Kling + FFmpeg running
    COMPLETE = "complete"         # final video ready
    FAILED = "failed"


class VideoCreation(Base):
    """
    A user-created video from the Video Creator flow.

    User provides:
    - A text description of what they want
    - Optional images to include

    AI generates:
    - A script (voiceover)
    - A video brief with scene-by-scene Kling prompts

    User edits brief → clicks render → gets final video.
    """
    __tablename__ = "video_creations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- User input ---
    title = Column(String(200), nullable=True)          # optional title
    user_prompt = Column(Text, nullable=False)           # what user typed
    uploaded_images = Column(JSON, nullable=False, default=list)  # list of image URLs

    # --- User preferences ---
    scene_count = Column(Integer, nullable=False, default=3)      # 3 or 6
    aspect_ratio = Column(String(10), nullable=False, default="9:16")
    subtitles = Column(Boolean, nullable=False, default=False)

    # --- User preferences for visual style ---
    preferred_tone = Column(String(100), nullable=True)
    preferred_palette = Column(String(100), nullable=True)
    preferred_pacing = Column(String(20), nullable=True)
    preferred_background = Column(String(100), nullable=True)

    # --- Status ---
    status = Column(
        SAEnum(CreationStatus, name="creation_status_enum"),
        nullable=False,
        default=CreationStatus.PENDING,
        index=True,
    )
    error_message = Column(Text, nullable=True)

    # --- Final output ---
    final_video_url = Column(String(500), nullable=True)
    final_video_9x16 = Column(String(500), nullable=True)
    final_video_1x1 = Column(String(500), nullable=True)
    final_video_16x9 = Column(String(500), nullable=True)
    audio_url = Column(String(500), nullable=True)

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
    user = relationship("User", lazy="select")
    video_brief = relationship(
        "VideoBrief",
        back_populates="creation",
        uselist=False,
        lazy="select",
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "title": self.title,
            "user_prompt": self.user_prompt,
            "uploaded_images": self.uploaded_images or [],
            "scene_count": self.scene_count,
            "aspect_ratio": self.aspect_ratio,
            "subtitles": self.subtitles,
            "preferred_tone": self.preferred_tone,
            "preferred_palette": self.preferred_palette,
            "preferred_pacing": self.preferred_pacing,
            "preferred_background": self.preferred_background,
            "status": self.status.value if self.status is not None else "pending",
            "error_message": self.error_message,
            "final_video_url": self.final_video_url,
            "final_video_9x16": self.final_video_9x16,
            "final_video_1x1": self.final_video_1x1,
            "final_video_16x9": self.final_video_16x9,
            "audio_url": self.audio_url,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
            "rendered_at": self.rendered_at.isoformat() if self.rendered_at is not None else None,
            "video_brief": self.video_brief.to_dict() if self.video_brief else None,
        }