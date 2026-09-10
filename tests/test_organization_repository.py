from backend.db.models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from backend.repositories.organization_repository import (
    create_organization,
    create_organization_membership,
    get_membership,
    get_organization_by_id,
    get_organization_members,
)


def test_create_organization(db):
    organization = create_organization(
        db=db,
        name="Test Company",
    )

    assert organization.id is not None
    assert organization.name == "Test Company"

    db.commit()


def test_create_organization_membership(db):
    user = User(
        email="organization-member@example.com",
        full_name="Organization Member",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    organization = create_organization(
        db=db,
        name="Membership Company",
    )

    membership = create_organization_membership(
        db=db,
        organization_id=organization.id,
        user_id=user.id,
        role=OrganizationRole.MEMBER,
    )

    db.commit()
    db.refresh(membership)

    assert membership.id is not None
    assert membership.organization_id == organization.id
    assert membership.user_id == user.id
    assert membership.role == OrganizationRole.MEMBER


def test_get_organization_by_id_returns_organization(db):
    organization = create_organization(
        db=db,
        name="Lookup Company",
    )

    db.commit()
    db.refresh(organization)

    found = get_organization_by_id(
        db=db,
        organization_id=organization.id,
    )

    assert found is not None
    assert found.id == organization.id
    assert found.name == "Lookup Company"


def test_get_organization_by_id_returns_none_when_missing(db):
    found = get_organization_by_id(
        db=db,
        organization_id=999999,
    )

    assert found is None


def test_get_membership_returns_matching_membership(db):
    user = User(
        email="membership-lookup@example.com",
        full_name="Membership Lookup",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    organization = create_organization(
        db=db,
        name="Membership Lookup Company",
    )

    membership = create_organization_membership(
        db=db,
        organization_id=organization.id,
        user_id=user.id,
        role=OrganizationRole.ADMIN,
    )

    db.commit()
    db.refresh(membership)

    found = get_membership(
        db=db,
        organization_id=organization.id,
        user_id=user.id,
    )

    assert found is not None
    assert found.id == membership.id
    assert found.role == OrganizationRole.ADMIN


def test_get_membership_returns_none_when_missing(db):
    found = get_membership(
        db=db,
        organization_id=999999,
        user_id=999999,
    )

    assert found is None


def test_get_organization_members_returns_all_members(db):
    first_user = User(
        email="organization-member-one@example.com",
        full_name="Organization Member One",
        password_hash="test-hash",
    )

    second_user = User(
        email="organization-member-two@example.com",
        full_name="Organization Member Two",
        password_hash="test-hash",
    )

    db.add_all([first_user, second_user])
    db.commit()
    db.refresh(first_user)
    db.refresh(second_user)

    organization = create_organization(
        db=db,
        name="Members Company",
    )

    first_membership = create_organization_membership(
        db=db,
        organization_id=organization.id,
        user_id=first_user.id,
        role=OrganizationRole.OWNER,
    )

    second_membership = create_organization_membership(
        db=db,
        organization_id=organization.id,
        user_id=second_user.id,
        role=OrganizationRole.MEMBER,
    )

    db.commit()

    members = get_organization_members(
        db=db,
        organization_id=organization.id,
    )

    member_ids = {
        membership.user_id
        for membership in members
    }

    assert member_ids == {
        first_user.id,
        second_user.id,
    }

    assert first_membership.role == OrganizationRole.OWNER
    assert second_membership.role == OrganizationRole.MEMBER
