"""Pure explicit-memory contracts and validation."""

import re
import unicodedata
from dataclasses import dataclass

from app.domain.persistence import MemoryKind, MemoryScope, MemoryVisibility


class MemoryValidationError(ValueError):
    """Explicit memory content is not safe to persist."""


_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ExplicitMemoryDraft:
    content: str
    kind: MemoryKind
    scope: MemoryScope
    visibility: MemoryVisibility = MemoryVisibility.SAME_CONVERSATION
    confidence: float = 1.0


def normalize_explicit_memory(content: str, scope: MemoryScope) -> ExplicitMemoryDraft:
    """Normalize only user-command content; no inference or extraction occurs."""

    normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", content)).strip()
    if not normalized or len(normalized) > 500:
        raise MemoryValidationError("memory content must contain 1-500 characters")
    if any(ord(character) < 32 for character in normalized):
        raise MemoryValidationError("memory content contains a control character")
    return ExplicitMemoryDraft(
        content=normalized, kind=MemoryKind.EXPLICIT_FACT, scope=scope
    )
