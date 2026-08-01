# Deployment

Before deployment run the canonical validators, take a PostgreSQL backup, check
schema compatibility, and verify required secret *presence* without printing
values. Preflight that Telegram uses exactly one of polling or webhook mode.

Start PostgreSQL, Redis, API, dispatcher, conversation worker, command worker,
planning worker, outbound worker, then retention worker. Configure rate limits
and provider concurrency independently. Before restarting after an incident,
inspect dead letters and quarantines. Roll back application code when possible;
database downgrade is an exceptional, explicitly scoped recovery action.
