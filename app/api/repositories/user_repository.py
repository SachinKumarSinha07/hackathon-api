"""User Repository for database operations"""

from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.api.models.user_master import UserMaster
from app.api.models.role_master import RoleMaster
from app.core.logger import get_logger

logger = get_logger(__name__)


class UserRepository:
    """Repository for User database operations"""

    def __init__(self, db: Session):
        self.db = db

    def check_username_exists(self, username: str) -> bool:
        """Check if a username already exists"""
        return self.db.query(UserMaster).filter(UserMaster.username == username).first() is not None

    def check_email_exists(self, email: str) -> bool:
        """Check if an email already exists"""
        return self.db.query(UserMaster).filter(UserMaster.email == email).first() is not None

    def check_role_exists(self, role_id: int) -> bool:
        """Check if a role exists"""
        return self.db.query(RoleMaster).filter(RoleMaster.role_id == role_id).first() is not None

    def create_user(self, user_data: Dict[str, Any]) -> UserMaster:
        """Create a new user"""
        user = UserMaster(**user_data)
        self.db.add(user)
        self.db.flush()
        logger.info(f"Created user: {user.user_id} - {user.username}")
        return user

    def get_user_by_username(self, username: str) -> Optional[UserMaster]:
        """Get a user by username"""
        return self.db.query(UserMaster).filter(UserMaster.username == username).first()

    def get_user_by_role(self, role_id: int) -> Optional[UserMaster]:
        """Get the first user assigned a specific global role (e.g. 7 for CTO)."""
        return self.db.query(UserMaster).filter(UserMaster.role_id == role_id).first()

    def get_user_with_role(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a user with role information"""
        result = self.db.query(
            UserMaster.user_id,
            UserMaster.username,
            UserMaster.email,
            UserMaster.role_id,
            RoleMaster.role_name
        ).join(
            RoleMaster, UserMaster.role_id == RoleMaster.role_id
        ).filter(
            UserMaster.user_id == user_id
        ).first()

        if not result:
            return None

        return {
            "user_id": result.user_id,
            "username": result.username,
            "email": result.email,
            "role_id": result.role_id,
            "role_name": result.role_name
        }

    def update_last_login(self, user_id: int) -> None:
        """Update user's last login timestamp"""
        user = self.db.query(UserMaster).filter(UserMaster.user_id == user_id).first()
        if user:
            user.last_login = datetime.utcnow()
            self.db.flush()
            logger.info(f"Updated last login for user: {user_id}")

    def get_users(self, role_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get users with their role information.
        
        Args:
            role_id: Optional filter by specific role ID
        
        Returns:
            List of users with role details
        """
        query = self.db.query(
            UserMaster.user_id,
            UserMaster.username,
            UserMaster.email,
            UserMaster.role_id,
            RoleMaster.role_name,
            UserMaster.last_login
        ).join(
            RoleMaster, UserMaster.role_id == RoleMaster.role_id
        )
        
        # Apply role filter if provided
        if role_id is not None:
            query = query.filter(UserMaster.role_id == role_id)
        
        users = query.all()
        
        result = [
            {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "role_id": user.role_id,
                "role_name": user.role_name,
                "last_login": user.last_login
            }
            for user in users
        ]
        
        logger.info(f"Retrieved {len(result)} users" + (f" with role_id {role_id}" if role_id else ""))
        return result
