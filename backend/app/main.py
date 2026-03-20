"""
AdEngineAI — FastAPI Application
====================================
Main entry point for the entire backend.

Startup:
    uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

This file:
    1. Creates FastAPI app
    2. Registers middleware (CORS, security headers, logging)
    3. Registers exception handlers
    4. Registers all routers
    5. Handles startup/shutdown lifecycle
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppException
from app.db.database import check_connection, create_tables
from app.middleware.security import setup_middleware
from app.routes.auth_routes import router as auth_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""

    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Check database connection
    db_ok = await check_connection()
    if not db_ok:
        logger.error("Database connection failed — check DATABASE_URL in .env")
    else:
        logger.info("Database connected")

    # Create tables in development (use Alembic in production)
    if settings.is_development:
        await create_tables()
        logger.info("Database tables synced")

    logger.info(f"AdEngineAI ready on port {settings.SIDECAR_PORT}")

    yield

    # Shutdown
    logger.info("AdEngineAI shutting down...")


# ---------------------------------------------------------------------------
# Create app
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered video ad generation platform",
    docs_url="/docs" if settings.is_development else None,    # hide docs in prod
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# Register middleware
setup_middleware(app)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Converts all AppExceptions to clean JSON responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches any unhandled exception — never leaks stack traces."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # In development show the actual error, in production hide it
    message = str(exc) if settings.is_development else "An unexpected error occurred"

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": message,
                "details": {},
            },
        },
    )


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)

# Future routers — add as we build each module
# app.include_router(user_router)
# app.include_router(campaign_router)
# app.include_router(brand_router)
# app.include_router(subscription_router)
# app.include_router(publish_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint — used by load balancers and monitoring."""
    db_ok = await check_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": "connected" if db_ok else "disconnected",
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.is_development else "disabled",
    }