from backend.db.models import OrganizationRole, User
from backend.repositories.organization_repository import get_membership
from backend.services.organization_service import (
    create_organization_service,
)


def test_create_organization_makes_creator_owner(db):
    user = User(
        email="organization-owner@example.com",
        full_name="Organization Owner",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    organization = create_organization_service(
        db=db,
        name="Owner Company",
        user_id=user.id,
    )

    assert organization.id is not None
    assert organization.name == "Owner Company"

    membership = get_membership(
        db=db,
        organization_id=organization.id,
        user_id=user.id,
    )

    assert membership is not None
    assert membership.role == OrganizationRole.OWNER


def test_create_organization_strips_name(db):
    user = User(
        email="organization-name@example.com",
        full_name="Organization Name",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    organization = create_organization_service(
        db=db,
        name="   Acme Engineering   ",
        user_id=user.id,
    )

    assert organization.name == "Acme Engineering"
