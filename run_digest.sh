#!/bin/bash

# Runs the LLM news digest.
#   ./run_digest.sh collect   -> gather article titles (run hourly)
#   ./run_digest.sh send      -> screen, summarize and send the digest (run daily at 16:00 KST)

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$PROJECT_DIR"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python3 digest_main.py "$@"

# --- Cron Job Instructions ---
#
# cron uses the server's time zone. Ubuntu's cron ignores CRON_TZ, so either set the server
# to KST (sudo timedatectl set-timezone Asia/Seoul && sudo systemctl restart cron) and use:
#
# 0 * * * *   /path/to/web-fetch-notify-bot/run_digest.sh collect >> /path/to/web-fetch-notify-bot/cron.log 2>&1
# 50 15 * * * /path/to/web-fetch-notify-bot/run_digest.sh collect >> /path/to/web-fetch-notify-bot/cron.log 2>&1
# 0 16 * * *  /path/to/web-fetch-notify-bot/run_digest.sh send    >> /path/to/web-fetch-notify-bot/cron.log 2>&1
#
# or keep UTC and shift the times by -9 hours (16:00 KST = 07:00 UTC):
#
# 50 6 * * * /path/to/web-fetch-notify-bot/run_digest.sh collect >> /path/to/web-fetch-notify-bot/cron.log 2>&1
# 0 7 * * *  /path/to/web-fetch-notify-bot/run_digest.sh send    >> /path/to/web-fetch-notify-bot/cron.log 2>&1
