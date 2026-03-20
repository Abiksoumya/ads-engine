"""
AdEngineAI — User Models
==========================
Tables:
    users       — core user accounts
    roles       — role definitions
    user_roles  — many-to-many user ↔ role
"""

import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum,
    ForeignKey, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import UUID as UUIDType


from app.models.base import Base, utcnow, new_uuid


class RoleEnum(str, enum.Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    AGENCY = "agency"
    USER = "user"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    avatar_url = Column(String(500), nullable=True)

    

    # Stripe
    stripe_customer_id = Column(String(255), unique=True, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user_roles = relationship("UserRole",back_populates="user",cascade="all, delete-orphan",foreign_keys="UserRole.user_id",)
    subscription = relationship("Subscription", back_populates="user", uselist=False)
    brands = relationship("BrandDNA", back_populates="user", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="user", cascade="all, delete-orphan")
    platform_connections = relationship("PlatformConnection", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


    @property
    def is_active_bool(self) -> bool:
        return bool(self.is_active)

    @property
    def hashed_password_str(self) -> str:
        return str(self.hashed_password)
    

    @property
    def typed_id(self) -> UUIDType:
        return UUIDType(str(self.id))

    @property
    def active(self) -> bool:
        return bool(self.is_active)

    @property
    def verified(self) -> bool:
        return bool(self.is_verified)

    @property
    def password_hash(self) -> str:
        return str(self.hashed_password)

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class Role(Base):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name = Column(Enum(RoleEnum), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user_roles = relationship("UserRole", back_populates="role")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), default=utcnow)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="user_roles", foreign_keys=[user_id])
    role = relationship("Role", back_populates="user_roles")