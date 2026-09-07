from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUser
from backend.dependencies.database import get_db
from backend.schemas.auth import (
    AuthLoginRequest,
    AuthRegisterRequest,
    TokenResponse,
)
from backend.schemas.user import UserResponse
from backend.services.auth_service import (
    login_user_service,
    register_user_service,
)


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
)
def register_user(
    request: AuthRegisterRequest,
    db: Session = Depends(get_db),
):
    return register_user_service(
        db=db,
        email=request.email,
        full_name=request.full_name,
        password=request.password,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_user(
    request: AuthLoginRequest,
    db: Session = Depends(get_db),
):
    access_token = login_user_service(
        db=db,
        email=request.email,
        password=request.password,
    )

    return TokenResponse(
        access_token=access_token,
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_current_user_profile(
    current_user: CurrentUser,
):
    return current_user
