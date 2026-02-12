from fastapi import APIRouter

from app.api.v1.assessments import router as assessments_router
from app.api.v1.assistant import router as assistant_router
from app.api.v1.auth import router as auth_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.models import router as models_router
from app.api.v1.patients import router as patients_router
from app.api.v1.reports import router as reports_router
from app.api.v1.scans import router as scans_router
from app.api.v1.stage3 import router as stage3_router
from app.api.v1.timeline import router as timeline_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(patients_router)
api_router.include_router(assessments_router)
api_router.include_router(assistant_router)
api_router.include_router(scans_router)
api_router.include_router(models_router)
api_router.include_router(knowledge_router)
api_router.include_router(reports_router)
api_router.include_router(timeline_router)
api_router.include_router(stage3_router)
