"""FastAPI application factory and ASGI entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.infrastructure.database.database import Database
from app.infrastructure.telegram.adapter import create_telegram_adapter
from app.interface.http.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from app.interface.http.models import ErrorResponse
from app.interface.http.routes import create_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct the HTTP application without connecting during import."""

    configured_settings = settings or get_settings()
    configure_logging(configured_settings.log_level)
    database = Database(configured_settings)
    telegram = create_telegram_adapter(configured_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await database.start()
        app.state.database = database
        app.state.telegram = telegram
        try:
            yield
        finally:
            if telegram is not None:
                await telegram.aclose()
            await database.stop()

    app = FastAPI(
        title=configured_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.database = database
    app.state.telegram = telegram
    app.add_middleware(RequestIdMiddleware)
    app.include_router(create_router(configured_settings))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logging.getLogger("january").exception("unhandled_request_error")
        body = ErrorResponse(
            error_type="internal_error",
            message="Internal server error",
            request_id=request_id,
        )
        response = JSONResponse(status_code=500, content=body.model_dump())
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    return app


app = create_app()
