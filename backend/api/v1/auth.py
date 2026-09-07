from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies.database import get_db
from backend.schemas.auth import AuthRegisterRequest
from backend.schemas.user import UserResponse
from backend.services.auth_service import register_user_service


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
