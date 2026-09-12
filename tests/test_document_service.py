import pytest

from backend.core.exceptions import (
    DocumentNotFoundError,
    OrganizationAccessDeniedError,
    OrganizationMembershipRequiredError,
)
from backend.db.models import (
    DocumentStatus,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from backend.repositories.document_repository import (
    create_document,
)
from backend.services.document_service import (
    create_document_service,
    delete_document_service,
    get_document_service,
    list_documents_service,
    update_document_status_service,
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
    role=OrganizationRole.MEMBER,
):
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )

    db.add(membership)
    db.commit()

    return membership


def test_member_can_create_document(db):
    user = create_user(
        db,
        "document-service-member@example.com",
        "Document Service Member",
    )

    organization = create_organization_service(
        db=db,
        name="Document Service Company",
        user_id=user.id,
    )

    document = create_document_service(
        db=db,
        organization_id=organization.id,
        name="engineering.pdf",
        current_user=user,
    )

    assert document.id is not None
    assert document.organization_id == organization.id
    assert document.uploaded_by == user.id
    assert document.status == DocumentStatus.PENDING


def test_non_member_cannot_create_document(db):
    owner = create_user(
        db,
        "document-create-owner@example.com",
        "Document Create Owner",
    )

    outsider = create_user(
        db,
        "document-create-outsider@example.com",
        "Document Create Outsider",
    )

    organization = create_organization_service(
        db=db,
        name="Private Document Company",
        user_id=owner.id,
    )

    with pytest.raises(
        OrganizationMembershipRequiredError
    ):
        create_document_service(
            db=db,
            organization_id=organization.id,
            name="secret.pdf",
            current_user=outsider,
        )


def test_document_access_is_tenant_scoped(db):
    user_a = create_user(
        db,
        "document-service-a@example.com",
        "Document Service A",
    )

    user_b = create_user(
        db,
        "document-service-b@example.com",
        "Document Service B",
    )

    organization_a = create_organization_service(
        db=db,
        name="Service Company A",
        user_id=user_a.id,
    )

    organization_b = create_organization_service(
        db=db,
        name="Service Company B",
        user_id=user_b.id,
    )

    document = create_document(
        db=db,
        organization_id=organization_a.id,
        uploaded_by=user_a.id,
        name="private-a.pdf",
    )

    with pytest.raises(DocumentNotFoundError):
        get_document_service(
            db=db,
            organization_id=organization_b.id,
            document_id=document.id,
            current_user=user_b,
        )


def test_member_can_list_organization_documents(db):
    user = create_user(
        db,
        "document-list-member@example.com",
        "Document List Member",
    )

    organization = create_organization_service(
        db=db,
        name="Document List Company",
        user_id=user.id,
    )

    create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="one.pdf",
    )

    create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="two.pdf",
    )

    documents = list_documents_service(
        db=db,
        organization_id=organization.id,
        current_user=user,
    )

    assert len(documents) == 2


def test_member_cannot_update_document_status(db):
    owner = create_user(
        db,
        "document-status-owner@example.com",
        "Document Status Owner",
    )

    member = create_user(
        db,
        "document-status-member@example.com",
        "Document Status Member",
    )

    organization = create_organization_service(
        db=db,
        name="Status Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        member.id,
        OrganizationRole.MEMBER,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="status.pdf",
    )

    with pytest.raises(OrganizationAccessDeniedError):
        update_document_status_service(
            db=db,
            organization_id=organization.id,
            document_id=document.id,
            status=DocumentStatus.READY,
            current_user=member,
        )


def test_admin_can_update_document_status(db):
    owner = create_user(
        db,
        "document-admin-owner@example.com",
        "Document Admin Owner",
    )

    admin = create_user(
        db,
        "document-admin@example.com",
        "Document Admin",
    )

    organization = create_organization_service(
        db=db,
        name="Admin Document Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        admin.id,
        OrganizationRole.ADMIN,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="admin-status.pdf",
    )

    updated = update_document_status_service(
        db=db,
        organization_id=organization.id,
        document_id=document.id,
        status=DocumentStatus.READY,
        current_user=admin,
    )

    assert updated.status == DocumentStatus.READY


def test_member_cannot_delete_document(db):
    owner = create_user(
        db,
        "document-delete-owner@example.com",
        "Document Delete Owner",
    )

    member = create_user(
        db,
        "document-delete-member@example.com",
        "Document Delete Member",
    )

    organization = create_organization_service(
        db=db,
        name="Delete Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        member.id,
        OrganizationRole.MEMBER,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=member.id,
        name="delete.pdf",
    )

    with pytest.raises(OrganizationAccessDeniedError):
        delete_document_service(
            db=db,
            organization_id=organization.id,
            document_id=document.id,
            current_user=member,
        )


def test_admin_can_delete_document(db):
    owner = create_user(
        db,
        "document-admin-delete-owner@example.com",
        "Document Admin Delete Owner",
    )

    admin = create_user(
        db,
        "document-admin-delete@example.com",
        "Document Admin Delete",
    )

    organization = create_organization_service(
        db=db,
        name="Admin Delete Company",
        user_id=owner.id,
    )

    add_membership(
        db,
        organization.id,
        admin.id,
        OrganizationRole.ADMIN,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="admin-delete.pdf",
    )

    delete_document_service(
        db=db,
        organization_id=organization.id,
        document_id=document.id,
        current_user=admin,
    )

    with pytest.raises(DocumentNotFoundError):
        get_document_service(
            db=db,
            organization_id=organization.id,
            document_id=document.id,
            current_user=owner,
        )
