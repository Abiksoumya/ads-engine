"""
AdEngineAI — Brand Model
==========================
Table:
    brand_dna  — brand profiles with AI-learned performance data

One user can have multiple brands.
Agency users manage one brand per client.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Float,
    ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from app.models.base import Base, utcnow, new_uuid


class BrandDNA(Base):
    __tablename__ = "brand_dna"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Brand identity
    name = Column(String(255), nullable=False)
    tone = Column(String(255), default="professional")
    audience = Column(Text, nullable=True)
    colors = Column(JSON, default=list)             # ["#FF6B6B", "#FFFFFF"]
    avoid_topics = Column(JSON, default=list)       # ["competitors", "medical claims"]

    # AI preferences
    preferred_actor = Column(String(100), default="professional")
    preferred_voice = Column(String(100), default="professional")

    # Performance learnings — updated automatically after campaigns
    top_hooks = Column(JSON, default=list)          # ["problem", "social_proof"]
    avg_confidence = Column(Float, default=0.0)
    total_campaigns = Column(Integer, default=0)

    # Flags
    is_default = Column(Boolean, default=False)     # user's default brand

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    user = relationship("User", back_populates="brands")
    campaigns = relationship("Campaign", back_populates="brand")

    def __repr__(self) -> str:
        return f"<BrandDNA {self.name}>"