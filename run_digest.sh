#!/bin/bash

# Runs the LLM news digest.
#   ./run_digest.sh collect   -> gather article titles (run hourly)
#   ./run_digest.sh send      -> screen, summarize and send the digest (run daily at 18:00 KST)

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$PROJECT_DIR"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python3 digest_main.py "$@"

# --- Cron Job Instructions ---
#
# Servers often run in UTC, so pin the schedule to KST with CRON_TZ:
#
# CRON_TZ=Asia/Seoul
# 0 * * * *  /path/to/web-fetch-notify-bot/run_digest.sh collect >> /path/to/web-fetch-notify-bot/cron.log 2>&1
# 50 17 * * * /path/to/web-fetch-notify-bot/run_digest.sh collect >> /path/to/web-fetch-notify-bot/cron.log 2>&1
# 0 18 * * * /path/to/web-fetch-notify-bot/run_digest.sh send    >> /path/to/web-fetch-notify-bot/cron.log 2>&1
