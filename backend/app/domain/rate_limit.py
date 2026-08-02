"""Platform-independent distributed rate-limit contracts."""

from dataclasses import dataclass
from enum import StrEnum


class RateLimitOperation(StrEnum):
    GENERATION = "generation"
    DELIVERY = "delivery"
    EMBEDDING = "embedding"


class RateLimitScope(StrEnum):
    DEPLOYMENT = "deployment"
    CONNECTION = "connection"
    CONVERSATION = "conversation"
    PARTICIPANT = "participant"
    PROVIDER = "provider"


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    scope: RateLimitScope
    identifier: str
    limit: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limiting_scope: RateLimitScope | None = None
    retry_after_seconds: int | None = None
