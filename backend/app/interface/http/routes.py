"""Operational HTTP endpoints."""

from fastapi import APIRouter

from app.core.config import Settings
from app.interface.http.models import ServiceResponse


def create_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_model=ServiceResponse, tags=["operations"])
    async def root() -> ServiceResponse:
        return ServiceResponse(service=settings.app_name)

    @router.get("/health", response_model=ServiceResponse, tags=["operations"])
    async def health() -> ServiceResponse:
        return ServiceResponse(service=settings.app_name)

    @router.get("/live", response_model=ServiceResponse, tags=["operations"])
    async def live() -> ServiceResponse:
        return ServiceResponse(service=settings.app_name)

    @router.get("/ready", response_model=ServiceResponse, tags=["operations"])
    async def ready() -> ServiceResponse:
        return ServiceResponse(service=settings.app_name)

    return router
