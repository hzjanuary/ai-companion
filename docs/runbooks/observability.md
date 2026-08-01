# Observability

Telemetry recording and export are independent. Both default to disabled.
When export is enabled it binds to `127.0.0.1:9464`; use a distinct local port
for each runtime process. Do not expose this endpoint beyond loopback without
an operator-owned network boundary.

```bash
JANUARY_METRICS_ENABLED=true \
JANUARY_METRICS_EXPORT_ENABLED=true \
JANUARY_METRICS_PORT=9464 \
uv run uvicorn app.main:app --app-dir backend
curl http://127.0.0.1:9464/metrics
```

The Prometheus-compatible text catalog uses `january_` names for HTTP,
ingress, eligibility, planning, provider, response-plan, outbound, safety,
rate-limit, and worker operation measurements. It never contains text,
prompts, memory, raw platform IDs, request/correlation IDs, usernames, URLs,
tokens, secrets, or exception bodies as labels or exposition values.

`request_id` identifies one HTTP request. A correlation ID is a separate opaque
durable-work root and is logged, never used as a metric label. JSON logs are
allowlisted operational events and omit product content and credentials.

Provider usage is counted only when the provider reports it. Configure optional
prices as JSON with integer `input_microusd_per_million` and
`output_microusd_per_million` rates keyed by `provider:model`. Estimates are
not invoices; absent rate or usage is unknown. CI does not claim production
latency/SLO compliance; component-duration histograms provide the evidence for
operators to measure it in their own environment.

Run `./scripts/validate-observability.sh` for no-network telemetry proof.
