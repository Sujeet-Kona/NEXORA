from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.core.exceptions import (
    DocumentNotFoundError,
    DocumentUploadFailedError,
    InvalidCredentialsError,
    InvalidDocumentUploadError,
    InvalidUserIdError,
    OrganizationAccessDeniedError,
    OrganizationMembershipAlreadyExistsError,
    OrganizationMembershipRequiredError,
    OrganizationNotFoundError,
    UserAlreadyExistsError,
    UserNotFoundError,
)


async def invalid_credentials_handler(
    request: Request,
    exc: InvalidCredentialsError,
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": str(exc)},
    )


async def invalid_user_id_handler(
    request: Request,
    exc: InvalidUserIdError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


async def user_not_found_handler(
    request: Request,
    exc: UserNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
    )


async def user_already_exists_handler(
    request: Request,
    exc: UserAlreadyExistsError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc)},
    )


async def organization_not_found_handler(
    request: Request,
    exc: OrganizationNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
    )


async def organization_membership_required_handler(
    request: Request,
    exc: OrganizationMembershipRequiredError,
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": str(exc)},
    )


async def organization_access_denied_handler(
    request: Request,
    exc: OrganizationAccessDeniedError,
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": str(exc)},
    )


async def organization_membership_already_exists_handler(
    request: Request,
    exc: OrganizationMembershipAlreadyExistsError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc)},
    )


async def document_not_found_handler(
    request: Request,
    exc: DocumentNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
    )


async def invalid_document_upload_handler(
    request: Request,
    exc: InvalidDocumentUploadError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


async def document_upload_failed_handler(
    request: Request,
    exc: DocumentUploadFailedError,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Document upload failed"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        InvalidCredentialsError,
        invalid_credentials_handler,
    )

    app.add_exception_handler(
        InvalidUserIdError,
        invalid_user_id_handler,
    )

    app.add_exception_handler(
        UserNotFoundError,
        user_not_found_handler,
    )

    app.add_exception_handler(
        UserAlreadyExistsError,
        user_already_exists_handler,
    )

    app.add_exception_handler(
        OrganizationNotFoundError,
        organization_not_found_handler,
    )

    app.add_exception_handler(
        OrganizationMembershipRequiredError,
        organization_membership_required_handler,
    )

    app.add_exception_handler(
        OrganizationAccessDeniedError,
        organization_access_denied_handler,
    )

    app.add_exception_handler(
        OrganizationMembershipAlreadyExistsError,
        organization_membership_already_exists_handler,
    )

    app.add_exception_handler(
        DocumentNotFoundError,
        document_not_found_handler,
    )

    app.add_exception_handler(
        InvalidDocumentUploadError,
        invalid_document_upload_handler,
    )

    app.add_exception_handler(
        DocumentUploadFailedError,
        document_upload_failed_handler,
    )
