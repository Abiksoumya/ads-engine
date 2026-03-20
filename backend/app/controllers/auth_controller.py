"""
AdEngineAI — Auth Controller
==============================
Handles HTTP request/response for auth endpoints.
Calls AuthService for business logic.
No business logic here — only request parsing and response formatting.
"""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.service.auth_service import AuthService


class AuthController:

    def __init__(self, db: AsyncSession):
        self.service = AuthService(db)

    async def register(self, body: dict) -> dict:
        result = await self.service.register(
            email=body["email"],
            password=body["password"],
            full_name=body["full_name"],
        )
        return {
            "success": True,
            "message": "Registration successful",
            "data": result,
        }

    async def login(self, body: dict, request: Request) -> dict:
        result = await self.service.login(
            email=body["email"],
            password=body["password"],
        )
        return {
            "success": True,
            "message": "Login successful",
            "data": result,
        }

    async def refresh(self, body: dict) -> dict:
        result = await self.service.refresh(
            refresh_token=body["refresh_token"],
        )
        return {
            "success": True,
            "data": result,
        }

    async def me(self, current_user: CurrentUser) -> dict:
        result = await self.service.get_current_user(current_user.user_id)
        return {
            "success": True,
            "data": result,
        }

    async def change_password(self, body: dict, current_user: CurrentUser) -> dict:
        await self.service.change_password(
            user_id=current_user.user_id,
            current_password=body["current_password"],
            new_password=body["new_password"],
        )
        return {
            "success": True,
            "message": "Password changed successfully",
        }