from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import InvalidDocumentUploadError
from backend.dependencies.auth import CurrentUser
from backend.dependencies.database import (
    get_db,
    get_session_factory,
)
from backend.dependencies.pagination import Pagination
from backend.dependencies.rag import get_qdrant_repository
from backend.repositories.qdrant_repository import QdrantRepository
from backend.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentStatusUpdate,
)
from backend.services.document_processing_worker import (
    process_document_background,
)
from backend.services.document_service import (
    create_document_service,
    delete_document_service,
    get_document_service,
    list_documents_service,
    update_document_status_service,
    upload_document_service,
    upload_document_version_service,
)


router = APIRouter(
    prefix="/organizations",
    tags=["documents"],
)


async def _read_upload(file: UploadFile) -> bytes:
    chunks = []
    total_size = 0

    while True:
        chunk = await file.read(1024 * 1024)

        if not chunk:
            break

        total_size += len(chunk)

        if total_size > settings.max_upload_size_bytes:
            raise InvalidDocumentUploadError(
                "Uploaded file exceeds the maximum allowed size"
            )

        chunks.append(chunk)

    return b"".join(chunks)


@router.post(
    "/{organization_id}/documents",
    response_model=DocumentResponse,
    status_code=201,
)
def create_document(
    organization_id: int,
    request: DocumentCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    return create_document_service(
        db=db,
        organization_id=organization_id,
        name=request.name,
        current_user=current_user,
    )


@router.post(
    "/{organization_id}/documents/upload",
    response_model=DocumentResponse,
    status_code=201,
)
async def upload_document(
    organization_id: int,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    session_factory: Callable[[], Session] = Depends(
        get_session_factory,
    ),
):
    content = await _read_upload(file)

    document = upload_document_service(
        db=db,
        organization_id=organization_id,
        filename=file.filename or "",
        content=content,
        content_type=file.content_type,
        current_user=current_user,
    )

    background_tasks.add_task(
        process_document_background,
        document.id,
        session_factory,
    )

    return document


@router.post(
    "/{organization_id}/documents/{document_id}/versions",
    response_model=DocumentResponse,
    status_code=201,
)
async def upload_document_version(
    organization_id: int,
    document_id: int,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    session_factory: Callable[[], Session] = Depends(
        get_session_factory,
    ),
    qdrant_repository: QdrantRepository = Depends(
        get_qdrant_repository,
    ),
):
    content = await _read_upload(file)

    document = upload_document_version_service(
        db=db,
        organization_id=organization_id,
        document_id=document_id,
        filename=file.filename or "",
        content=content,
        content_type=file.content_type,
        current_user=current_user,
        qdrant_repository=qdrant_repository,
    )

    background_tasks.add_task(
        process_document_background,
        document.id,
        session_factory,
    )

    return document


@router.get(
    "/{organization_id}/documents",
    response_model=list[DocumentResponse],
)
def list_documents(
    organization_id: int,
    current_user: CurrentUser,
    pagination: Pagination,
    db: Session = Depends(get_db),
):
    return list_documents_service(
        db=db,
        organization_id=organization_id,
        current_user=current_user,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/{organization_id}/documents/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    organization_id: int,
    document_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    return get_document_service(
        db=db,
        organization_id=organization_id,
        document_id=document_id,
        current_user=current_user,
    )


@router.patch(
    "/{organization_id}/documents/{document_id}",
    response_model=DocumentResponse,
)
def update_document_status(
    organization_id: int,
    document_id: int,
    request: DocumentStatusUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    return update_document_status_service(
        db=db,
        organization_id=organization_id,
        document_id=document_id,
        status=request.status,
        current_user=current_user,
    )


@router.delete(
    "/{organization_id}/documents/{document_id}",
    status_code=204,
)
def delete_document(
    organization_id: int,
    document_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    qdrant_repository: QdrantRepository = Depends(
        get_qdrant_repository,
    ),
):
    delete_document_service(
        db=db,
        organization_id=organization_id,
        document_id=document_id,
        current_user=current_user,
        qdrant_repository=qdrant_repository,
    )

    return Response(status_code=204)


