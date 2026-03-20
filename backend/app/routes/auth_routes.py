"""
AdEngineAI — Auth Routes
==========================
All authentication endpoints.

POST /api/auth/register    → create account
POST /api/auth/login       → get tokens
POST /api/auth/refresh     → refresh access token
GET  /api/auth/me          → get current user
PUT  /api/auth/password    → change password
POST /api/auth/logout      → logout (client-side token deletion)
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import AuthController
from app.core.dependencies import (
    get_current_user,
    get_db_session,
    auth_rate_limit,
    CurrentUser,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    full_name: str = Field(min_length=2, max_length=255)

    @field_validator("full_name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name cannot be empty")
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=100)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=100)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    is_verified: bool
    avatar_url: str | None
    created_at: str | None


class RegisterResponse(BaseModel):
    success: bool
    message: str
    data: dict


class LoginResponse(BaseModel):
    success: bool
    message: str
    data: dict


class MeResponse(BaseModel):
    success: bool
    data: dict


class SuccessResponse(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=201,
    summary="Create a new account",
)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Creates a new user account.

    - Validates password strength (8+ chars, upper, lower, number)
    - Checks email is not already registered
    - Creates user with FREE subscription
    - Returns JWT access + refresh tokens
    """
    controller = AuthController(db)
    return await controller.register(body.model_dump())


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login with email and password",
)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Authenticates user and returns JWT tokens.

    - Rate limited to 10 requests/minute per IP
    - Returns access token (30 min) + refresh token (30 days)
    - Same error message for wrong email or wrong password (security)
    """
    controller = AuthController(db)
    return await controller.login(body.model_dump(), request)


@router.post(
    "/refresh",
    response_model=dict,
    summary="Refresh access token",
)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Issues a new access token using a valid refresh token.
    Call this when the access token expires.
    """
    controller = AuthController(db)
    return await controller.refresh(body.model_dump())


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current user profile",
)
async def me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Returns the authenticated user's profile, role, and plan.
    Requires: valid access token in Authorization header.
    """
    controller = AuthController(db)
    return await controller.me(current_user)


@router.put(
    "/password",
    response_model=SuccessResponse,
    summary="Change password",
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Changes the authenticated user's password.
    Requires current password for verification.
    """
    controller = AuthController(db)
    return await controller.change_password(body.model_dump(), current_user)


@router.post(
    "/logout",
    response_model=SuccessResponse,
    summary="Logout",
)
async def logout(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Logs out the user.
    Tokens are stateless JWTs — client must delete them locally.
    Future: add token blacklist in Redis for immediate invalidation.
    """
    return {
        "success": True,
        "message": "Logged out successfully — please delete your tokens",
    }