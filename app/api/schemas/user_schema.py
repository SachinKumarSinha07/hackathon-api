"""User Schemas for request/response validation"""

from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional
from datetime import datetime


class UserCreateRequest(BaseModel):
    """Schema for creating a new user"""
    username: str = Field(..., min_length=3, max_length=100, description="Username")
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=8, description="Password (minimum 8 characters)")
    role_id: int = Field(..., gt=0, description="Role ID")

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username"""
        if not v or not v.strip():
            raise ValueError("Username cannot be empty")
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "password": "SecurePassword123",
                "role_id": 2
            }
        }


class LoginRequest(BaseModel):
    """Schema for user login"""
    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Password")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "SecurePassword123"
            }
        }


class LoginResponse(BaseModel):
    """Schema for login response"""
    user_id: int
    username: str
    email: str
    role_id: int
    role_name: str

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "username": "john_doe",
                "email": "john@example.com",
                "role_id": 2,
                "role_name": "Developer"
            }
        }


class UserResponse(BaseModel):
    """Schema for user response"""
    user_id: int
    username: str
    email: str
    role_id: int
    role_name: str
    last_login: Optional[datetime]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "username": "john_doe",
                "email": "john@example.com",
                "role_id": 1,
                "role_name": "Admin",
                "last_login": "2026-08-12T10:00:00"
            }
        }
