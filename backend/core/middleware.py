import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.core.logging import LOGGER_NAME


logger = logging.getLogger(LOGGER_NAME)

REQUEST_ID_HEADER = "X-Request-ID"

# A client-supplied request ID is only trusted when it is short and made of
# characters that cannot smuggle newlines, quotes or other values into logs or
# downstream headers. Anything else is discarded and replaced with a fresh UUID.
_MAX_REQUEST_ID_LENGTH = 128
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def generate_request_id() -> str:
    return str(uuid.uuid4())


def sanitize_request_id(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    if not value or len(value) > _MAX_REQUEST_ID_LENGTH:
        return None

    if not _REQUEST_ID_PATTERN.match(value):
        return None

    return value


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request and log its completion.

    Only non-sensitive request metadata (id, method, path, status, duration) is
    logged. Headers, query strings, bodies and payloads are never touched.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = sanitize_request_id(
            request.headers.get(REQUEST_ID_HEADER)
        ) or generate_request_id()

        # Stored on the shared scope state so the endpoint and the top-level
        # exception handler can attach the same ID to their responses.
        request.state.request_id = request_id

        start = time.monotonic()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = (time.monotonic() - start) * 1000.0

            logger.info(
                "request completed "
                f"request_id={request_id} "
                f"method={request.method} "
                f"path={request.url.path} "
                f"status_code={status_code} "
                f"duration_ms={duration_ms:.2f}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
