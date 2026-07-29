"""Operational HTTP endpoints."""

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.infrastructure.database.database import Database
from app.interface.http.middleware import REQUEST_ID_HEADER
from app.interface.http.models import (
    DatabaseComponentResponse,
    DependencyUnavailableResponse,
    HealthResponse,
    ReadinessResponse,
    ServiceResponse,
)


def dependency_unavailable(request: Request) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    body = DependencyUnavailableResponse(request_id=request_id)
    response = JSONResponse(status_code=503, content=body.model_dump())
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def database_for(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def create_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_model=ServiceResponse, tags=["operations"])
    async def root() -> ServiceResponse:
        return ServiceResponse(service=settings.app_name)

    @router.get("/health", response_model=HealthResponse, tags=["operations"])
    async def health(request: Request) -> HealthResponse | JSONResponse:
        ready = await database_for(request).is_ready()
        return HealthResponse(
            service=settings.app_name,
            status="ok" if ready else "degraded",
            application=DatabaseComponentResponse(status="ok"),
            database=DatabaseComponentResponse(status="ok" if ready else "unavailable"),
        )

    @router.get("/live", response_model=ServiceResponse, tags=["operations"])
    async def live() -> ServiceResponse:
        return ServiceResponse(service=settings.app_name)

    @router.get("/ready", response_model=ReadinessResponse, tags=["operations"])
    async def ready(request: Request) -> ReadinessResponse | JSONResponse:
        if not await database_for(request).is_ready():
            return dependency_unavailable(request)
        return ReadinessResponse(
            service=settings.app_name,
            database=DatabaseComponentResponse(status="ok"),
        )

    return router
