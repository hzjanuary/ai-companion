# January Architecture

January is a modular monolith. It will grow into independently scalable API,
worker, and sender runtime processes without splitting product behavior into
services prematurely.

## Dependency Direction

```text
domain
  <- application
      <- infrastructure
          <- interface
              <- runtime surfaces
```

Dependencies point toward the left. The domain is framework-independent;
application code coordinates use cases; infrastructure implements external
ports; interfaces translate transport input and output; runtime surfaces wire
the application together.

SPEC-002 adds concrete domain records, application persistence ports, and
PostgreSQL infrastructure. It still avoids speculative modules.

## Boundary Rules

- Framework and provider clients stay outside the domain layer.
- Telegram, Zalo, LLM, database, and queue SDKs stay outside inner layers.
- Unknown external input is parsed at interfaces before it enters inner layers.
- Future model-generated actions are validated by application policy before
  execution by an adapter.
- Operational logs describe runtime behavior; product audit records are a
  separate future persistence concern.
- Current readiness reports only the running application. It does not claim
  health for future dependencies.

## Current Layout

```text
backend/app/
  core/          settings, logging, request context
  domain/        platform-independent persistence records and enums
  application/   persistence and platform-independent ingress contracts
  infrastructure/database/ async engine, models, repositories, migrations
  infrastructure/telegram/ typed Bot API HTTP adapter and Update DTOs
  infrastructure/queue/ Redis Streams ingress queue
  interface/http/ response models, routes, middleware
  runtime/       dedicated polling and outbox dispatch entry points
  main.py        application factory and API runtime entry point
```

The factory is the composition boundary. New modules are introduced only with
the first behavior that needs them.

SPEC-004 keeps Telegram raw payloads and SDK contracts in infrastructure. The
application ingress envelope is platform independent; PostgreSQL owns durable
deduplication and outbox intent; Redis Streams transports references only.

SPEC-005 consumes those references in a dedicated runtime. Telegram payloads
are normalized before application policy runs; PostgreSQL commits normalized
conversation state and the idempotency ledger before Redis acknowledgement.
Context readers return application values rather than ORM models, raw payloads,
or credentials. No LLM or outgoing-delivery dependency crosses this boundary.

SPEC-006 adds a separate response-planning runtime. Provider HTTP JSON remains
in infrastructure; application values carry only typed generation requests,
results, and safe errors. PostgreSQL leases and immutable response plans make
planning durable without claiming exactly-once generation or executing any
platform action.

SPEC-007 compiles response plans to ordered platform-independent actions in the
planning transaction. Its sender is a separate runtime: PostgreSQL owns action
leases, attempts, and outgoing-message linkage; Telegram rendering and asset
references stay in infrastructure. A send timeout or malformed post-send
response is terminal `delivery_unknown`, deliberately avoiding automatic
duplicate visible messages rather than claiming exactly-once delivery.
