from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.db.models import OrganizationRole


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Organization name cannot be empty")

        return value


class OrganizationResponse(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationMemberCreate(BaseModel):
    user_id: int = Field(gt=0)
    role: OrganizationRole


class OrganizationMemberResponse(BaseModel):
    id: int
    organization_id: int
    user_id: int
    role: OrganizationRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationMemberRoleUpdate(BaseModel):
    role: OrganizationRole
