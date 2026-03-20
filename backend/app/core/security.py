"""
AdEngineAI — Core Security
============================
Password hashing and JWT token management.

Two token types:
    access_token  — short-lived (30 min), used for API requests
    refresh_token — long-lived (30 days), used to get new access tokens

Never store plain passwords. Never log tokens.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import InvalidTokenException

# Password hashing context — bcrypt with configurable rounds
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(plain_password: str) -> str:
    """Hashes a plain text password using bcrypt."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_strength(password: str) -> list[str]:
    """
    Validates password strength.
    Returns list of error messages — empty list means password is valid.
    """
    errors: list[str] = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters")
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one number")

    return errors


# ---------------------------------------------------------------------------
# JWT token management
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: UUID,
    role: str,
    plan: str,
) -> str:
    """
    Creates a short-lived JWT access token.
    Expires in ACCESS_TOKEN_EXPIRE_MINUTES (default 30 min).
    """
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "plan": plan,
        "type": "access",
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """
    Creates a long-lived JWT refresh token.
    Expires in REFRESH_TOKEN_EXPIRE_DAYS (default 30 days).
    """
    expires = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decodes and validates a JWT token.
    Raises InvalidTokenException if token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        raise InvalidTokenException(f"Token validation failed: {str(e)}")


def decode_access_token(token: str) -> dict:
    """
    Decodes an access token and validates it's the correct type.
    Returns payload with user_id, role, plan.
    """
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise InvalidTokenException("Invalid token type — access token required")
    return payload


def decode_refresh_token(token: str) -> dict:
    """
    Decodes a refresh token and validates it's the correct type.
    Returns payload with user_id.
    """
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise InvalidTokenException("Invalid token type — refresh token required")
    return payload


def get_user_id_from_token(token: str) -> UUID:
    """Extracts user_id from a valid access token."""
    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise InvalidTokenException("Token missing user ID")
    try:
        return UUID(user_id_str)
    except ValueError:
        raise InvalidTokenException("Invalid user ID in token")