# Product Docs

This directory contains current consumer-product behavior derived from real
accepted intent. Harness deliberately ships no fake product domains.

When a user provides a product specification, derive smaller living documents
here instead of keeping one growing specification as the operating manual. Name
files after actual product domains, such as `overview.md`, `billing.md`,
`permissions.md`, or `api-conventions.md`.

## Current Product Contract

No consumer-specific product contract is shipped in this generic directory.
The upstream `repository-harness` contract lives in the root README, current
workflow and architecture documents, lasting decisions, optional orchestration
contract, implementation, and executable tests.

## Accepted Specifications

- [SPEC-002 Database and Persistence](specs/SPEC-002-database-and-persistence.md)
- [SPEC-003 Telegram Platform Adapter](specs/SPEC-003-telegram-platform-adapter.md)
- [SPEC-004 Telegram Ingress, Queue, and Idempotency](specs/SPEC-004-telegram-ingress-queue-idempotency.md)
- [SPEC-005 Conversation Domain and Context](specs/SPEC-005-conversation-domain-and-context.md)
- [SPEC-006 LLM Provider and Response Planning](specs/SPEC-006-llm-provider-and-response-planning.md)
- [SPEC-007 Outbound Actions, Delivery, and Idempotency](specs/SPEC-007-outbound-actions-delivery-idempotency.md)
- [SPEC-008 Operator Bootstrap and End-to-End Demo](specs/SPEC-008-operator-bootstrap-end-to-end-demo.md)
- [SPEC-009 Personality Profiles and Group Configuration](specs/SPEC-009-personality-profiles-and-group-configuration.md)
- [SPEC-010 Telegram Administration Commands and User Preferences](specs/SPEC-010-telegram-administration-commands-and-user-preferences.md)
- [SPEC-011 Explicit Memory, Privacy, and Retention](specs/SPEC-011-explicit-memory-privacy-retention.md)
- [SPEC-012 Safety Policy and Distributed Rate Limiting](specs/SPEC-012-safety-policy-and-distributed-rate-limiting.md)
- [SPEC-013 Zalo Feasibility Spike and Capability Matrix](specs/SPEC-013-zalo-feasibility-spike-and-capability-matrix.md)
- [SPEC-014 Zalo Operator Verification Gate](specs/SPEC-014-zalo-operator-verification-gate.md)
- [SPEC-015 Telegram MVP Observability and Operational Telemetry](specs/SPEC-015-telegram-observability-and-operational-telemetry.md)
- [SPEC-016 Telegram Operational Reliability, Recovery, and Scale](specs/SPEC-016-telegram-operational-reliability-recovery-and-scale.md)
- [SPEC-017 Telegram Ambient Selective Participation](specs/SPEC-017-telegram-ambient-selective-participation.md)
- [SPEC-018 Telegram Conversation Summaries and Bounded Context Compression](specs/SPEC-018-telegram-conversation-summaries-and-context-compression.md)
- [SPEC-019 Explicit Memory Semantic Retrieval and Qdrant Derived Index](specs/SPEC-019-explicit-memory-semantic-retrieval-and-qdrant.md)
- [SPEC-020 Production Deployment, Secrets, and Runtime Operations](specs/SPEC-020-production-deployment-secrets-and-runtime-operations.md)
- [SPEC-021 Authenticated Operator and Group Administration Control Plane](specs/SPEC-021-authenticated-operator-and-group-administration-control-plane.md)
- [SPEC-022 Telegram Production Integration and Live Acceptance](specs/SPEC-022-telegram-production-integration-and-live-acceptance.md)
- [SPEC-023 Production Observability, SLOs, Alerting, and Incident Operations](specs/SPEC-023-production-observability-slos-alerting-and-incident-operations.md)
- [SPEC-024 Safety Moderation, Abuse Prevention, and User Protection](specs/SPEC-024-safety-moderation-abuse-prevention-and-user-protection.md)
- [Telegram Capabilities](telegram-capabilities.md)

## Roadmap State

SPEC-014 is `DEFERRED / BLOCKED_ON_EXTERNAL_PREREQUISITE` pending a dedicated
nonproduction Zalo OA/application. Its outstanding live checks do not block
the Telegram MVP. SPEC-001 through SPEC-022 are complete; SPEC-022 has been
approved and committed, with its live Telegram acceptance remaining an
externally gated operational step. SPEC-023 is implemented as an approved
candidate: the production observability contract (SLI catalog, SLO targets and
error budget over a rolling 28-day window, content-safe alert rules, and
incident operations) is declared in code and documentation with no schema
migration, pending Product Owner and operating-owner approval of the proposed
objectives and notification channels. SPEC-024 is implemented as an approved
candidate: the safety moderation, abuse prevention, and user protection
contract is enforced in the response-planning and outbound-delivery workers,
exposed through the `/safety`, `/protect`, and `/unprotect` commands and
content-free control-plane review endpoints, and backed by the additive
`0015_safety_moderation` migration and `safety_risk` alert rules; its threshold
objectives remain operating-owner approvals.

## Update Rule

When behavior changes:

1. Update the affected product document when the expected behavior changed.
2. Update the active execution plan when complex work uses one.
3. Add a lasting decision only when future work must inherit a consequential
   product, architecture, data, security, compatibility, or validation choice.
4. Add or update executable proof that exercises the behavior.

Bounded changes do not require a story packet, proof-matrix row, or Harness CLI
mutation.
