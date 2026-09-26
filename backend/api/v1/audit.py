from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUser
from backend.dependencies.database import get_db
from backend.dependencies.pagination import Pagination
from backend.schemas.audit import AuditLogResponse
from backend.services.audit_service import (
    list_organization_audit_logs_service,
)


router = APIRouter(
    prefix="/organizations",
    tags=["audit"],
)


@router.get(
    "/{organization_id}/audit-logs",
    response_model=list[AuditLogResponse],
)
def list_audit_logs(
    organization_id: int,
    current_user: CurrentUser,
    pagination: Pagination,
    db: Session = Depends(get_db),
):
    return list_organization_audit_logs_service(
        db=db,
        organization_id=organization_id,
        acting_user=current_user,
        limit=pagination.limit,
        offset=pagination.offset,
    )
