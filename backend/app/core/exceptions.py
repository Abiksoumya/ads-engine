"""
AdEngineAI — Custom Exceptions
================================
All application exceptions defined here.
Never raise generic Exception — always use these.

Each exception maps to an HTTP status code.
FastAPI exception handlers in main.py convert these to JSON responses.

Usage:
    from app.core.exceptions import NotFoundException
    raise NotFoundException("Campaign not found")
"""

from typing import Optional


class AppException(Exception):
    """Base exception for all AdEngineAI errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[dict] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


# ─── 400 Bad Request ────────────────────────────────────────────────────────

class ValidationException(AppException):
    """Invalid input data."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, 400, "VALIDATION_ERROR", details)


class BadRequestException(AppException):
    """Generic bad request."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, 400, "BAD_REQUEST", details)


# ─── 401 Unauthorized ───────────────────────────────────────────────────────

class UnauthorizedException(AppException):
    """Missing or invalid authentication."""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, 401, "UNAUTHORIZED")


class InvalidTokenException(AppException):
    """JWT token is invalid or expired."""
    def __init__(self, message: str = "Token is invalid or expired"):
        super().__init__(message, 401, "INVALID_TOKEN")


class InvalidCredentialsException(AppException):
    """Wrong email or password."""
    def __init__(self):
        super().__init__("Invalid email or password", 401, "INVALID_CREDENTIALS")


# ─── 403 Forbidden ──────────────────────────────────────────────────────────

class ForbiddenException(AppException):
    """Authenticated but not authorized for this action."""
    def __init__(self, message: str = "You don't have permission to do this"):
        super().__init__(message, 403, "FORBIDDEN")


class InsufficientRoleException(AppException):
    """User's role doesn't have access to this endpoint."""
    def __init__(self, required_role: str):
        super().__init__(
            f"This action requires '{required_role}' role or higher",
            403,
            "INSUFFICIENT_ROLE",
            {"required_role": required_role},
        )


class SubscriptionRequiredException(AppException):
    """Feature requires a paid subscription."""
    def __init__(self, required_plan: str = "starter"):
        super().__init__(
            f"This feature requires the '{required_plan}' plan or higher",
            403,
            "SUBSCRIPTION_REQUIRED",
            {"required_plan": required_plan},
        )


# ─── 404 Not Found ──────────────────────────────────────────────────────────

class NotFoundException(AppException):
    """Resource not found."""
    def __init__(self, resource: str = "Resource"):
        super().__init__(f"{resource} not found", 404, "NOT_FOUND")


class UserNotFoundException(AppException):
    def __init__(self):
        super().__init__("User not found", 404, "USER_NOT_FOUND")


class CampaignNotFoundException(AppException):
    def __init__(self):
        super().__init__("Campaign not found", 404, "CAMPAIGN_NOT_FOUND")


class BrandNotFoundException(AppException):
    def __init__(self):
        super().__init__("Brand not found", 404, "BRAND_NOT_FOUND")


# ─── 409 Conflict ───────────────────────────────────────────────────────────

class ConflictException(AppException):
    """Resource already exists."""
    def __init__(self, message: str):
        super().__init__(message, 409, "CONFLICT")


class EmailAlreadyExistsException(AppException):
    def __init__(self):
        super().__init__(
            "An account with this email already exists",
            409,
            "EMAIL_EXISTS",
        )


# ─── 422 Unprocessable Entity ───────────────────────────────────────────────

class UnprocessableException(AppException):
    """Request understood but cannot be processed."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, 422, "UNPROCESSABLE", details)


# ─── 429 Too Many Requests ──────────────────────────────────────────────────

class RateLimitException(AppException):
    """Too many requests."""
    def __init__(self, retry_after: int = 60):
        super().__init__(
            "Too many requests. Please slow down.",
            429,
            "RATE_LIMITED",
            {"retry_after_seconds": retry_after},
        )


# ─── 500 Internal Server Error ──────────────────────────────────────────────

class InternalException(AppException):
    """Unexpected server error."""
    def __init__(self, message: str = "An unexpected error occurred"):
        super().__init__(message, 500, "INTERNAL_ERROR")


class AgentException(AppException):
    """AI agent pipeline failed."""
    def __init__(self, agent: str, message: str):
        super().__init__(
            f"{agent} agent failed: {message}",
            500,
            "AGENT_ERROR",
            {"agent": agent},
        )


class DatabaseException(AppException):
    """Database operation failed."""
    def __init__(self, message: str = "Database error occurred"):
        super().__init__(message, 500, "DATABASE_ERROR")