"""
AdEngineAI — Audit Log Model
==============================
Table:
    audit_logs  — security audit trail for all sensitive actions

Every login, campaign creation, plan change, and admin action
is logged here. Never delete audit logs.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from app.models.base import Base, utcnow, new_uuid


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # What happened
    action = Column(String(100), nullable=False, index=True)
    # e.g. "auth.login" | "campaign.create" | "plan.upgrade" | "admin.deactivate_user"

    resource_type = Column(String(50), nullable=True)   # "campaign" | "user" | "subscription"
    resource_id = Column(String(255), nullable=True)

    # Request context
    ip_address = Column(String(45), nullable=True)      # supports IPv6
    user_agent = Column(String(500), nullable=True)

    # Extra data
    extra_data = Column(JSON, default=dict)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} by {self.user_id}>"