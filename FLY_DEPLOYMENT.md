# Fly.io deployment

This bot runs as a single always-on worker; it does not expose a web port. State files are stored on the `/data` volume, while local `.env`, route settings, and seen-code history are excluded from the image.

## Setup

1. Install `flyctl`, sign in with `fly auth login`, and confirm Fly billing in your account.
2. In the Fly dashboard, create the app named in `fly.toml` if it does not exist. Set `DISCORD_BOT_TOKEN` as a Fly secret and `OWNER_USER_ID` as an environment variable or secret. Add optional Telegram, OCR, or Supabase credentials only if you use those integrations.
3. Keep the local bot running while preparing the app. Stop the local instance immediately before running `fly deploy`; the hosted process uses the same Discord bot identity.
4. From the repository directory, run `fly deploy`. If Fly asks for a payment method, add it only in Fly's own account dashboard.
5. On the first hosted boot, monitoring is paused. With the Fly machine running, seed its persistent deduplication state without sending notifications:

   ```powershell
   fly ssh console -C "python main.py check-once"
   ```

6. Enable monitoring from the Discord `/dashboard` after confirming the hosted bot is responding. Configure notification routes there; the local `routes_config.json` is intentionally not uploaded.

`seen_codes.json`, dashboard routes, and saved calculator preferences persist on the Fly volume. The first seed scan builds fresh hosted history from currently available recent drops; old local history is not copied.

## Cost and operation

Fly.io is not guaranteed to be free. Its current Free plan includes $5 of monthly usage credit after adding a payment card; excess usage is billed. At current `iad` rates, a continuously running 512 MB shared-CPU machine is about $3.69 per 30 days, and the 1 GB volume is about $0.15 per month, before outbound data transfer. The base estimate is about $3.84, so actual use may exceed the credit. Check the [official pricing page](https://docs.fly.io/about/pricing/) and your Fly billing dashboard; do not add a card unless you accept possible charges.

Useful commands:

```powershell
fly status
fly logs
fly machine restart
```

Never put bot tokens, webhook URLs, or Telegram credentials in GitHub or in this file. Enter secrets directly in Fly's authenticated dashboard or CLI, not in this chat.
