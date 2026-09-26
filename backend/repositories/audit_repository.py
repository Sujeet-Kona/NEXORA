from sqlalchemy.orm import Session

from backend.db.models import AuditAction, AuditLog


def create_audit_log(
    db: Session,
    *,
    organization_id: int | None,
    actor_user_id: int | None,
    action: AuditAction,
    resource_type: str | None = None,
    resource_id: int | None = None,
    request_id: str | None = None,
    success: bool = True,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        success=success,
        details=details,
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry


def list_audit_logs_for_organization(
    db: Session,
    *,
    organization_id: int,
    limit: int,
    offset: int,
) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(
            AuditLog.organization_id == organization_id,
        )
        .order_by(
            AuditLog.created_at.desc(),
            AuditLog.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
