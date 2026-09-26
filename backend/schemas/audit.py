from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.db.models import AuditAction


class AuditLogResponse(BaseModel):
    id: int
    organization_id: int | None
    actor_user_id: int | None
    action: AuditAction
    resource_type: str | None
    resource_id: int | None
    request_id: str | None
    success: bool
    details: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
