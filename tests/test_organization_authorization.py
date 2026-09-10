import pytest
from fastapi import HTTPException

from backend.db.models import OrganizationMembership, OrganizationRole, User
from backend.dependencies.organization_authorization import (
    require_organization_admin,
    require_organization_member,
    require_organization_owner,
)
from backend.services.organization_service import (
    create_organization_service,
)


def create_user(
    db,
    email,
    name,
):
    user = User(
        email=email,
        full_name=name,
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def add_membership(
    db,
    organization_id,
    user_id,
    role,
):
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )

    db.add(membership)
    db.commit()

    return membership


def test_member_guard_allows_member(db):
    user = create_user(
        db,
        "guard-member@example.com",
        "Guard Member",
    )

    organization = create_organization_service(
        db=db,
        name="Guard Member Company",
        user_id=user.id,
    )

    assert (
        require_organization_member(
            db=db,
            organization_id=organization.id,
            current_user=user,
        )
        is user
    )


def test_member_guard_rejects_non_member(db):
    owner = create_user(
        db,
        "guard-owner@example.com",
        "Guard Owner",
    )

    outsider = create_user(
        db,
        "guard-outsider@example.com",
        "Guard Outsider",
    )

    organization = create_organization_service(
        db=db,
        name="Guard Company",
        user_id=owner.id,
    )

    with pytest.raises(HTTPException) as exc_info:
        require_organization_member(
            db=db,
            organization_id=organization.id,
            current_user=outsider,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "Organization membership required"
    )


def test_admin_guard_allows_admin(db):
    owner = create_user(
        db,
        "guard-admin-owner@example.com",
        "Guard Admin Owner",
    )

    admin = create_user(
        db,
        "guard-admin@example.com",
        "Guard Admin",
    )

    organization = create_organization_service(
        db=db,
        name="Guard Admin Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        admin.id,
        OrganizationRole.ADMIN,
    )

    assert (
        require_organization_admin(
            db=db,
            organization_id=organization.id,
            current_user=admin,
        )
        is admin
    )


def test_admin_guard_rejects_member(db):
    owner = create_user(
        db,
        "guard-member-owner@example.com",
        "Guard Member Owner",
    )

    member = create_user(
        db,
        "guard-admin-member@example.com",
        "Guard Admin Member",
    )

    organization = create_organization_service(
        db=db,
        name="Guard Admin Reject Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        member.id,
        OrganizationRole.MEMBER,
    )

    with pytest.raises(HTTPException) as exc_info:
        require_organization_admin(
            db=db,
            organization_id=organization.id,
            current_user=member,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "Organization admin access required"
    )


def test_owner_guard_rejects_admin(db):
    owner = create_user(
        db,
        "guard-owner-user@example.com",
        "Guard Owner User",
    )

    admin = create_user(
        db,
        "guard-owner-admin@example.com",
        "Guard Owner Admin",
    )

    organization = create_organization_service(
        db=db,
        name="Guard Owner Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        admin.id,
        OrganizationRole.ADMIN,
    )

    with pytest.raises(HTTPException) as exc_info:
        require_organization_owner(
            db=db,
            organization_id=organization.id,
            current_user=admin,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "Organization owner access required"
    )


def test_owner_guard_allows_owner(db):
    owner = create_user(
        db,
        "guard-real-owner@example.com",
        "Guard Real Owner",
    )

    organization = create_organization_service(
        db=db,
        name="Guard Real Owner Company",
        user_id=owner.id,
    )

    assert (
        require_organization_owner(
            db=db,
            organization_id=organization.id,
            current_user=owner,
        )
        is owner
    )

