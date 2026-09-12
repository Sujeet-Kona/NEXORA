from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUser
from backend.dependencies.database import get_db
from backend.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentStatusUpdate,
)
from backend.services.document_service import (
    create_document_service,
    delete_document_service,
    get_document_service,
    list_documents_service,
    update_document_status_service,
)


router = APIRouter(
    prefix="/organizations",
    tags=["documents"],
)


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


@router.get(
    "/{organization_id}/documents",
    response_model=list[DocumentResponse],
)
def list_documents(
    organization_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    return list_documents_service(
        db=db,
        organization_id=organization_id,
        current_user=current_user,
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
):
    delete_document_service(
        db=db,
        organization_id=organization_id,
        document_id=document_id,
        current_user=current_user,
    )

    return Response(status_code=204)
