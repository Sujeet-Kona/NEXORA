from contextvars import ContextVar


# Bridges the request ID from the observability middleware into services that
# do not receive the Request object. A ContextVar is used so each concurrent
# request keeps its own value; Starlette/anyio copy the context into the
# threadpool used for synchronous routes.
_request_id_var: ContextVar[str | None] = ContextVar(
    "nexora_request_id",
    default=None,
)


def set_request_id(request_id: str | None) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    return _request_id_var.get()
