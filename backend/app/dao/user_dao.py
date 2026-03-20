"""
AdEngineAI — User DAO
=======================
All user-related database queries.
No business logic here — only DB operations.

Called by: UserService, AuthService
"""

import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, Role, UserRole, RoleEnum
from app.core.exceptions import DatabaseException

logger = logging.getLogger(__name__)


class UserDAO:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Gets user by ID with roles and subscription loaded."""
        try:
            result = await self.db.execute(
                select(User)
                .options(
                    selectinload(User.user_roles).selectinload(UserRole.role),
                    selectinload(User.subscription),
                )
                .where(User.id == user_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get_by_id failed: {e}")
            raise DatabaseException()

    async def get_by_email(self, email: str) -> User | None:
        """Gets user by email. Used for login and duplicate check."""
        try:
            result = await self.db.execute(
                select(User)
                .options(
                    selectinload(User.user_roles).selectinload(UserRole.role),
                    selectinload(User.subscription),
                )
                .where(User.email == email.lower().strip())
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get_by_email failed: {e}")
            raise DatabaseException()

    async def exists_by_email(self, email: str) -> bool:
        """Checks if email is already registered."""
        try:
            result = await self.db.execute(
                select(User.id).where(User.email == email.lower().strip())
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"exists_by_email failed: {e}")
            raise DatabaseException()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 50,
        is_active: bool | None = None,
    ) -> list[User]:
        """Gets paginated list of users. Admin only."""
        try:
            query = select(User).offset(skip).limit(limit)
            if is_active is not None:
                query = query.where(User.is_active == is_active)
            result = await self.db.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"get_all failed: {e}")
            raise DatabaseException()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(
        self,
        email: str,
        hashed_password: str,
        full_name: str,
    ) -> User:
        """Creates a new user. Does NOT assign role — do that separately."""
        try:
            user = User(
                email=email.lower().strip(),
                hashed_password=hashed_password,
                full_name=full_name.strip(),
            )
            self.db.add(user)
            await self.db.flush()   # get the ID without committing
            return user
        except Exception as e:
            logger.error(f"create user failed: {e}")
            raise DatabaseException()

    async def update_last_login(self, user_id: UUID) -> None:
        """Updates last_login_at timestamp."""
        from datetime import datetime, timezone
        try:
            await self.db.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_login_at=datetime.now(timezone.utc))
            )
        except Exception as e:
            logger.error(f"update_last_login failed: {e}")
            raise DatabaseException()

    async def update_profile(
        self,
        user_id: UUID,
        full_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User | None:
        """Updates user profile fields."""
        try:
            values: dict = {}
            if full_name is not None:
                values["full_name"] = full_name.strip()
            if avatar_url is not None:
                values["avatar_url"] = avatar_url

            if values:
                await self.db.execute(
                    update(User).where(User.id == user_id).values(**values)
                )

            return await self.get_by_id(user_id)
        except Exception as e:
            logger.error(f"update_profile failed: {e}")
            raise DatabaseException()

    async def update_password(self, user_id: UUID, hashed_password: str) -> None:
        """Updates hashed password."""
        try:
            await self.db.execute(
                update(User)
                .where(User.id == user_id)
                .values(hashed_password=hashed_password)
            )
        except Exception as e:
            logger.error(f"update_password failed: {e}")
            raise DatabaseException()

    async def deactivate(self, user_id: UUID) -> None:
        """Soft deletes a user by setting is_active=False."""
        try:
            await self.db.execute(
                update(User).where(User.id == user_id).values(is_active=False)
            )
        except Exception as e:
            logger.error(f"deactivate failed: {e}")
            raise DatabaseException()

    async def update_stripe_customer_id(
        self, user_id: UUID, stripe_customer_id: str
    ) -> None:
        """Stores Stripe customer ID after first payment setup."""
        try:
            await self.db.execute(
                update(User)
                .where(User.id == user_id)
                .values(stripe_customer_id=stripe_customer_id)
            )
        except Exception as e:
            logger.error(f"update_stripe_customer_id failed: {e}")
            raise DatabaseException()

    # ------------------------------------------------------------------
    # Role management
    # ------------------------------------------------------------------

    async def assign_role(
        self,
        user_id: UUID,
        role_name: RoleEnum,
        assigned_by: UUID | None = None,
    ) -> None:
        """Assigns a role to a user."""
        try:
            # Get role ID
            role_result = await self.db.execute(
                select(Role).where(Role.name == role_name)
            )
            role = role_result.scalar_one_or_none()
            if not role:
                raise DatabaseException(f"Role '{role_name}' not found")

            # Check if already assigned
            existing = await self.db.execute(
                select(UserRole).where(
                    UserRole.user_id == user_id,
                    UserRole.role_id == role.id,
                )
            )
            if existing.scalar_one_or_none():
                return  # already has this role

            user_role = UserRole(
                user_id=user_id,
                role_id=role.id,
                assigned_by=assigned_by,
            )
            self.db.add(user_role)
            await self.db.flush()
        except DatabaseException:
            raise
        except Exception as e:
            logger.error(f"assign_role failed: {e}")
            raise DatabaseException()

    async def get_user_roles(self, user_id: UUID) -> list[str]:
        """Returns list of role names for a user."""
        try:
            result = await self.db.execute(
                select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
            )
            return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"get_user_roles failed: {e}")
            raise DatabaseException()