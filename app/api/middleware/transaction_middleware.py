"""
Transaction Middleware

Manages the database transaction lifecycle for every request:
- Opens a session at request start
- Commits on a successful response (2xx)
- Rolls back on error responses (4xx/5xx) or exceptions
- Always closes the session
"""

from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.logger import get_logger
import traceback

logger = get_logger(__name__)


class TransactionMiddleware(BaseHTTPMiddleware):
    """Manage one database transaction per request."""

    async def dispatch(self, request, call_next):
        db: Session = None
        try:
            db = SessionLocal()
            request.state.db = db
            logger.debug(f"Transaction START: {request.method} {request.url.path}")

            response = await call_next(request)

            if 200 <= response.status_code < 300:
                db.commit()
                logger.debug(
                    f"Transaction COMMIT: {request.method} {request.url.path} "
                    f"[{response.status_code}]"
                )
            else:
                db.rollback()
                logger.warning(
                    f"Transaction ROLLBACK: {request.method} {request.url.path} "
                    f"[{response.status_code}]"
                )
            return response
        except Exception as e:
            if db:
                db.rollback()
                logger.error(
                    f"Transaction ROLLBACK: {request.method} {request.url.path} "
                    f"- Exception: {str(e)}\n{traceback.format_exc()}"
                )
            raise
        finally:
            if db:
                db.close()
                logger.debug(f"Transaction END: {request.method} {request.url.path} - Session closed")
