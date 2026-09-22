from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from backend.db.models import UserRole


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdate(BaseModel):
    role: UserRole
