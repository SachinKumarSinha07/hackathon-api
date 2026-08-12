"""Role Master Model"""

from sqlalchemy import Column, Integer, String
from app.core.database import Base


class RoleMaster(Base):
    """Role Master table model"""

    __tablename__ = "role_master"

    role_id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(50), nullable=False)

    def __repr__(self):
        return f"<RoleMaster(role_id={self.role_id}, role_name='{self.role_name}')>"
