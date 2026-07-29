# Telegram Capabilities

## Implemented In SPEC-003 And SPEC-004

- `getMe` identity verification.
- `sendMessage`, including reply parameters and safe optional send controls.
- `sendSticker` using an existing Telegram asset reference.
- `getChatMember`; information for other users can depend on bot administrator
  access granted by Telegram.
- Typed `getUpdates`, `setWebhook`, `deleteWebhook`, and `getWebhookInfo`.
- Secure webhook ingress and controlled polling into one durable inbox.
- PostgreSQL deduplication and Redis Streams outbox publication.

## Deferred

- Later specifications: mention policy, sticker selection, persistence writes,
  retry policy, authorization policy, and conversation behavior.

## Operator Configuration

Set `JANUARY_TELEGRAM_ENABLED=true` and provide the token outside source
control. `./scripts/verify-telegram.sh` performs only an explicit `getMe`
check. Normal startup, CI, and tests do not require a Telegram credential.

For configured operators, `scripts/telegram-webhook.sh register|inspect|remove`
manages webhook state explicitly. `remove --drop-pending-updates` is the only
form that requests Telegram to discard pending updates.
