import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app


class AppClient:
    """Synchronous test facade over HTTPX's in-process ASGI transport."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def get(self, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return asyncio.run(self._get(path, headers))

    async def _get(self, path: str, headers: dict[str, str] | None) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get(path, headers=headers)


@pytest.fixture
def client() -> AppClient:
    return AppClient(create_app(Settings(environment="test")))
