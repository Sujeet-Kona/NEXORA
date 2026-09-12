from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.db.models import DocumentStatus


class DocumentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Document name cannot be empty")

        return value


class DocumentStatusUpdate(BaseModel):
    status: DocumentStatus


class DocumentResponse(BaseModel):
    id: int
    organization_id: int
    uploaded_by: int
    name: str
    storage_key: str | None
    file_size: int | None
    content_type: str | None
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
