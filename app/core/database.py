"""
Database Configuration and Session Management

Handles the database connection, session management, and base model setup.
Uses SQLAlchemy ORM with PostgreSQL.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator
from fastapi import Request
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

DATABASE_URL = settings.get_database_url()

logger.info(f"Database URL: {DATABASE_URL}")

# Create SQLAlchemy engine.
# pool_pre_ping keeps connections healthy across idle periods.
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for SQLAlchemy models
Base = declarative_base()


def get_db(request: Request = None) -> Generator[Session, None, None]:
    """
    Dependency that yields a database session.

    When TransactionMiddleware is active it reuses the session stored in
    request.state.db so every operation in a request shares one transaction.
    Otherwise it creates a new session (tests / middleware disabled).
    """
    if request and hasattr(request.state, "db"):
        logger.debug("Using database session from TransactionMiddleware")
        yield request.state.db
    else:
        db = SessionLocal()
        try:
            logger.debug("Creating new database session (no middleware)")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            logger.debug("Closing database session")
            db.close()


def init_db() -> None:
    """Create all tables defined by the SQLAlchemy models."""
    # Import models so they are registered on Base.metadata before create_all.
    from app.api import models  # noqa: F401

    try:
        logger.info("Initializing database...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise


def drop_db() -> None:
    """Drop all database tables. Use with caution."""
    try:
        logger.warning("Dropping all database tables...")
        Base.metadata.drop_all(bind=engine)
        logger.warning("All database tables dropped")
    except Exception as e:
        logger.error(f"Failed to drop database: {str(e)}")
        raise


def shutdown_db() -> None:
    """Dispose of the engine and close all pooled connections."""
    try:
        logger.info("Shutting down database connections...")
        engine.dispose()
        logger.info("Database engine disposed successfully")
    except Exception as e:
        logger.error(f"Error during database shutdown: {str(e)}")
        raise
