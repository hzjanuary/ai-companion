"""Platform-independent durable outbound delivery values."""

from enum import StrEnum


class OutboundActionKind(StrEnum):
    TEXT = "text"
    STICKER = "sticker"


class OutboundActionStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    DELIVERED = "delivered"
    SKIPPED = "skipped"
    PERMANENTLY_FAILED = "permanently_failed"
    DELIVERY_UNKNOWN = "delivery_unknown"


class DeliveryAttemptStatus(StrEnum):
    STARTED = "started"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class DeliveryCertainty(StrEnum):
    NOT_SENT = "not_sent"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"
