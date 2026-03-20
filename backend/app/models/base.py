"""
AdEngineAI — Model Base
=========================
Shared base class and helpers used by all models.
Every model file imports from here.
"""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid():
    return uuid4()


__all__ = ["Base", "utcnow", "new_uuid"]