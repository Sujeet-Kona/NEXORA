import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.api.router import router as api_router
from backend.core.exception_handlers import register_exception_handlers
from backend.core.logging import LOGGER_NAME, configure_logging


configure_logging()

logger = logging.getLogger(LOGGER_NAME)


app = FastAPI(
    title="Nexora API",
    description="Secure Enterprise AI Knowledge Platform",
    version="0.1.0",
)


@app.exception_handler(Exception)
async def internal_server_error_handler(
    request: Request,
    exc: Exception,
):
    logger.exception(
        "Unhandled application error",
        extra={
            "method": request.method,
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


register_exception_handlers(app)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(api_router)
