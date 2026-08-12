"""
FastAPI Application Entry Point

Initializes and configures the FastAPI application with middleware,
exception handlers, and routers.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db, shutdown_db
from app.core.logger import setup_logging, get_logger
from app.api.middleware import (
    LoggingMiddleware,
    CORSLoggingMiddleware,
    TransactionMiddleware,
    LocaleMiddleware,
    APIException,
    http_exception_handler,
    validation_exception_handler,
    sqlalchemy_exception_handler,
    api_exception_handler,
    general_exception_handler,
)
from app.api.controllers import health_router, project_router, user_router

# Setup logging first
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    logger.info("=" * 60)
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info("=" * 60)

    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {str(e)}")
        raise

    yield

    logger.info("Shutting down application")
    try:
        shutdown_db()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error during database shutdown: {str(e)}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    FastAPI backend scaffold with:
    * SQLAlchemy ORM + PostgreSQL
    * Controller-Service-Repository pattern
    * Centralized error handling
    * Request/response logging
    * Per-request DB transactions
    * i18n (en/ja) support
    * OpenAPI/Swagger docs
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Custom middleware (added last executes first)
app.add_middleware(LocaleMiddleware)
app.add_middleware(TransactionMiddleware)
app.add_middleware(CORSLoggingMiddleware)
app.add_middleware(LoggingMiddleware)

# Exception handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(APIException, api_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Routers
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(project_router, prefix=settings.api_prefix)
app.include_router(user_router, prefix=settings.api_prefix)


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": f"{settings.api_prefix}/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level=settings.log_level.lower())
