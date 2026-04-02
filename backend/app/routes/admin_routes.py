"""
AdEngineAI — Admin Routes
===========================
All admin endpoints. Requires admin or superadmin role.

GET  /api/admin/stats                      → platform stats
GET  /api/admin/users                      → list all users
PUT  /api/admin/users/{id}/plan            → assign plan to user
PUT  /api/admin/users/{id}/role            → change user role (superadmin only)
PUT  /api/admin/users/{id}/toggle-active   → activate/deactivate user
GET  /api/admin/plans                      → list all plans
PUT  /api/admin/plans/{plan_name}          → update plan limits
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.admin_controller import AdminController
from app.core.dependencies import (
    get_current_user,
    get_db_session,
    require_role,
    require_superadmin,
    CurrentUser,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class AssignPlanRequest(BaseModel):
    plan: str = Field(..., pattern="^(free|starter|pro|agency)$")


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(superadmin|admin|agency|user|viewer)$")


class UpdatePlanRequest(BaseModel):
    campaigns_per_month: int | None = None   # -1 = unlimited
    team_seats: int | None = None
    platforms_allowed: int | None = None
    ugc_mode: bool | None = None
    white_label: bool | None = None
    api_access: bool | None = None
    price_monthly: float | None = None
    price_yearly: float | None = None
    stripe_price_id_monthly: str | None = None
    stripe_price_id_yearly: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/stats", summary="Platform stats (admin)")
async def get_stats(
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns total users, campaigns, and subscriptions by plan."""
    controller = AdminController(db)
    return await controller.get_stats()


@router.get("/users", summary="List all users (admin)")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Returns all users with their roles and plans.
    Supports search by email or name.
    Requires: admin role or higher.
    """
    controller = AdminController(db)
    return await controller.list_users(skip=skip, limit=limit, search=search)


@router.put("/users/{user_id}/plan", summary="Assign plan to user (admin)")
async def assign_plan(
    user_id: UUID,
    body: AssignPlanRequest,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Manually assigns a subscription plan to a user.
    Use this before Stripe is set up to onboard early users.
    Requires: admin role or higher.
    """
    controller = AdminController(db)
    return await controller.assign_plan(user_id, body.model_dump(), current_user)


@router.put("/users/{user_id}/role", summary="Change user role (superadmin)")
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
    controller = AdminController(db)
    return await controller.change_role(user_id, body.model_dump(), current_user)


@router.put("/users/{user_id}/toggle-active", summary="Toggle user active status (admin)")
async def toggle_active(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Activates or deactivates a user account.
    Requires: admin role or higher.
    """
    controller = AdminController(db)
    return await controller.toggle_active(user_id, current_user)


@router.get("/plans", summary="List all subscription plans (admin)")
async def list_plans(
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns all subscription plans with their limits and pricing."""
    controller = AdminController(db)
    return await controller.list_plans()


@router.put("/plans/{plan_name}", summary="Update plan limits (superadmin)")
async def update_plan(
    plan_name: str,
    body: UpdatePlanRequest,
    current_user: CurrentUser = Depends(require_superadmin()),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Updates a subscription plan's limits and pricing.
    Requires: superadmin only.
    """
    controller = AdminController(db)
    return await controller.update_plan(plan_name, body.model_dump(exclude_none=True))