#!/bin/bash

# Runs the share-card bot (long polling; stays running).
#   Send an article URL to the bot in Telegram, get back a 1080x1080 share card.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$PROJECT_DIR"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

exec python3 card_bot.py

# --- systemd ---
#
# /etc/systemd/system/card-bot.service:
#
# [Unit]
# Description=Telegram share-card bot
# After=network-online.target
# Wants=network-online.target
#
# [Service]
# User=<your user>
# ExecStart=/path/to/web-fetch-notify-bot/run_card_bot.sh
# Restart=always
# RestartSec=10
#
# [Install]
# WantedBy=multi-user.target
#
# sudo systemctl daemon-reload && sudo systemctl enable --now card-bot
# journalctl -u card-bot -f
