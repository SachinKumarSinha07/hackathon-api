"""
Error Handler Middleware

Centralized exception handling. Formats exceptions into consistent API responses.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional
from app.core.logger import get_logger
from app.core.i18n import translate

logger = get_logger(__name__)


class APIException(Exception):
    """Custom API exception carrying an HTTP status code and message."""

    def __init__(self, status_code: int, detail: str, headers: Optional[dict] = None):
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
        super().__init__(detail)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle Starlette/FastAPI HTTP exceptions."""
    logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail} - Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "path": str(request.url.path),
            },
        },
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request body/query validation errors."""
    logger.warning(f"Validation Error: {exc.errors()} - Path: {request.url.path}")

    serializable_errors = []
    for error in exc.errors():
        error_dict = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
        }
        input_val = error.get("input")
        if isinstance(input_val, (str, int, float, bool, list, dict, type(None))):
            error_dict["input"] = input_val
        else:
            error_dict["input"] = str(input_val)
        if "ctx" in error:
            ctx = error["ctx"]
            if isinstance(ctx, dict):
                error_dict["ctx"] = {
                    k: v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
                    for k, v in ctx.items()
                }
            else:
                error_dict["ctx"] = str(ctx)
        serializable_errors.append(error_dict)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "message": translate("error.validation_error"),
                "details": serializable_errors,
                "path": str(request.url.path),
            },
        },
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle database errors."""
    logger.error(f"Database Error: {str(exc)} - Path: {request.url.path}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": translate("error.database_error"),
                "path": str(request.url.path),
            },
        },
    )


async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    """Handle custom API exceptions."""
    logger.error(f"API Exception: {exc.status_code} - {exc.detail} - Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "path": str(request.url.path),
            },
        },
        headers=exc.headers,
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions."""
    logger.critical(f"Unhandled Exception: {str(exc)} - Path: {request.url.path}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": translate("error.internal_server_error"),
                "path": str(request.url.path),
            },
        },
    )
