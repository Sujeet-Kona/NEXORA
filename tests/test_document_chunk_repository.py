from backend.db.models import DocumentChunk, User
from backend.repositories.document_chunk_repository import (
    create_document_chunks,
    get_chunks_for_document,
    replace_document_chunks,
)
from backend.repositories.document_repository import (
    create_document,
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


def create_document_for_owner(db, email):
    owner = create_user(
        db,
        email,
        "Chunk Repository",
    )

    organization = create_organization_service(
        db=db,
        name=f"Chunk Repository {email}",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="policy.pdf",
    )

    return document, organization


def test_create_document_chunks_stores_page_provenance(db):
    document, organization = create_document_for_owner(
        db,
        "chunk-repository-pages@example.com",
    )

    records = create_document_chunks(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
        chunks=[
            ("first chunk", 1, 1),
            ("second chunk", 1, 3),
        ],
    )

    db.commit()

    assert [record.chunk_index for record in records] == [0, 1]

    stored = get_chunks_for_document(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
    )

    assert [
        (chunk.text, chunk.page_start, chunk.page_end)
        for chunk in stored
    ] == [
        ("first chunk", 1, 1),
        ("second chunk", 1, 3),
    ]


def test_create_document_chunks_without_pages_stays_null(db):
    document, organization = create_document_for_owner(
        db,
        "chunk-repository-no-pages@example.com",
    )

    create_document_chunks(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
        chunks=[("unmapped chunk", None, None)],
    )

    db.commit()

    stored = get_chunks_for_document(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
    )

    assert stored[0].page_start is None
    assert stored[0].page_end is None


def test_replace_document_chunks_stores_page_provenance(db):
    document, organization = create_document_for_owner(
        db,
        "chunk-repository-replace@example.com",
    )

    create_document_chunks(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
        chunks=[("old chunk", 1, 1)],
    )

    db.commit()

    replace_document_chunks(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
        chunks=[
            ("replacement chunk", 2, 4),
        ],
    )

    db.commit()

    stored = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document.id,
            DocumentChunk.organization_id == organization.id,
        )
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    assert [
        (chunk.text, chunk.page_start, chunk.page_end)
        for chunk in stored
    ] == [
        ("replacement chunk", 2, 4),
    ]
