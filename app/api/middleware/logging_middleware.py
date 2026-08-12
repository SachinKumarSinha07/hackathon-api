"""
Logging Middleware

Logs incoming requests and outgoing responses with timing and a correlation ID.
"""

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logger import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log all HTTP requests and responses."""

    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())
        start_time = time.time()

        logger.info(
            f"Request started - ID: {request_id} - Method: {request.method} - "
            f"Path: {request.url.path} - Query: {dict(request.query_params)} - "
            f"Client: {request.client.host if request.client else 'unknown'}"
        )

        request.state.request_id = request_id

        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            logger.info(
                f"Request completed - ID: {request_id} - Status: {response.status_code} - "
                f"Duration: {process_time:.4f}s"
            )
            return response
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Request failed - ID: {request_id} - Error: {str(e)} - "
                f"Duration: {process_time:.4f}s",
                exc_info=True,
            )
            raise


class CORSLoggingMiddleware(BaseHTTPMiddleware):
    """Log CORS preflight requests (helpful during development)."""

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            logger.debug(
                f"CORS Preflight - Path: {request.url.path} - "
                f"Origin: {request.headers.get('origin', 'N/A')}"
            )
        return await call_next(request)
