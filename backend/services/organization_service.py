from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import Organization, OrganizationRole
from backend.repositories.organization_repository import (
    create_organization,
    create_organization_membership,
)


def create_organization_service(
    db: Session,
    name: str,
    user_id: int,
) -> Organization:
    organization = create_organization(
        db=db,
        name=name.strip(),
    )

    create_organization_membership(
        db=db,
        organization_id=organization.id,
        user_id=user_id,
        role=OrganizationRole.OWNER,
    )

    try:
        db.commit()
        db.refresh(organization)
    except IntegrityError:
        db.rollback()
        raise

    return organization
