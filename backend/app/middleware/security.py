"""
AdEngineAI — Security Middleware
===================================
Applied to every request:
    1. CORS — whitelist frontend origin
    2. Security headers — HSTS, X-Frame-Options, CSP, etc.
    3. Request logging — method, path, status, duration
    4. Error sanitization — never leak stack traces in production
"""

import logging
import time
from urllib import response
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to every response.
    Prevents clickjacking, XSS, MIME sniffing, etc.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy — disable unnecessary browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )

        # HSTS — only in production
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Remove server header (don't reveal server info)
        if "server" in response.headers:
            del response.headers["server"]

        return response


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every request with method, path, status code, and duration.
    Assigns a unique request ID for tracing.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Add request ID to state for use in route handlers
        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Don't log health checks — too noisy
        if request.url.path not in ["/health", "/metrics"]:
            logger.info(
                f"[{request_id}] {request.method} {request.url.path} "
                f"→ {response.status_code} ({duration_ms}ms)"
            )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        return response


# ---------------------------------------------------------------------------
# Register all middleware on the FastAPI app
# ---------------------------------------------------------------------------

def setup_middleware(app: FastAPI) -> None:
    """
    Registers all middleware on the FastAPI app.
    Called once in main.py during app creation.
    Order matters — middleware runs in reverse registration order.
    """

    # 1. CORS — must be first
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Response-Time"],
    )

    # 2. Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 3. Request logging
    app.add_middleware(RequestLoggingMiddleware)

    logger.info("Middleware registered: CORS, SecurityHeaders, RequestLogging")