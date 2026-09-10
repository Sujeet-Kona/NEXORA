import pytest

from backend.core.exceptions import (
    OrganizationAccessDeniedError,
    OrganizationMembershipAlreadyExistsError,
    OrganizationMembershipRequiredError,
    UserNotFoundError,
)
from backend.db.models import OrganizationRole, User
from backend.repositories.organization_repository import (
    get_membership,
)
from backend.services.organization_membership_service import (
    add_organization_member_service,
)
from backend.services.organization_service import (
    create_organization_service,
)


def create_user(db, email, name):
    user = User(
        email=email,
        full_name=name,
        password_hash="test-hash",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_owner_can_add_member(db):
    owner = create_user(
        db,
        "owner@example.com",
        "Owner User",
    )

    target = create_user(
        db,
        "target@example.com",
        "Target User",
    )

    organization = create_organization_service(
        db=db,
        name="Owner Company",
        user_id=owner.id,
    )

    membership = add_organization_member_service(
        db=db,
        organization_id=organization.id,
        user_id=target.id,
        role=OrganizationRole.MEMBER,
        acting_user=owner,
    )

    assert membership.user_id == target.id
    assert membership.organization_id == organization.id
    assert membership.role == OrganizationRole.MEMBER


def test_admin_can_add_member(db):
    owner = create_user(
        db,
        "org-owner@example.com",
        "Org Owner",
    )

    admin = create_user(
        db,
        "org-admin@example.com",
        "Org Admin",
    )

    target = create_user(
        db,
        "org-target@example.com",
        "Org Target",
    )

    organization = create_organization_service(
        db=db,
        name="Admin Company",
        user_id=owner.id,
    )

    admin_membership = __import__(
        "backend.db.models",
        fromlist=["OrganizationMembership"],
    ).OrganizationMembership(
        organization_id=organization.id,
        user_id=admin.id,
        role=OrganizationRole.ADMIN,
    )

    db.add(admin_membership)
    db.commit()

    membership = add_organization_member_service(
        db=db,
        organization_id=organization.id,
        user_id=target.id,
        role=OrganizationRole.MEMBER,
        acting_user=admin,
    )

    assert membership.user_id == target.id
    assert membership.organization_id == organization.id
    assert membership.role == OrganizationRole.MEMBER


def test_member_cannot_add_member(db):
    owner = create_user(
        db,
        "member-owner@example.com",
        "Member Owner",
    )

    member = create_user(
        db,
        "member-user@example.com",
        "Member User",
    )

    target = create_user(
        db,
        "member-target@example.com",
        "Member Target",
    )

    organization = create_organization_service(
        db=db,
        name="Member Company",
        user_id=owner.id,
    )

    member_membership = __import__(
        "backend.db.models",
        fromlist=["OrganizationMembership"],
    ).OrganizationMembership(
        organization_id=organization.id,
        user_id=member.id,
        role=OrganizationRole.MEMBER,
    )

    db.add(member_membership)
    db.commit()

    with pytest.raises(OrganizationAccessDeniedError) as exc_info:
        add_organization_member_service(
            db=db,
            organization_id=organization.id,
            user_id=target.id,
            role=OrganizationRole.MEMBER,
            acting_user=member,
        )

    assert str(exc_info.value) == "Organization admin access required"


def test_user_from_other_organization_cannot_add_member(db):
    owner_a = create_user(
        db,
        "owner-a@example.com",
        "Owner A",
    )

    owner_b = create_user(
        db,
        "owner-b@example.com",
        "Owner B",
    )

    target = create_user(
        db,
        "cross-target@example.com",
        "Cross Target",
    )

    organization_a = create_organization_service(
        db=db,
        name="Company A",
        user_id=owner_a.id,
    )

    create_organization_service(
        db=db,
        name="Company B",
        user_id=owner_b.id,
    )

    with pytest.raises(
        OrganizationMembershipRequiredError
    ) as exc_info:
        add_organization_member_service(
            db=db,
            organization_id=organization_a.id,
            user_id=target.id,
            role=OrganizationRole.MEMBER,
            acting_user=owner_b,
        )

    assert str(exc_info.value) == "Organization membership required"


def test_duplicate_membership_is_rejected(db):
    owner = create_user(
        db,
        "duplicate-owner@example.com",
        "Duplicate Owner",
    )

    target = create_user(
        db,
        "duplicate-target@example.com",
        "Duplicate Target",
    )

    organization = create_organization_service(
        db=db,
        name="Duplicate Company",
        user_id=owner.id,
    )

    add_organization_member_service(
        db=db,
        organization_id=organization.id,
        user_id=target.id,
        role=OrganizationRole.MEMBER,
        acting_user=owner,
    )

    with pytest.raises(
        OrganizationMembershipAlreadyExistsError
    ) as exc_info:
        add_organization_member_service(
            db=db,
            organization_id=organization.id,
            user_id=target.id,
            role=OrganizationRole.MEMBER,
            acting_user=owner,
        )

    assert str(exc_info.value) == "User is already a member"
