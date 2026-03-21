"""
AdEngineAI — User Routes
==========================
All user management endpoints.

Own profile (any authenticated user):
    GET    /api/users/me              → get own profile
    PUT    /api/users/me              → update own profile
    DELETE /api/users/me              → deactivate own account

Admin only:
    GET    /api/users                 → list all users
    GET    /api/users/{id}            → get user by ID
    PUT    /api/users/{id}/activate   → activate user
    PUT    /api/users/{id}/deactivate → deactivate user

Superadmin only:
    PUT    /api/users/{id}/role       → change user role
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.user_controller import UserController
from app.core.dependencies import (
    get_current_user,
    get_db_session,
    require_role,
    require_superadmin,
    CurrentUser,
)

router = APIRouter(prefix="/api/users", tags=["Users"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=255)
    avatar_url: str | None = Field(None, max_length=500)


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(superadmin|admin|agency|user|viewer)$")


# ---------------------------------------------------------------------------
# Own profile endpoints — any authenticated user
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    summary="Get my profile",
)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns the authenticated user's full profile."""
    controller = UserController(db)
    return await controller.get_me(current_user)


@router.put(
    "/me",
    summary="Update my profile",
)
async def update_me(
    body: UpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Updates full name and/or avatar URL."""
    controller = UserController(db)
    return await controller.update_me(body.model_dump(exclude_none=True), current_user)


@router.delete(
    "/me",
    summary="Deactivate my account",
)
async def deactivate_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Soft deletes the authenticated user's account.
    Account can be reactivated by an admin.
    """
    controller = UserController(db)
    return await controller.deactivate_me(current_user)


# ---------------------------------------------------------------------------
# Admin endpoints — require admin role or higher
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="List all users (admin)",
)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    is_active: bool | None = Query(None),
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Returns paginated list of all users.
    Optionally filter by is_active status.
    Requires: admin role or higher.
    """
    controller = UserController(db)
    return await controller.list_users(skip=skip, limit=limit, is_active=is_active)


@router.get(
    "/{user_id}",
    summary="Get user by ID (admin)",
)
async def get_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Returns any user's profile by ID.
    Requires: admin role or higher.
    """
    controller = UserController(db)
    return await controller.get_user(user_id)


@router.put(
    "/{user_id}/activate",
    summary="Activate user (admin)",
)
async def activate_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Activates a deactivated user account.
    Requires: admin role or higher.
    """
    controller = UserController(db)
    return await controller.activate_user(user_id)


@router.put(
    "/{user_id}/deactivate",
    summary="Deactivate user (admin)",
)
async def deactivate_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Deactivates a user account.
    Requires: admin role or higher.
    Cannot deactivate your own account this way.
    """
    controller = UserController(db)
    return await controller.deactivate_user(user_id, current_user)


# ---------------------------------------------------------------------------
# Superadmin endpoints
# ---------------------------------------------------------------------------

@router.put(
    "/{user_id}/role",
    summary="Change user role (superadmin)",
)
async def change_role(
    user_id: UUID,
    body: ChangeRoleRequest,
    current_user: CurrentUser = Depends(require_superadmin()),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Changes a user's role.
    Requires: superadmin only.
    """
    controller = UserController(db)
    return await controller.change_role(user_id, body.model_dump(), current_user)