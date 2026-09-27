import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.router import router as api_router
from backend.core.config import settings
from backend.core.exception_handlers import register_exception_handlers
from backend.core.logging import LOGGER_NAME, configure_logging
from backend.core.middleware import (
    REQUEST_ID_HEADER,
    RequestObservabilityMiddleware,
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
