from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUser
from backend.dependencies.authorization import require_admin
from backend.dependencies.database import get_db
from backend.schemas.auth import (
    AuthLoginRequest,
    AuthRegisterRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from backend.schemas.user import UserResponse
from backend.services.auth_service import (
    login_user_service,
    register_user_service,
)
from backend.services.refresh_token_service import (
    logout_user_service,
    refresh_access_token_service,
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
    access_token, refresh_token = login_user_service(
        db=db,
        email=request.email,
        password=request.password,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    access_token, new_refresh_token = (
        refresh_access_token_service(
            db=db,
            refresh_token=request.refresh_token,
        )
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.post(
    "/logout",
    status_code=204,
)
def logout_user(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    logout_user_service(
        db=db,
        refresh_token=request.refresh_token,
    )

    return None


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_current_user_profile(
    current_user: CurrentUser,
):
    return current_user


