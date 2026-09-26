import logging

from sqlalchemy.orm import Session

from backend.core.exceptions import (
    OrganizationAccessDeniedError,
    OrganizationMembershipRequiredError,
    OrganizationNotFoundError,
)
from backend.core.logging import LOGGER_NAME
from backend.core.request_context import get_request_id
from backend.db.models import (
    AuditAction,
    AuditLog,
    OrganizationRole,
    User,
)
from backend.repositories.audit_repository import (
    create_audit_log,
    list_audit_logs_for_organization,
)
from backend.repositories.organization_repository import (
    get_membership,
    get_organization_by_id,
)


logger = logging.getLogger(LOGGER_NAME)


# Only these keys may ever be persisted in AuditLog.details, and their values
# must be non-sensitive scalars (ids, counts, enum strings). Anything else is
# dropped so audit logging can never become a data-leak path for credentials,
# tokens, request bodies/headers, prompts or document content.
_SAFE_DETAIL_KEYS = frozenset(
    {
        "version",
        "file_size",
        "content_type",
        "status",
        "role",
        "target_user_id",
    }
)


def _safe_details(details: dict | None) -> dict | None:
    if not details:
        return None

    safe = {
        key: value
        for key, value in details.items()
        if key in _SAFE_DETAIL_KEYS
    }

    return safe or None


def record_audit_event(
    db: Session,
    *,
    organization_id: int | None,
    actor_user_id: int | None,
    action: AuditAction,
    resource_type: str | None = None,
    resource_id: int | None = None,
    success: bool = True,
    details: dict | None = None,
) -> None:
    """Best-effort audit write.

    A failure here must never break the underlying operation or mask its real
    error, so exceptions are swallowed after a rollback and a warning log.
    """

    try:
        create_audit_log(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=get_request_id(),
            success=success,
            details=_safe_details(details),
        )
    except Exception:
        db.rollback()

        logger.warning(
            "audit event could not be recorded",
            extra={
                "action": str(action),
                "organization_id": organization_id,
            },
        )


def list_organization_audit_logs_service(
    db: Session,
    *,
    organization_id: int,
    acting_user: User,
    limit: int,
    offset: int,
) -> list[AuditLog]:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    membership = get_membership(
        db=db,
        organization_id=organization_id,
        user_id=acting_user.id,
    )

    if not membership:
        raise OrganizationMembershipRequiredError(
            "Organization membership required"
        )

    if membership.role not in {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
    }:
        raise OrganizationAccessDeniedError(
            "Organization admin access required"
        )

    return list_audit_logs_for_organization(
        db=db,
        organization_id=organization_id,
        limit=limit,
        offset=offset,
    )
