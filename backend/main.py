import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.api.v1.router import router as api_router
from backend.core.config import settings
from backend.core.exception_handlers import register_exception_handlers
from backend.core.logging import LOGGER_NAME, configure_logging
from backend.core.middleware import (
    REQUEST_ID_HEADER,
    RequestObservabilityMiddleware,
)
from backend.dependencies.database import get_session_factory
from backend.services.providers import get_qdrant_repository
from backend.services.document_processing_recovery import (
    recover_stale_processing_documents,
)


configure_logging()

logger = logging.getLogger(LOGGER_NAME)


def recover_stale_processing_jobs(
    application: FastAPI | None = None,
) -> None:
    # Resolve the session-factory dependency through the app so test
    # overrides retain the same provider -> factory -> session contract.
    target_app = application or app
    session_factory_provider = target_app.dependency_overrides.get(
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


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    recover_stale_processing_jobs(application)
    yield


app = FastAPI(
    title="Nexora API",
    description="Secure Enterprise AI Knowledge Platform",
    version="0.1.0",
    lifespan=lifespan,
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
@app.get("/health/live")
def health_check():
    """Liveness probe: the API process is running."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness_check(request: Request):
    """Readiness probe for the dependencies required by API requests."""
    dependencies = {"postgres": "ok", "qdrant": "ok"}

    try:
        session_factory_provider = request.app.dependency_overrides.get(
            get_session_factory,
            get_session_factory,
        )
        session_factory = session_factory_provider()
        db = session_factory()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - expose status, not connection details
        dependencies["postgres"] = "unavailable"

    try:
        qdrant = get_qdrant_repository()
        qdrant.client.get_collections()
    except Exception:  # noqa: BLE001 - expose status, not server details
        dependencies["qdrant"] = "unavailable"

    ready = all(status == "ok" for status in dependencies.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "dependencies": dependencies,
        },
    )


app.include_router(api_router)
