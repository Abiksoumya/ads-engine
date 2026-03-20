"""
AdEngineAI — Publish Models
=============================
Tables:
    publish_jobs          — publishing history per platform per video
    platform_connections  — encrypted OAuth tokens per platform per user
"""

import enum

from sqlalchemy import (
    Column, DateTime, Enum,
    ForeignKey, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from app.models.base import Base, utcnow, new_uuid


class PublishStatusEnum(str, enum.Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    render_result_id = Column(
        UUID(as_uuid=True),
        ForeignKey("render_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    platform = Column(String(50), nullable=False)   # youtube/instagram/facebook/linkedin/tiktok
    status = Column(Enum(PublishStatusEnum), default=PublishStatusEnum.PENDING)
    platform_post_id = Column(String(255), nullable=True)
    post_url = Column(String(2000), nullable=True)

    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    render_result = relationship("RenderResult", back_populates="publish_jobs")


class PlatformConnection(Base):
    __tablename__ = "platform_connections"
    __table_args__ = (UniqueConstraint("user_id", "platform"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform = Column(String(50), nullable=False)

    # Encrypted tokens — never store plain text
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(JSON, default=list)

    platform_user_id = Column(String(255), nullable=True)
    platform_username = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    user = relationship("User", back_populates="platform_connections")