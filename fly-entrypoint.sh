#!/bin/sh
set -eu

if [ -z "${DISCORD_BOT_TOKEN:-}" ]; then
    echo "DISCORD_BOT_TOKEN must be configured as a Fly secret." >&2
    exit 1
fi

mkdir -p /data
export STATE_FILE_PATH="${STATE_FILE_PATH:-/data/seen_codes.json}"
export DASHBOARD_CONFIG_FILE="${DASHBOARD_CONFIG_FILE:-/data/routes_config.json}"
export USER_PREFERENCES_FILE="${USER_PREFERENCES_FILE:-/data/user_prefs.json}"

if [ ! -f "$DASHBOARD_CONFIG_FILE" ]; then
    printf '{"settings":{"realtime_monitoring_enabled":false}}\n' > "$DASHBOARD_CONFIG_FILE"
fi

exec python main.py bot
