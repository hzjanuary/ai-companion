# Telegram Administration Commands

Use only a dedicated test bot and a private test group. Start the guarded demo
topology with `./scripts/january-demo.sh up --confirm-live-demo`; it starts the
separate command worker only when `.env.demo` explicitly enables it.

Run `/help` and `/status`. As an ordinary member run `/quiet` and confirm the
reply denies the change. As a current Telegram administrator run `/mode
mention_and_name`, `/quiet`, and `/resume`; inspect the durable command job,
revision, response plan, and normal outbound delivery state. Test `/mentions
off` and `/teasing off` from a member account, then confirm only that account's
preferences change.

Never use this runbook to register Telegram command menus, change profile
content, expose tokens, or test in a production group. Command menu management
is deferred; visibility does not grant authorization.
