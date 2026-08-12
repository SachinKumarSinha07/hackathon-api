"""User Controller - API endpoints for user management"""

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.api.schemas.user_schema import (
    UserResponse,
    UserCreateRequest,
    LoginRequest,
    LoginResponse
)
from app.api.services.user_service import UserService
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="""
    Create a new user account with a hashed password.
    
    **Validations:**
    - Username must be unique (3-100 characters, alphanumeric with underscores/hyphens)
    - Email must be unique and valid
    - Password must be at least 8 characters
    - Role ID must exist in the database
    
    **Password Security:**
    - Passwords are hashed using bcrypt before storage
    - Plain text passwords are never stored in the database
    
    **Required fields:**
    - username: Unique username
    - email: Valid email address
    - password: Secure password (min 8 characters)
    - role_id: Valid role ID
    """
)
def register_user(
    request: UserCreateRequest,
    db: Session = Depends(get_db)
):
    """Register a new user"""
    logger.info(f"Registering new user: {request.username}")
    service = UserService(db)
    return service.create_user(request)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="User login",
    description="""
    Authenticate user with username and password.
    
    **Response includes:**
    - user_id: User's unique identifier
    - username: User's username
    - email: User's email address
    - role_id: User's role ID
    - role_name: User's role name
    
    **Behavior:**
    - Validates username and password
    - Updates last_login timestamp on successful login
    - Returns 401 Unauthorized if credentials are invalid
    """
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """User login - authenticate and return user information"""
    logger.info(f"Login attempt for username: {request.username}")
    service = UserService(db)
    return service.login(request)


@router.get(
    "/",
    response_model=List[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Get list of users",
    description="""
    Get a list of users with their role information.
    
    **Filter:**
    - `role_id`: Optional - Filter by specific role ID. If null, all users are returned.
    
    **Response includes:**
    - user_id: User's unique identifier
    - username: User's username
    - email: User's email address
    - role_id: User's role ID
    - role_name: User's role name
    - last_login: User's last login timestamp (nullable)
    """
)
def get_users(
    role_id: Optional[int] = Query(None, description="Filter by specific role ID", gt=0),
    db: Session = Depends(get_db)
):
    """Get list of users, optionally filtered by role_id"""
    logger.info(f"Fetching users" + (f" with role_id: {role_id}" if role_id else ""))
    service = UserService(db)
    return service.get_users(role_id=role_id)
