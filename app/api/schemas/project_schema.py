"""Project Schemas for request/response validation"""

from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional, List
from datetime import datetime


class ProjectMemberInput(BaseModel):
    """Schema for project member input"""
    user_id: int = Field(..., gt=0, description="User ID")
    role_id: int = Field(..., gt=0, description="Role ID")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "role_id": 2
            }
        }


class ProjectCreateRequest(BaseModel):
    """Schema for creating a new project"""
    project_name: str = Field(..., min_length=1, max_length=150, description="Project name")
    project_description: Optional[str] = Field(None, description="Project description")
    project_type: str = Field(..., min_length=1, max_length=20, description="Project type (e.g., web, mobile, api)")
    environment: Optional[str] = Field(None, min_length=1, max_length=20, description="Environment (e.g., dev, staging, production)")
    project_url: Optional[str] = Field(None, max_length=500, description="Project URL")
    members: List[ProjectMemberInput] = Field(..., min_length=1, description="Project members with roles")

    @field_validator('project_name')
    @classmethod
    def validate_project_name(cls, v: str) -> str:
        """Validate project name"""
        if not v or not v.strip():
            raise ValueError("Project name cannot be empty")
        return v.strip()

    @field_validator('members')
    @classmethod
    def validate_members(cls, v: List[ProjectMemberInput]) -> List[ProjectMemberInput]:
        """Validate no duplicate users in members list"""
        user_ids = [member.user_id for member in v]
        if len(user_ids) != len(set(user_ids)):
            raise ValueError("Duplicate users found in members list")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "project_name": "E-Commerce Platform",
                "project_description": "Main e-commerce application",
                "project_type": "web",
                "environment": "production",
                "project_url": "https://example.com",
                "members": [
                    {"user_id": 1, "role_id": 1},
                    {"user_id": 2, "role_id": 2}
                ]
            }
        }


class ProjectUpdateRequest(BaseModel):
    """Schema for updating a project"""
    project_name: Optional[str] = Field(None, min_length=1, max_length=150, description="Project name")
    project_description: Optional[str] = Field(None, description="Project description")
    project_type: Optional[str] = Field(None, min_length=1, max_length=20, description="Project type")
    environment: Optional[str] = Field(None, min_length=1, max_length=20, description="Environment")
    project_url: Optional[str] = Field(None, max_length=500, description="Project URL")
    members: Optional[List[ProjectMemberInput]] = Field(None, min_length=1, description="Project members with roles")

    @field_validator('project_name')
    @classmethod
    def validate_project_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate project name"""
        if v is not None and (not v or not v.strip()):
            raise ValueError("Project name cannot be empty")
        return v.strip() if v else None

    @field_validator('project_type')
    @classmethod
    def validate_project_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate project type"""
        if v is not None:
            allowed_types = ['web', 'mobile', 'api', 'desktop', 'embedded', 'other']
            if v.lower() not in allowed_types:
                raise ValueError(f"Project type must be one of: {', '.join(allowed_types)}")
            return v.lower()
        return None

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: Optional[str]) -> Optional[str]:
        """Validate environment"""
        if v is not None:
            allowed_envs = ['dev', 'development', 'staging', 'uat', 'production', 'prod']
            if v.lower() not in allowed_envs:
                raise ValueError(f"Environment must be one of: {', '.join(allowed_envs)}")
            return v.lower()
        return None

    @field_validator('members')
    @classmethod
    def validate_members(cls, v: Optional[List[ProjectMemberInput]]) -> Optional[List[ProjectMemberInput]]:
        """Validate no duplicate users in members list"""
        if v is not None:
            user_ids = [member.user_id for member in v]
            if len(user_ids) != len(set(user_ids)):
                raise ValueError("Duplicate users found in members list")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "project_name": "Updated Project Name",
                "project_description": "Updated description",
                "project_type": "web",
                "environment": "production",
                "project_url": "https://updated-example.com",
                "members": [
                    {"user_id": 1, "role_id": 1},
                    {"user_id": 3, "role_id": 2}
                ]
            }
        }


class ProjectMemberResponse(BaseModel):
    """Schema for project member response"""
    user_id: int
    username: str
    email: str
    role_id: int
    role_name: str

    class Config:
        from_attributes = True


class ProjectResponse(BaseModel):
    """Schema for project response"""
    project_id: int
    project_name: str
    project_description: Optional[str]
    project_type: str
    environment: str
    project_url: Optional[str]
    members: List[ProjectMemberResponse] = []

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "project_id": 1,
                "project_name": "E-Commerce Platform",
                "project_description": "Main e-commerce application",
                "project_type": "web",
                "environment": "production",
                "project_url": "https://example.com",
                "members": [
                    {
                        "user_id": 1,
                        "username": "john_doe",
                        "email": "john@example.com",
                        "role_id": 1,
                        "role_name": "Admin"
                    }
                ]
            }
        }


class VulnerabilityStats(BaseModel):
    """Schema for vulnerability statistics by severity"""
    critical: int = Field(0, description="Count of critical severity vulnerabilities")
    high: int = Field(0, description="Count of high severity vulnerabilities")
    medium: int = Field(0, description="Count of medium severity vulnerabilities")
    low: int = Field(0, description="Count of low severity vulnerabilities")
    info: int = Field(0, description="Count of info/informational severity vulnerabilities")
    total: int = Field(0, description="Total count of open vulnerabilities")

    class Config:
        json_schema_extra = {
            "example": {
                "critical": 2,
                "high": 5,
                "medium": 10,
                "low": 8,
                "info": 3,
                "total": 28
            }
        }


class ProjectWithStatsResponse(BaseModel):
    """Schema for project with vulnerability statistics"""
    project_id: int
    project_name: str
    project_description: Optional[str]
    project_type: str
    environment: Optional[str]
    project_url: Optional[str]
    vulnerability_stats: VulnerabilityStats

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "project_id": 1,
                "project_name": "E-Commerce Platform",
                "project_description": "Main e-commerce application",
                "project_type": "web",
                "environment": "production",
                "project_url": "https://example.com",
                "vulnerability_stats": {
                    "critical": 2,
                    "high": 5,
                    "medium": 10,
                    "low": 8,
                    "info": 3,
                    "total": 28
                }
            }
        }
