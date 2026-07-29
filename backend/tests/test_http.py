from fastapi import HTTPException

from app.core.request_context import get_request_id
from app.main import create_app
from tests.conftest import AppClient


def test_operational_endpoints_succeed(client: AppClient) -> None:
    for path in ("/", "/health", "/live", "/ready"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == {"service": "January", "status": "ok"}
        assert response.headers["X-Request-ID"]


def test_supplied_request_id_is_returned(client: AppClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "request-123"})

    assert response.headers["X-Request-ID"] == "request-123"


def test_missing_or_invalid_request_ids_are_generated(client: AppClient) -> None:
    missing = client.get("/health")
    invalid = client.get("/health", headers={"X-Request-ID": "bad value"})

    assert missing.headers["X-Request-ID"]
    assert invalid.headers["X-Request-ID"]
    assert invalid.headers["X-Request-ID"] != "bad value"


def test_request_local_state_does_not_leak_between_requests(client: AppClient) -> None:
    first = client.get("/health", headers={"X-Request-ID": "first-request"})
    second = client.get("/health", headers={"X-Request-ID": "second-request"})

    assert first.headers["X-Request-ID"] == "first-request"
    assert second.headers["X-Request-ID"] == "second-request"
    assert get_request_id() is None


def test_unhandled_errors_are_safe_and_include_request_id() -> None:
    app = create_app()

    @app.get("/test-unhandled-error")
    async def test_unhandled_error() -> None:
        raise RuntimeError("secret implementation detail")

    response = AppClient(app).get(
        "/test-unhandled-error", headers={"X-Request-ID": "error-123"}
    )

    assert response.status_code == 500
    assert response.json() == {
        "error_type": "internal_error",
        "message": "Internal server error",
        "request_id": "error-123",
    }
    assert response.headers["X-Request-ID"] == "error-123"
    assert "secret implementation detail" not in response.text


def test_normal_http_errors_are_not_converted_to_internal_errors() -> None:
    app = create_app()

    @app.get("/test-http-error")
    async def test_http_error() -> None:
        raise HTTPException(status_code=418, detail="expected client error")

    response = AppClient(app).get("/test-http-error")

    assert response.status_code == 418
    assert response.json() == {"detail": "expected client error"}
    assert response.headers["X-Request-ID"]
