from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.core.exceptions import (
    InvalidUserIdError,
    UserAlreadyExistsError,
    UserNotFoundError,
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


def register_exception_handlers(app: FastAPI) -> None:
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
