import pytest

from backend.core.exceptions import (
    OrganizationAccessDeniedError,
    UserNotFoundError,
)
from backend.db.models import OrganizationRole, User
from backend.repositories.organization_repository import (
    get_membership,
)
from backend.services.organization_membership_service import (
    list_organization_members_service,
    remove_organization_member_service,
    update_organization_member_role_service,
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


def add_membership(
    db,
    organization_id,
    user_id,
    role,
):
    from backend.db.models import OrganizationMembership

    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )

    db.add(membership)
    db.commit()
    db.refresh(membership)

    return membership


def test_member_can_list_organization_members(db):
    owner = create_user(
        db,
        "list-owner@example.com",
        "List Owner",
    )

    member = create_user(
        db,
        "list-member@example.com",
        "List Member",
    )

    organization = create_organization_service(
        db=db,
        name="List Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        member.id,
        OrganizationRole.MEMBER,
    )

    members = list_organization_members_service(
        db=db,
        organization_id=organization.id,
        acting_user=member,
    )

    assert len(members) == 2


def test_member_can_change_no_roles(db):
    owner = create_user(
        db,
        "role-owner@example.com",
        "Role Owner",
    )

    member = create_user(
        db,
        "role-member@example.com",
        "Role Member",
    )

    organization = create_organization_service(
        db=db,
        name="Role Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        member.id,
        OrganizationRole.MEMBER,
    )

    with pytest.raises(OrganizationAccessDeniedError):
        update_organization_member_role_service(
            db=db,
            organization_id=organization.id,
            user_id=member.id,
            role=OrganizationRole.ADMIN,
            acting_user=member,
        )


def test_owner_can_promote_member_to_admin(db):
    owner = create_user(
        db,
        "promote-owner@example.com",
        "Promote Owner",
    )

    member = create_user(
        db,
        "promote-member@example.com",
        "Promote Member",
    )

    organization = create_organization_service(
        db=db,
        name="Promote Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        member.id,
        OrganizationRole.MEMBER,
    )

    updated = update_organization_member_role_service(
        db=db,
        organization_id=organization.id,
        user_id=member.id,
        role=OrganizationRole.ADMIN,
        acting_user=owner,
    )

    assert updated.role == OrganizationRole.ADMIN


def test_admin_cannot_promote_member_to_owner(db):
    owner = create_user(
        db,
        "admin-owner@example.com",
        "Admin Owner",
    )

    admin = create_user(
        db,
        "admin-user@example.com",
        "Admin User",
    )

    member = create_user(
        db,
        "admin-member@example.com",
        "Admin Member",
    )

    organization = create_organization_service(
        db=db,
        name="Admin Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        admin.id,
        OrganizationRole.ADMIN,
    )

    add_membership(
        db,
        organization.id,
        member.id,
        OrganizationRole.MEMBER,
    )

    with pytest.raises(OrganizationAccessDeniedError):
        update_organization_member_role_service(
            db=db,
            organization_id=organization.id,
            user_id=member.id,
            role=OrganizationRole.OWNER,
            acting_user=admin,
        )


def test_owner_cannot_be_modified(db):
    owner = create_user(
        db,
        "protected-owner@example.com",
        "Protected Owner",
    )

    organization = create_organization_service(
        db=db,
        name="Protected Owner Company",
        user_id=owner.id,
    )

    with pytest.raises(OrganizationAccessDeniedError):
        update_organization_member_role_service(
            db=db,
            organization_id=organization.id,
            user_id=owner.id,
            role=OrganizationRole.ADMIN,
            acting_user=owner,
        )


def test_owner_can_remove_member(db):
    owner = create_user(
        db,
        "remove-owner@example.com",
        "Remove Owner",
    )

    member = create_user(
        db,
        "remove-member@example.com",
        "Remove Member",
    )

    organization = create_organization_service(
        db=db,
        name="Remove Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        member.id,
        OrganizationRole.MEMBER,
    )

    remove_organization_member_service(
        db=db,
        organization_id=organization.id,
        user_id=member.id,
        acting_user=owner,
    )

    assert get_membership(
        db=db,
        organization_id=organization.id,
        user_id=member.id,
    ) is None


def test_member_cannot_remove_member(db):
    owner = create_user(
        db,
        "cannot-remove-owner@example.com",
        "Cannot Remove Owner",
    )

    member = create_user(
        db,
        "cannot-remove-member@example.com",
        "Cannot Remove Member",
    )

    target = create_user(
        db,
        "cannot-remove-target@example.com",
        "Cannot Remove Target",
    )

    organization = create_organization_service(
        db=db,
        name="Cannot Remove Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        member.id,
        OrganizationRole.MEMBER,
    )

    add_membership(
        db,
        organization.id,
        target.id,
        OrganizationRole.MEMBER,
    )

    with pytest.raises(OrganizationAccessDeniedError):
        remove_organization_member_service(
            db=db,
            organization_id=organization.id,
            user_id=target.id,
            acting_user=member,
        )


def test_removing_unknown_member_fails(db):
    owner = create_user(
        db,
        "unknown-remove-owner@example.com",
        "Unknown Remove Owner",
    )

    organization = create_organization_service(
        db=db,
        name="Unknown Remove Company",
        user_id=owner.id,
    )

    with pytest.raises(UserNotFoundError):
        remove_organization_member_service(
            db=db,
            organization_id=organization.id,
            user_id=999999,
            acting_user=owner,
        )
