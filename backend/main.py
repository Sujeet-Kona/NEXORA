import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.v1.router import router as api_router
from backend.core.config import settings
from backend.core.exception_handlers import register_exception_handlers
from backend.core.logging import LOGGER_NAME, configure_logging
from backend.core.middleware import (
    REQUEST_ID_HEADER,
    RequestObservabilityMiddleware,
)
from backend.dependencies.database import get_session_factory
from backend.services.document_processing_recovery import (
    recover_stale_processing_documents,
)


configure_logging()

logger = logging.getLogger(LOGGER_NAME)


app = FastAPI(
    title="Nexora API",
    description="Secure Enterprise AI Knowledge Platform",
    version="0.1.0",
)

app.add_middleware(RequestObservabilityMiddleware)

# CORS is only enabled when explicit origins are configured. A wildcard origin
# is rejected at settings-load time in production, so this list never contains
# "*" for a production deployment.
cors_allowed_origins = settings.cors_allowed_origins

if cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allowed_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def recover_stale_processing_jobs() -> None:
    # ``get_session_factory`` is a dependency provider whose return value is
    # the actual session factory. Test overrides therefore have the same
    # contract: override -> session factory -> session. Calling the override
    # only once would leave ``db`` as a sessionmaker and break startup cleanup.
    session_factory_provider = app.dependency_overrides.get(
        get_session_factory,
        get_session_factory,
    )
    session_factory = session_factory_provider()
    db = session_factory()

    try:
        recovered = recover_stale_processing_documents(db)
        if recovered:
            logger.warning(
                "Recovered stale document processing jobs at startup",
                extra={"recovered_count": recovered},
            )
    finally:
        db.close()


@app.exception_handler(Exception)
async def internal_server_error_handler(
    request: Request,
    exc: Exception,
):
    request_id = getattr(request.state, "request_id", None)

    logger.exception(
        "Unhandled application error",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        },
    )

    headers = {}

    if request_id is not None:
        headers[REQUEST_ID_HEADER] = request_id

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=headers,
    )


register_exception_handlers(app)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(api_router)
