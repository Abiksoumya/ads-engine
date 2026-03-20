"""
AdEngineAI — Auth Service
===========================
Business logic for authentication.
Calls UserDAO for DB operations, core/security for JWT.

Methods:
    register    → create user + assign default role + create free subscription
    login       → verify credentials + return tokens
    refresh     → exchange refresh token for new access token
    logout      → invalidate refresh token (blacklist in Redis)
    me          → get current user profile
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.core.exceptions import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidTokenException,
    ValidationException,
    UserNotFoundException,
)
from app.dao.user_dao import UserDAO
from app.dao.subscription_dao import SubscriptionDAO
from app.models.user import User, Role, UserRole, RoleEnum


logger = logging.getLogger(__name__)


class AuthService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_dao = UserDAO(db)
        self.subscription_dao = SubscriptionDAO(db)

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    async def register(
        self,
        email: str,
        password: str,
        full_name: str,
    ) -> dict:
        """
        Registers a new user.
        1. Validates input
        2. Checks email not already taken
        3. Hashes password
        4. Creates user
        5. Assigns USER role
        6. Creates FREE subscription
        7. Returns tokens

        Returns: {access_token, refresh_token, token_type, user}
        """
        # Validate password strength
        password_errors = validate_password_strength(password)
        if password_errors:
            raise ValidationException(
                "Password does not meet requirements",
                {"errors": password_errors},
            )

        # Check email uniqueness
        if await self.user_dao.exists_by_email(email):
            raise EmailAlreadyExistsException()

        # Create user
        hashed = hash_password(password)
        user = await self.user_dao.create(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
        )

        # Assign default role
        await self.user_dao.assign_role(UUID(str(user.id)), RoleEnum.USER)

        # Create free subscription
        await self.subscription_dao.create_free_subscription(UUID(str(user.id)))

        # Generate tokens
        tokens = self._generate_tokens(user, role="user", plan="free")

        logger.info(f"New user registered: {email}")

        return {
            "user": self._user_to_dict(user),
        }

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str) -> dict:
        user = await self.user_dao.get_by_email(email)
        if not user:
            raise InvalidCredentialsException()

        if not verify_password(password, str(user.hashed_password)):
            raise InvalidCredentialsException()

        if not bool(user.is_active):
            raise InvalidCredentialsException()

        await self.user_dao.update_last_login(UUID(str(user.id)))

        role = await self._get_primary_role(user)
        plan = await self._get_plan(user)
        tokens = self._generate_tokens(user, role=role, plan=plan)

        logger.info(f"User logged in: {email}")

        return {**tokens, }

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    async def refresh(self, refresh_token: str) -> dict:
        """
        Issues a new access token using a valid refresh token.
        Refresh token remains valid until it expires.
        """
        payload = decode_refresh_token(refresh_token)
        user_id_str = payload.get("sub")

        if not user_id_str:
            raise InvalidTokenException()

        user = await self.user_dao.get_by_id(UUID(user_id_str))
        if not user or not user.active:
            raise InvalidTokenException("User not found or inactive")

        role = await self._get_primary_role(user)
        plan = await self._get_plan(user)

        access_token = create_access_token(user.typed_id, role=role, plan=plan)

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    # ------------------------------------------------------------------
    # Get current user
    # ------------------------------------------------------------------

    async def get_current_user(self, user_id: UUID) -> dict:
        """Returns the current user's profile."""
        user = await self.user_dao.get_by_id(user_id)
        if not user:
            raise UserNotFoundException()

        role = await self._get_primary_role(user)
        plan = await self._get_plan(user)

        return {
            **self._user_to_dict(user),
            "role": role,
            "plan": plan,
        }

    # ------------------------------------------------------------------
    # Change password
    # ------------------------------------------------------------------

    async def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
    ) -> None:
        """Changes user password after verifying current password."""
        user = await self.user_dao.get_by_id(user_id)
        if not user:
            raise UserNotFoundException()

        if not verify_password(current_password, user.password_hash):
                raise InvalidCredentialsException()

        errors = validate_password_strength(new_password)
        if errors:
            raise ValidationException("New password too weak", {"errors": errors})

        hashed = hash_password(new_password)
        await self.user_dao.update_password(user_id, hashed)
        logger.info(f"Password changed for user: {user_id}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _generate_tokens(self, user: User, role: str, plan: str) -> dict:
        user_id = UUID(str(user.id))
        access_token = create_access_token(user_id, role=role, plan=plan)
        refresh_token = create_refresh_token(user_id)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 1800,
        }

    async def _get_primary_role(self, user: User) -> str:
        roles = await self.user_dao.get_user_roles(UUID(str(user.id)))
        priority = ["superadmin", "admin", "agency", "user", "viewer"]
        for role in priority:
            if role in roles:
                return role
        return "user"

      

    async def _get_plan(self, user: User) -> str:
        subscription = await self.subscription_dao.get_by_user_id(UUID(str(user.id)))
        if subscription and subscription.plan:
            return str(subscription.plan.name.value)
        return "free"

    @staticmethod
    def _user_to_dict(user: User) -> dict:
        created_at = user.created_at
        return {
            "id": str(user.id),
            "email": str(user.email),
            "full_name": str(user.full_name),
            "is_active": bool(user.is_active),
            "is_verified": bool(user.is_verified),
            "avatar_url": str(user.avatar_url) if user.avatar_url is not None else None,
            "created_at": created_at.isoformat() if created_at is not None else None,
        }