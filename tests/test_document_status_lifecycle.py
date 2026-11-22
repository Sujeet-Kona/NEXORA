from backend.db.models import (
    OrganizationMembership,
    OrganizationRole,
    User,
)


def register_and_login(
    client,
    email,
):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": "MySecret123!",
        },
    )

    assert response.status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "MySecret123!",
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def get_user(db, email):
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    assert user is not None

    return user


def create_organization(
    client,
    token,
    name,
):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def add_member(
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


def create_document(
    client,
    token,
    organization_id,
    name="lifecycle.pdf",
):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": name},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def patch_status(
    client,
    token,
    organization_id,
    document_id,
    status,
):
    return client.patch(
        f"/api/v1/organizations/{organization_id}"
        f"/documents/{document_id}",
        json={"status": status},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )


def test_pending_to_processing_is_rejected_for_worker_ownership(client):
    token = register_and_login(
        client,
        "lifecycle-pending-processing@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Pending Processing Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "processing",
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Cannot change document status from 'pending' to 'processing'"
    }



def test_processing_to_ready_is_rejected_without_worker_promotion(client, db):
    token = register_and_login(
        client,
        "lifecycle-processing-ready@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Processing Ready Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    # Simulate a worker-owned PROCESSING state; the admin API cannot
    # create this state because it must be paired with an attempt token/lease.
    from backend.db.models import Document, DocumentStatus

    document = db.query(Document).filter(Document.id == document_id).first()
    assert document is not None
    document.status = DocumentStatus.PROCESSING
    db.commit()

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "ready",
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Cannot change document status from 'processing' to 'ready'"
    }



def test_pending_to_failed_is_allowed(client):
    token = register_and_login(
        client,
        "lifecycle-pending-failed@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Pending Failed Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "failed",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_failed_to_pending_is_allowed(client):
    token = register_and_login(
        client,
        "lifecycle-failed-pending@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Failed Pending Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    assert patch_status(
        client,
        token,
        organization_id,
        document_id,
        "failed",
    ).status_code == 200

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "pending",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_pending_to_ready_is_rejected(client):
    token = register_and_login(
        client,
        "lifecycle-skip-processing@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Skip Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "ready",
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Cannot change document status from "
            "'pending' to 'ready'"
        )
    }


def test_ready_to_pending_is_rejected(client, db):
    token = register_and_login(
        client,
        "lifecycle-ready-pending@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Ready Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    from backend.db.models import Document, DocumentStatus

    document = db.query(Document).filter(Document.id == document_id).first()
    assert document is not None
    document.status = DocumentStatus.READY
    db.commit()

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "pending",
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Cannot change document status from "
            "'ready' to 'pending'"
        )
    }


def test_ready_to_processing_is_rejected(client, db):
    token = register_and_login(
        client,
        "lifecycle-ready-processing@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Ready Processing Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    from backend.db.models import Document, DocumentStatus

    document = db.query(Document).filter(Document.id == document_id).first()
    assert document is not None
    document.status = DocumentStatus.READY
    db.commit()

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "processing",
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Cannot change document status from "
            "'ready' to 'processing'"
        )
    }


def test_repeating_the_same_status_is_allowed(client):
    token = register_and_login(
        client,
        "lifecycle-idempotent@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Idempotent Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "pending",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_unknown_status_value_is_rejected(client):
    token = register_and_login(
        client,
        "lifecycle-unknown-status@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Unknown Status Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "archived",
    )

    assert response.status_code == 422


def test_member_is_denied_before_transition_validation(
    client,
    db,
):
    owner_token = register_and_login(
        client,
        "lifecycle-member-owner@example.com",
    )

    member_token = register_and_login(
        client,
        "lifecycle-member@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Lifecycle Member Company",
    )

    member = get_user(
        db,
        "lifecycle-member@example.com",
    )

    add_member(
        db,
        organization_id,
        member.id,
        OrganizationRole.MEMBER,
    )

    document_id = create_document(
        client,
        owner_token,
        organization_id,
        name="member-lifecycle.pdf",
    )

    response = patch_status(
        client,
        member_token,
        organization_id,
        document_id,
        "ready",
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required"
    }


def test_processing_recovery_clears_attempt_ownership(client, db):
    token = register_and_login(
        client,
        "lifecycle-recovery-ownership@example.com",
    )
    organization_id = create_organization(
        client,
        token,
        "Lifecycle Recovery Ownership Company",
    )
    document_id = create_document(
        client,
        token,
        organization_id,
    )

    from datetime import datetime, timedelta
    from backend.db.models import Document, DocumentStatus

    document = db.query(Document).filter(Document.id == document_id).first()
    assert document is not None
    document.status = DocumentStatus.PROCESSING
    document.processing_attempt_id = "manual-test-attempt"
    document.processing_lease_expires_at = datetime.utcnow() + timedelta(minutes=5)
    db.commit()

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "pending",
    )
    assert response.status_code == 200
    db.refresh(document)
    assert document.status == DocumentStatus.PENDING
    assert document.processing_attempt_id is None
    assert document.processing_lease_expires_at is None



def test_admin_recovery_abandons_only_inactive_staging_generations(
    client,
    db,
):
    token = register_and_login(
        client,
        "lifecycle-recovery-generations@example.com",
    )
    organization_id = create_organization(
        client,
        token,
        "Lifecycle Recovery Generations Company",
    )
    document_id = create_document(
        client,
        token,
        organization_id,
    )

    from datetime import datetime, timedelta
    from backend.db.models import (
        Document,
        DocumentProcessingGeneration,
        DocumentStatus,
    )

    document = db.query(Document).filter(Document.id == document_id).first()
    assert document is not None
    document.status = DocumentStatus.PROCESSING
    document.processing_attempt_id = "recovery-generation-attempt"
    document.processing_lease_expires_at = datetime.utcnow() + timedelta(
        minutes=5
    )
    document.active_generation_id = "active-pointer"
    db.add_all(
        [
            DocumentProcessingGeneration(
                id="inactive-staging",
                document_id=document_id,
                organization_id=organization_id,
                attempt_id="recovery-generation-attempt",
                status="staging",
            ),
            DocumentProcessingGeneration(
                id="active-pointer",
                document_id=document_id,
                organization_id=organization_id,
                attempt_id="recovery-generation-attempt",
                status="staging",
            ),
            DocumentProcessingGeneration(
                id="other-attempt",
                document_id=document_id,
                organization_id=organization_id,
                attempt_id="different-attempt",
                status="staging",
            ),
        ]
    )
    db.commit()

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "pending",
    )
    assert response.status_code == 200

    generations = {
        generation.id: generation.status
        for generation in db.query(DocumentProcessingGeneration)
        .filter(DocumentProcessingGeneration.document_id == document_id)
        .all()
    }
    assert generations == {
        "inactive-staging": "abandoned",
        "active-pointer": "staging",
        "other-attempt": "staging",
    }
    db.refresh(document)
    assert document.active_generation_id == "active-generation"
    assert document.processing_attempt_id is None
    assert document.processing_lease_expires_at is None
