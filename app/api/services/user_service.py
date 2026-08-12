"""User Service for business logic"""

from sqlalchemy.orm import Session
from typing import Optional, List
from fastapi import HTTPException, status

from app.api.repositories.user_repository import UserRepository
from app.api.schemas.user_schema import (
    UserResponse,
    UserCreateRequest,
    LoginRequest,
    LoginResponse
)
from app.core.security import hash_password, verify_password
from app.core.logger import get_logger

logger = get_logger(__name__)


class UserService:
    """Service for User business logic"""

    def __init__(self, db: Session):
        self.db = db
        self.repository = UserRepository(db)

    def create_user(self, request: UserCreateRequest) -> UserResponse:
        """
        Create a new user with hashed password.
        
        Validations:
        - Username must be unique
        - Email must be unique
        - Role must exist
        """
        # Validate username uniqueness
        if self.repository.check_username_exists(request.username):
            logger.warning(f"Duplicate username: {request.username}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{request.username}' already exists"
            )

        # Validate email uniqueness
        if self.repository.check_email_exists(request.email):
            logger.warning(f"Duplicate email: {request.email}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email '{request.email}' already exists"
            )

        # Validate role exists
        if not self.repository.check_role_exists(request.role_id):
            logger.warning(f"Role not found: {request.role_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role with ID {request.role_id} not found"
            )

        try:
            # Hash the password
            hashed_password = hash_password(request.password)

            # Create user data
            user_data = {
                "username": request.username,
                "email": request.email,
                "password": hashed_password,
                "role_id": request.role_id
            }

            # Create user
            user = self.repository.create_user(user_data)

            # Commit the transaction
            self.db.commit()

            logger.info(f"User created successfully: {user.user_id}")

            # Get user with role information
            user_with_role = self.repository.get_user_with_role(user.user_id)

            return UserResponse(
                user_id=user_with_role["user_id"],
                username=user_with_role["username"],
                email=user_with_role["email"],
                role_id=user_with_role["role_id"],
                role_name=user_with_role["role_name"],
                last_login=None
            )

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating user: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )

    def login(self, request: LoginRequest) -> LoginResponse:
        """
        Authenticate user and return user information.
        
        Validates username and password, updates last_login timestamp.
        """
        # Get user by username
        user = self.repository.get_user_by_username(request.username)

        if not user:
            logger.warning(f"Login failed - username not found: {request.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        # Verify password
        if not verify_password(request.password, user.password):
            logger.warning(f"Login failed - invalid password for username: {request.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        try:
            # Update last login timestamp
            self.repository.update_last_login(user.user_id)
            self.db.commit()

            # Get user with role information
            user_with_role = self.repository.get_user_with_role(user.user_id)

            logger.info(f"User logged in successfully: {user.user_id}")

            return LoginResponse(
                user_id=user_with_role["user_id"],
                username=user_with_role["username"],
                email=user_with_role["email"],
                role_id=user_with_role["role_id"],
                role_name=user_with_role["role_name"]
            )

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error during login: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Login failed"
            )

    def get_users(self, role_id: Optional[int] = None) -> List[UserResponse]:
        """
        Get list of users, optionally filtered by role_id.
        
        Args:
            role_id: Optional filter by specific role ID
        
        Returns:
            List of users with their role information
        """
        try:
            users_data = self.repository.get_users(role_id=role_id)
            
            result = [
                UserResponse(**user_data)
                for user_data in users_data
            ]
            
            logger.info(f"Retrieved {len(result)} users" + (f" with role_id {role_id}" if role_id else ""))
            return result
            
        except Exception as e:
            logger.error(f"Error getting users: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve users"
            )
