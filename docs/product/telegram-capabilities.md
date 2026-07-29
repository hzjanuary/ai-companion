# Telegram Capabilities

## Implemented In SPEC-003

- `getMe` identity verification.
- `sendMessage`, including reply parameters and safe optional send controls.
- `sendSticker` using an existing Telegram asset reference.
- `getChatMember`; information for other users can depend on bot administrator
  access granted by Telegram.

## Deferred

- SPEC-004: polling, webhook lifecycle, incoming updates, queues, and
  idempotency.
- Later specifications: mention policy, sticker selection, persistence writes,
  retry policy, authorization policy, and conversation behavior.

## Operator Configuration

Set `JANUARY_TELEGRAM_ENABLED=true` and provide the token outside source
control. `./scripts/verify-telegram.sh` performs only an explicit `getMe`
check. Normal startup, CI, and tests do not require a Telegram credential.
