"""Typed provider-neutral generation contract."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from app.application.context import ConversationContext
from app.domain.planning import ProviderErrorCategory, ProviderId


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    json_schema: bool
    json_object: bool
    max_output_tokens_parameter: str | None
    reports_usage: bool
    request_identifier: bool
    keyless_local: bool = False


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    planning_job_id: UUID
    context: ConversationContext
    prompt_version: str
    response_schema_version: str
    locale_hint: str
    maximum_output_tokens: int
    system_instructions: str
    user_content: str
    response_schema: dict[str, object]
    correction_attempt: int = 0
    correction_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider: ProviderId
    model: str
    structured_text: str
    provider_request_id: str | None
    usage: ProviderUsage
    latency: timedelta
    finish_reason: str | None
    refused: bool = False
    safety_blocked: bool = False


@dataclass(frozen=True, slots=True)
class ProviderError(Exception):
    category: ProviderErrorCategory
    provider: ProviderId
    model: str
    retryable: bool
    operation: str
    summary: str
    retry_after: timedelta | None = None
    provider_request_id: str | None = None

    def __str__(self) -> str:
        return f"{self.provider.value} {self.operation}: {self.category.value}"


class ModelProvider(Protocol):
    provider_id: ProviderId
    model: str
    capabilities: ProviderCapabilities

    async def generate(self, request: GenerationRequest) -> ProviderResult: ...

    async def aclose(self) -> None: ...
