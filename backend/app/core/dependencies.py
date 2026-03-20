"""
AdEngineAI — FastAPI Dependencies
====================================
Dependency injection for all protected routes.

Usage in routes:
    # Require any authenticated user
    @router.get("/me")
    async def get_me(current_user = Depends(get_current_user)):
        ...

    # Require specific role
    @router.delete("/users/{id}")
    async def delete_user(current_user = Depends(require_role("admin"))):
        ...

    # Require minimum subscription plan
    @router.post("/campaigns")
    async def create_campaign(current_user = Depends(require_plan("starter"))):
        ...
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ForbiddenException,
    InsufficientRoleException,
    RateLimitException,
    SubscriptionRequiredException,
    UnauthorizedException,
)
from app.core.security import decode_access_token
from app.db.database import get_db

logger = logging.getLogger(__name__)

# HTTP Bearer scheme — extracts token from Authorization header
bearer_scheme = HTTPBearer(auto_error=False)

# Role hierarchy — higher index = more permissions
ROLE_HIERARCHY = ["viewer", "user", "agency", "admin", "superadmin"]

# Plan hierarchy
PLAN_HIERARCHY = ["free", "starter", "pro", "agency"]


# ---------------------------------------------------------------------------
# Current user dataclass — passed to all protected routes
# ---------------------------------------------------------------------------

@dataclass
class CurrentUser:
    user_id: UUID
    role: str
    plan: str

    def has_role(self, required: str) -> bool:
        """Returns True if user has required role or higher."""
        try:
            user_level = ROLE_HIERARCHY.index(self.role)
            required_level = ROLE_HIERARCHY.index(required)
            return user_level >= required_level
        except ValueError:
            return False

    def has_plan(self, required: str) -> bool:
        """Returns True if user has required plan or higher."""
        try:
            user_level = PLAN_HIERARCHY.index(self.plan)
            required_level = PLAN_HIERARCHY.index(required)
            return user_level >= required_level
        except ValueError:
            return False

    @property
    def is_admin(self) -> bool:
        return self.has_role("admin")

    @property
    def is_superadmin(self) -> bool:
        return self.role == "superadmin"


# ---------------------------------------------------------------------------
# Core auth dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """
    Validates JWT token and returns current user.
    Raises UnauthorizedException if token is missing or invalid.

    Use this as a dependency on any protected route.
    """
    if not credentials:
        raise UnauthorizedException("No authentication token provided")

    token = credentials.credentials
    payload = decode_access_token(token)   # raises InvalidTokenException if invalid

    user_id_str = payload.get("sub")
    role = payload.get("role", "user")
    plan = payload.get("plan", "free")

    if not user_id_str:
        raise UnauthorizedException("Invalid token payload")

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise UnauthorizedException("Invalid user ID in token")

    return CurrentUser(user_id=user_id, role=role, plan=plan)


# ---------------------------------------------------------------------------
# Optional auth — doesn't fail if no token
# ---------------------------------------------------------------------------

async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser | None:
    """
    Like get_current_user but returns None instead of raising.
    Use for endpoints that work for both authenticated and anonymous users.
    """
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------

def require_role(minimum_role: str):
    """
    Dependency factory — requires minimum role or higher.

    Usage:
        @router.get("/admin/users")
        async def list_users(user = Depends(require_role("admin"))):
            ...
    """
    async def _check_role(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if not current_user.has_role(minimum_role):
            raise InsufficientRoleException(minimum_role)
        return current_user

    return _check_role


def require_superadmin():
    """Requires superadmin role exactly."""
    async def _check(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if not current_user.is_superadmin:
            raise ForbiddenException("Superadmin access required")
        return current_user
    return _check


# ---------------------------------------------------------------------------
# Plan-based access control
# ---------------------------------------------------------------------------

def require_plan(minimum_plan: str):
    """
    Dependency factory — requires minimum subscription plan.

    Usage:
        @router.post("/campaigns/publish")
        async def publish(user = Depends(require_plan("starter"))):
            ...
    """
    async def _check_plan(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if not current_user.has_plan(minimum_plan):
            raise SubscriptionRequiredException(minimum_plan)
        return current_user

    return _check_plan


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def rate_limit(max_per_minute: int = settings.RATE_LIMIT_PER_MINUTE):
    """
    Redis-backed per-user rate limiter.
    Falls back gracefully if Redis is unavailable.

    Usage:
        @router.post("/campaigns")
        async def create(
            _=Depends(rate_limit(10)),   # max 10/min
            user=Depends(get_current_user),
        ):
            ...
    """
    async def _check_rate(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user),
    ) -> None:
        try:
            import redis.asyncio as aioredis

            redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            key = f"rate:{current_user.user_id}:{request.url.path}"

            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)

            await redis.aclose()

            if count > max_per_minute:
                raise RateLimitException(retry_after=60)

        except RateLimitException:
            raise
        except Exception as e:
            # Redis unavailable — fail open (don't block requests)
            logger.warning(f"Rate limit check failed (Redis unavailable): {e}")

    return _check_rate


def auth_rate_limit():
    """Stricter rate limit for auth endpoints."""
    return rate_limit(settings.RATE_LIMIT_AUTH_PER_MINUTE)


# ---------------------------------------------------------------------------
# Database dependency (re-exported for convenience)
# ---------------------------------------------------------------------------

get_db_session = get_db