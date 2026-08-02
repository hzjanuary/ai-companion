"""Owned, bounded Prometheus-compatible telemetry registry and exporter."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from typing import Any, Final, cast

from app.application.ports.telemetry import MetricsRecorder

PROHIBITED_LABEL_NAMES: Final = frozenset(
    {
        "request_id",
        "correlation_id",
        "conversation_id",
        "participant_id",
        "message_id",
        "planning_job_id",
        "response_plan_id",
        "outbound_action_id",
        "command_job_id",
        "telegram_update_id",
        "telegram_chat_id",
        "telegram_user_id",
        "telegram_message_id",
        "username",
        "text",
        "prompt",
        "memory",
        "url",
        "exception",
        "secret",
        "token",
        "model",
        "provider_request_id",
    }
)


@dataclass(frozen=True)
class MetricDefinition:
    kind: str
    labels: frozenset[str]


METRICS: Final[dict[str, MetricDefinition]] = {
    "january_http_requests_total": MetricDefinition(
        "counter", frozenset({"route", "method", "status"})
    ),
    "january_http_request_duration_seconds": MetricDefinition(
        "histogram", frozenset({"route", "method", "status"})
    ),
    "january_telegram_updates_total": MetricDefinition(
        "counter", frozenset({"outcome", "transport"})
    ),
    "january_conversation_eligibility_total": MetricDefinition(
        "counter", frozenset({"eligible", "reason"})
    ),
    "january_planning_jobs_total": MetricDefinition("counter", frozenset({"outcome"})),
    "january_model_requests_total": MetricDefinition(
        "counter", frozenset({"provider", "outcome"})
    ),
    "january_model_request_duration_seconds": MetricDefinition(
        "histogram", frozenset({"provider", "outcome"})
    ),
    "january_model_tokens_total": MetricDefinition(
        "counter", frozenset({"provider", "token_type"})
    ),
    "january_model_usage_reports_total": MetricDefinition(
        "counter", frozenset({"provider", "outcome"})
    ),
    "january_model_estimated_cost_usd_total": MetricDefinition(
        "counter", frozenset({"provider"})
    ),
    "january_model_cost_estimate_total": MetricDefinition(
        "counter", frozenset({"provider", "outcome"})
    ),
    "january_response_plan_validation_total": MetricDefinition(
        "counter", frozenset({"outcome"})
    ),
    "january_outbound_actions_total": MetricDefinition(
        "counter", frozenset({"kind", "outcome"})
    ),
    "january_telegram_send_failures_total": MetricDefinition(
        "counter", frozenset({"kind", "error_class"})
    ),
    "january_delivery_duration_seconds": MetricDefinition(
        "histogram", frozenset({"kind", "outcome"})
    ),
    "january_safety_decisions_total": MetricDefinition(
        "counter", frozenset({"stage", "outcome", "reason"})
    ),
    "january_rate_limit_events_total": MetricDefinition(
        "counter", frozenset({"operation", "scope", "result"})
    ),
    "january_recovery_events_total": MetricDefinition(
        "counter", frozenset({"work_kind", "operation", "outcome", "reason"})
    ),
    "january_dead_letter_events_total": MetricDefinition(
        "counter", frozenset({"work_kind", "reason"})
    ),
    "january_quarantine_events_total": MetricDefinition(
        "counter", frozenset({"work_kind", "reason"})
    ),
    "january_provider_concurrency_events_total": MetricDefinition(
        "counter", frozenset({"provider", "outcome"})
    ),
    "january_ambient_decisions_total": MetricDefinition(
        "counter", frozenset({"outcome", "profile", "policy"})
    ),
    "january_summary_jobs_total": MetricDefinition(
        "counter", frozenset({"outcome", "schema"})
    ),
    "january_summary_generation_total": MetricDefinition(
        "counter", frozenset({"outcome", "provider", "schema"})
    ),
    "january_summary_context_usage_total": MetricDefinition(
        "counter", frozenset({"outcome", "schema"})
    ),
    "january_summary_retention_events_total": MetricDefinition(
        "counter", frozenset({"outcome"})
    ),
    "january_worker_operations_total": MetricDefinition(
        "counter", frozenset({"runtime", "operation", "outcome"})
    ),
    "january_worker_operation_duration_seconds": MetricDefinition(
        "histogram", frozenset({"runtime", "operation", "outcome"})
    ),
}


class InMemoryMetricsRecorder:
    """A registry owned by one application/runtime instance, never global."""

    def __init__(self) -> None:
        self._counters: defaultdict[tuple[str, tuple[tuple[str, str], ...]], float] = (
            defaultdict(float)
        )
        self._histograms: defaultdict[
            tuple[str, tuple[tuple[str, str], ...]], list[float]
        ] = defaultdict(list)

    def increment(self, metric: str, amount: float = 1.0, /, **labels: str) -> None:
        definition, normalized = self._validate(metric, labels)
        if definition.kind != "counter":
            raise ValueError(f"{metric} is not a counter")
        if not isfinite(amount) or amount < 0:
            raise ValueError("metric counter amount must be finite and nonnegative")
        self._counters[(metric, normalized)] += amount

    def observe(self, metric: str, value: float, /, **labels: str) -> None:
        definition, normalized = self._validate(metric, labels)
        if definition.kind != "histogram":
            raise ValueError(f"{metric} is not a histogram")
        if not isfinite(value) or value < 0:
            raise ValueError("metric observation must be finite and nonnegative")
        self._histograms[(metric, normalized)].append(value)

    def counter_value(self, metric: str, /, **labels: str) -> float:
        _, normalized = self._validate(metric, labels)
        return self._counters[(metric, normalized)]

    def histogram_values(self, metric: str, /, **labels: str) -> tuple[float, ...]:
        _, normalized = self._validate(metric, labels)
        return tuple(self._histograms[(metric, normalized)])

    def exposition(self) -> str:
        lines: list[str] = []
        for metric, definition in METRICS.items():
            lines.append(f"# TYPE {metric} {definition.kind}")
            values = (
                self._counters if definition.kind == "counter" else self._histograms
            )
            for (name, labels), raw in sorted(values.items()):
                if name != metric:
                    continue
                rendered = _render_labels(labels)
                if definition.kind == "counter":
                    lines.append(f"{metric}{rendered} {raw:g}")
                else:
                    observations = cast(list[float], raw)
                    lines.append(f"{metric}_count{rendered} {len(observations)}")
                    lines.append(f"{metric}_sum{rendered} {sum(observations):g}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _validate(
        metric: str, labels: dict[str, str]
    ) -> tuple[MetricDefinition, tuple[tuple[str, str], ...]]:
        definition = METRICS.get(metric)
        if definition is None:
            raise ValueError(f"unknown metric: {metric}")
        names = set(labels)
        if names & PROHIBITED_LABEL_NAMES:
            raise ValueError("prohibited metric label name")
        if names != definition.labels:
            raise ValueError(f"invalid labels for {metric}")
        if any(not value or len(value) > 80 for value in labels.values()):
            raise ValueError("metric label values must be bounded and nonblank")
        return definition, tuple(sorted(labels.items()))


def _render_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    values = ",".join(
        f'{name}="{value.replace("\\", "\\\\").replace(chr(34), '\\\\"')}"'
        for name, value in labels
    )
    return "{" + values + "}"


class MetricsHttpExporter:
    """Small loopback-only HTTP exporter for one owned registry."""

    def __init__(self, recorder: MetricsRecorder, host: str, port: int) -> None:
        self._recorder = recorder
        self._host = host
        self._port = port
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, self._host, self._port)
        sockets = cast(Any, self._server).sockets
        if sockets:
            self._port = int(sockets[0].getsockname()[1])

    @property
    def port(self) -> int:
        return self._port

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _serve(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request = await reader.readline()
            while await reader.readline() not in {b"\r\n", b"\n", b""}:
                pass
            if request.startswith(b"GET /metrics "):
                body = self._recorder.exposition().encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; version=0.0.4\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode()
                    + body
                )
            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
