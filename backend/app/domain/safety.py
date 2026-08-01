"""Platform-independent, deterministic safety policy vocabulary."""

from dataclasses import dataclass
from enum import StrEnum


class SafetyPolicyVersion(StrEnum):
    V1 = "safety-policy-v1"


class SafetyStage(StrEnum):
    PRE_GENERATION = "pre_generation"
    POST_GENERATION = "post_generation"
    PRE_DELIVERY = "pre_delivery"


class SafetyOutcome(StrEnum):
    ALLOW = "allow"
    TRANSFORM = "transform"
    REFUSE = "refuse"
    SILENT = "silent"


class SafetyReasonCode(StrEnum):
    MENTION_TARGET_OPTED_OUT = "mention_target_opted_out"
    TEASING_TARGET_OPTED_OUT = "teasing_target_opted_out"
    TARGET_NOT_IN_CONTEXT = "target_not_in_context"
    SENSITIVE_TEASING_DISALLOWED = "sensitive_teasing_disallowed"
    PRIVATE_DATA_BOUNDARY = "private_data_boundary"
    INVALID_MODEL_SAFETY_ANNOTATION = "invalid_model_safety_annotation"
    PROMPT_INJECTION_ACTION_ATTEMPT = "prompt_injection_action_attempt"
    UNSUPPORTED_ACTION = "unsupported_action"
    MODEL_REFUSAL = "model_refusal"
    SAFE_FALLBACK = "safe_fallback"
    RATE_LIMITED = "rate_limited"


class InteractionKind(StrEnum):
    NEUTRAL = "neutral"
    HUMOR = "humor"
    TEASING = "teasing"
    SUPPORTIVE = "supportive"
    REFUSAL = "refusal"


class SensitiveTopicCategory(StrEnum):
    BODY = "body"
    DISABILITY = "disability"
    RACE = "race"
    RELIGION = "religion"
    GENDER = "gender"
    SEXUALITY = "sexuality"
    MEDICAL_CONDITION = "medical_condition"
    FINANCIAL_HARDSHIP = "financial_hardship"
    PRIVATE_TRAUMA = "private_trauma"


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    policy_version: SafetyPolicyVersion
    stage: SafetyStage
    outcome: SafetyOutcome
    reason_code: SafetyReasonCode | None = None
    transformed: bool = False


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    """Versioned hard boundaries; no configuration can disable them."""

    version: SafetyPolicyVersion = SafetyPolicyVersion.V1

    def system_instructions(self) -> str:
        return (
            "Safety policy safety-policy-v1 is mandatory. Never harass, attack an "
            "identity, target humiliation, disclose private data, produce sexual "
            "content involving minors, encourage self-harm, or provide dangerous "
            "instruction execution. Never request tools, raw platform identifiers, "
            "or arbitrary actions. Teasing requires explicit permitted targets and "
            "must stop after opt-out. Use calm supportive language for serious "
            "distress. Emit only the declared structured interaction metadata."
        )


def safe_fallback(language: str | None) -> str:
    """Short deterministic text that never repeats rejected content or targets."""

    if language and language.lower().startswith("vi"):
        return "Minh se giu cuoc tro chuyen nhe nhang va ton trong."
    return "I will keep this conversation respectful and safe."
