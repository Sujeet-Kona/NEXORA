from fastapi import APIRouter

from backend.api.v1.audit import router as audit_router
from backend.api.v1.auth import router as auth_router
from backend.api.v1.documents import router as documents_router
from backend.api.v1.organizations import router as organizations_router
from backend.api.v1.rag import router as rag_router
from backend.api.v1.users import router as users_router


router = APIRouter(
    prefix="/api/v1",
)

router.include_router(auth_router)
router.include_router(users_router)
router.include_router(organizations_router)
router.include_router(documents_router)
router.include_router(rag_router)
router.include_router(audit_router)
