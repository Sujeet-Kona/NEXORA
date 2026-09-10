from sqlalchemy.orm import Session

from backend.db.models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
)


def create_organization(
    db: Session,
    name: str,
) -> Organization:
    organization = Organization(
        name=name,
    )

    db.add(organization)
    db.flush()

    return organization


def create_organization_membership(
    db: Session,
    organization_id: int,
    user_id: int,
    role: OrganizationRole,
) -> OrganizationMembership:
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )

    db.add(membership)

    return membership


def get_organization_by_id(
    db: Session,
    organization_id: int,
) -> Organization | None:
    return (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )


def get_membership(
    db: Session,
    organization_id: int,
    user_id: int,
) -> OrganizationMembership | None:
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
        .first()
    )


def get_organization_members(
    db: Session,
    organization_id: int,
) -> list[OrganizationMembership]:
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id
            == organization_id,
        )
        .all()
    )
