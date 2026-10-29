from tests.document_processing_service_cases import *

from backend.repositories.document_repository import update_document_status


def test_reprocessing_clears_previous_failure_reason(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-retry@example.com",
        "Processing Retry",
    )

    organization = create_organization_service(
        db=db,
        name="Processing Retry Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="retry.pdf",
        storage_key="documents/retry.pdf",
        content_type="application/pdf",
    )

    update_document_failure(
        db=db,
        document=document,
        failure_reason="Document text extraction failed",
    )

    # Retry is an explicit FAILED -> PENDING transition. The processing
    # worker then owns the PENDING -> PROCESSING -> READY transitions.
    update_document_status(
        db=db,
        document=document,
        status=DocumentStatus.PENDING,
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.LocalStorage.read",
        lambda self, key: b"fake pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.extract_document",
        lambda **kwargs: make_extracted_document(),
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.index_document_chunks",
        lambda **kwargs: None,
    )

    embedding = Mock()
    qdrant = Mock()

    process_document(
        db=db,
        document_id=document.id,
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    db.refresh(document)

    assert document.status == DocumentStatus.READY
    assert document.failure_reason is None
