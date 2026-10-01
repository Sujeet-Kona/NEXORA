import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.core.exceptions import (
    DocumentDeletionFailedError,
    DocumentNotFoundError,
    DocumentUploadFailedError,
    InvalidCredentialsError,
    InvalidDocumentStatusTransitionError,
    InvalidDocumentUploadError,
    InvalidUserIdError,
    LLMConfigurationError,
    LLMGenerationError,
    OrganizationAccessDeniedError,
    OrganizationMembershipAlreadyExistsError,
    OrganizationMembershipRequiredError,
    OrganizationNotFoundError,
    TooManyLoginAttemptsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from backend.core.logging import LOGGER_NAME


logger = logging.getLogger(LOGGER_NAME)


# Domain exceptions whose response is exactly {"detail": str(exc)} at a fixed
# status code. Their handlers are generated from this table; anything needing a
# custom body, headers, or logging stays a named handler below.
SIMPLE_EXCEPTION_STATUS: dict[type[Exception], int] = {
    InvalidCredentialsError: 401,
    InvalidUserIdError: 400,
    UserNotFoundError: 404,
    UserAlreadyExistsError: 409,
    OrganizationNotFoundError: 404,
    OrganizationMembershipRequiredError: 403,
    OrganizationAccessDeniedError: 403,
    OrganizationMembershipAlreadyExistsError: 409,
    DocumentNotFoundError: 404,
    InvalidDocumentUploadError: 400,
    DocumentDeletionFailedError: 503,
    InvalidDocumentStatusTransitionError: 409,
}


def _detail_handler(status_code: int):
    async def handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"detail": str(exc)},
        )

    return handler


async def too_many_login_attempts_handler(
    request: Request,
    exc: TooManyLoginAttemptsError,
) -> JSONResponse:
    headers = {}

    if exc.retry_after > 0:
        headers["Retry-After"] = str(exc.retry_after)

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many login attempts. Try again later."
        },
        headers=headers,
    )


async def document_upload_failed_handler(
    request: Request,
    exc: DocumentUploadFailedError,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Document upload failed"},
    )


async def llm_generation_error_handler(
    request: Request,
    exc: LLMGenerationError,
) -> JSONResponse:
    logger.warning(
        "LLM provider request failed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "reason": str(exc),
        },
    )

    return JSONResponse(
        status_code=503,
        content={"detail": "LLM provider request failed"},
    )


async def llm_configuration_error_handler(
    request: Request,
    exc: LLMConfigurationError,
) -> JSONResponse:
    logger.error(
        "LLM provider is misconfigured",
        extra={
            "method": request.method,
            "path": request.url.path,
            "reason": str(exc),
        },
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "LLM provider is not configured"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    for exc_class, status_code in SIMPLE_EXCEPTION_STATUS.items():
        app.add_exception_handler(
            exc_class,
            _detail_handler(status_code),
        )

    app.add_exception_handler(
        TooManyLoginAttemptsError,
        too_many_login_attempts_handler,
    )

    app.add_exception_handler(
        DocumentUploadFailedError,
        document_upload_failed_handler,
    )

    app.add_exception_handler(
        LLMGenerationError,
        llm_generation_error_handler,
    )

    app.add_exception_handler(
        LLMConfigurationError,
        llm_configuration_error_handler,
    )
