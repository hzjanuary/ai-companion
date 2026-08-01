import asyncio
import logging

import pytest

from app.application.telemetry import record_provider_usage
from app.core.config import Settings
from app.core.logging import operational_event
from app.core.telemetry_context import (
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from app.infrastructure.telemetry import (
    METRICS,
    PROHIBITED_LABEL_NAMES,
    InMemoryMetricsRecorder,
    MetricsHttpExporter,
)
from app.main import create_app
from tests.conftest import AppClient, FakeDatabase


def test_registry_isolated_and_rejects_high_cardinality_labels() -> None:
    first = InMemoryMetricsRecorder()
    second = InMemoryMetricsRecorder()
    labels = {"route": "/health", "method": "GET", "status": "2xx"}
    first.increment("january_http_requests_total", **labels)

    assert first.counter_value("january_http_requests_total", **labels) == 1
    assert second.counter_value("january_http_requests_total", **labels) == 0
    assert not set().intersection(PROHIBITED_LABEL_NAMES)
    assert all(
        not (definition.labels & PROHIBITED_LABEL_NAMES)
        for definition in METRICS.values()
    )
    with pytest.raises(ValueError, match="prohibited"):
        first.increment(
            "january_http_requests_total",
            route="/health",
            method="GET",
            status="2xx",
            request_id="unsafe",
        )


def test_usage_cost_is_reported_or_unknown_without_fabrication() -> None:
    recorder = InMemoryMetricsRecorder()
    record_provider_usage(
        recorder,
        provider="openai",
        model="test-model",
        input_tokens=100,
        output_tokens=25,
        total_tokens=125,
        pricing={
            "openai:test-model": {
                "input_microusd_per_million": 2_000_000,
                "output_microusd_per_million": 4_000_000,
            }
        },
    )
    record_provider_usage(
        recorder,
        provider="openai",
        model="unknown",
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        pricing={},
    )

    assert (
        recorder.counter_value(
            "january_model_tokens_total", provider="openai", token_type="input"
        )
        == 100
    )
    assert recorder.counter_value(
        "january_model_estimated_cost_usd_total", provider="openai"
    ) == pytest.approx(0.0003)
    assert (
        recorder.counter_value(
            "january_model_cost_estimate_total",
            provider="openai",
            outcome="unavailable",
        )
        == 1
    )


def test_operational_log_is_allowlisted_and_correlation_restores() -> None:
    logger = logging.getLogger("january.test.observability")
    record = logging.LogRecord(
        logger.name, logging.INFO, __file__, 1, "ignored", (), None
    )
    token = set_correlation_id("correlation-1")
    try:
        logger.handle(record)
        operational_event(
            logger, "provider_result", provider="openai", outcome="success"
        )
        nested = set_correlation_id("correlation-2")
        reset_correlation_id(nested)
        assert get_correlation_id() == "correlation-1"
    finally:
        reset_correlation_id(token)
    assert get_correlation_id() is None
    with pytest.raises(ValueError, match="unsupported"):
        operational_event(logger, "unsafe", text="fixture-message-text")


def test_http_metrics_use_route_template_and_request_ids_still_work() -> None:
    app = create_app(Settings(environment="test", metrics_enabled=True))
    app.state.database = FakeDatabase(ready=True)
    response = AppClient(app).get("/health", headers={"X-Request-ID": "request-1"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-1"
    body = app.state.telemetry.exposition()
    assert 'route="/health"' in body
    assert "request-1" not in body


def test_loopback_exporter_exposes_prometheus_text_only() -> None:
    async def scenario() -> str:
        recorder = InMemoryMetricsRecorder()
        recorder.increment(
            "january_http_requests_total", route="/health", method="GET", status="2xx"
        )
        exporter = MetricsHttpExporter(recorder, "127.0.0.1", 0)
        await exporter.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", exporter.port)
            writer.write(b"GET /metrics HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
            return response.decode()
        finally:
            await exporter.close()

    response = asyncio.run(scenario())
    assert "200 OK" in response
    assert "january_http_requests_total" in response
    assert "fixture-message-text" not in response
