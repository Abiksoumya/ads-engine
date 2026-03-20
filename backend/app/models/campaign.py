"""
AdEngineAI — Campaign Models
==============================
Tables:
    campaigns       — campaign runs (one brand → many campaigns)
    scripts         — 5 hook scripts per campaign
    render_results  — video render output per script
"""

import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from app.models.base import Base, utcnow, new_uuid


class CampaignStatusEnum(str, enum.Enum):
    PENDING = "pending"
    RESEARCHING = "researching"
    SCRIPTING = "scripting"
    RENDERING = "rendering"
    QA = "qa"
    COMPLETE = "complete"
    FAILED = "failed"


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("brand_dna.id"),
        nullable=True,
    )

    product_url = Column(String(2000), nullable=False)
    status = Column(Enum(CampaignStatusEnum), default=CampaignStatusEnum.PENDING)
    job_id = Column(String(255), nullable=True)     # background task ID

    # Research output
    research_result = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)

    # Settings
    ugc_mode = Column(Boolean, default=False)
    voice_style = Column(String(100), default="professional")

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="campaigns")
    brand = relationship("BrandDNA", back_populates="campaigns")
    scripts = relationship("Script", back_populates="campaign", cascade="all, delete-orphan")


class Script(Base):
    __tablename__ = "scripts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hook
    hook_type = Column(String(50), nullable=False)   # problem/secret/social_proof/visual_first/emotional
    hook_line = Column(String(500), nullable=False)
    script_text = Column(Text, nullable=False)

    # Hook Score Explainer
    hook_score = Column(Integer, nullable=True)
    hook_trigger = Column(String(100), nullable=True)
    hook_reasoning = Column(Text, nullable=True)
    best_platform = Column(String(50), nullable=True)

    # Ad copy
    ad_headline = Column(String(100), nullable=True)
    ad_description = Column(String(300), nullable=True)

    # Platform captions
    caption_instagram = Column(Text, nullable=True)
    caption_tiktok = Column(Text, nullable=True)
    caption_linkedin = Column(Text, nullable=True)
    hashtags = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    # Relationships
    campaign = relationship("Campaign", back_populates="scripts")
    render_results = relationship(
        "RenderResult",
        back_populates="script",
        cascade="all, delete-orphan",
    )


class RenderResult(Base):
    __tablename__ = "render_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    script_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Audio
    audio_url = Column(String(2000), nullable=True)
    audio_duration_secs = Column(Float, nullable=True)
    is_mock_audio = Column(Boolean, default=False)

    # Video URLs per aspect ratio
    video_url_9x16 = Column(String(2000), nullable=True)   # Reels / TikTok
    video_url_1x1 = Column(String(2000), nullable=True)    # Feed
    video_url_16x9 = Column(String(2000), nullable=True)   # YouTube
    thumbnail_url = Column(String(2000), nullable=True)
    is_mock_video = Column(Boolean, default=False)

    # QA results
    qa_passed = Column(Boolean, nullable=True)
    qa_severity = Column(String(50), nullable=True)
    qa_issues = Column(JSON, default=list)
    qa_recommendation = Column(Text, nullable=True)

    provider = Column(String(50), nullable=True)    # "did" | "heygen" | "mock"
    render_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    # Relationships
    script = relationship("Script", back_populates="render_results")
    publish_jobs = relationship(
        "PublishJob",
        back_populates="render_result",
        cascade="all, delete-orphan",
    )