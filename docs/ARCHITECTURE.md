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
  application/   persistence ports
  infrastructure/database/ async engine, models, repositories, migrations
  interface/http/ response models, routes, middleware
  main.py        application factory and runtime entry point
```

The factory is the composition boundary. New modules are introduced only with
the first behavior that needs them.
