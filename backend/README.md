# Backend

The January backend is a Python 3.12 FastAPI application factory. Its current
surface is intentionally limited to operational endpoints; Telegram, database,
queue, and model-provider integrations begin in later specifications.

Run locally from the repository root:

```bash
uv run uvicorn app.main:app --app-dir backend --reload
```

Run `./scripts/validate.sh` from a normal shell after installing `uv`. It uses
`uv` from `PATH`, with `.tools/uv` as an optional repository-local fallback.

Every response includes `X-Request-ID`. A syntactically valid incoming value is
preserved; otherwise one is generated. Unhandled failures return a safe JSON
error with the same request ID.
