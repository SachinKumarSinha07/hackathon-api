"""User Master Model"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class UserMaster(Base):
    """User Master table model"""

    __tablename__ = "user_master"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("role_master.role_id"), nullable=False)

    last_login = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=datetime.utcnow)

    # Relationships
    role = relationship("RoleMaster", backref="users")

    def __repr__(self):
        return f"<UserMaster(user_id={self.user_id}, username='{self.username}', email='{self.email}')>"
