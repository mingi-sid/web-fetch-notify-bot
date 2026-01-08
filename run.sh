#!/bin/bash

# This script runs the news bot.
# It is designed to be called by a cron job or executed manually.

# Set the project directory to the location of this script.
# This ensures that all relative paths (for config, data, logs) work correctly.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$PROJECT_DIR"

echo "========================================="
echo "Running News Bot at $(date)"
echo "Project Directory: $PROJECT_DIR"
echo "========================================="

# Optional: Activate a virtual environment if you use one.
# Make sure the path to your virtual environment is correct.
if [ -f ".venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
else
    echo "Virtual environment not found, using system python."
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null
then
    echo "Error: python3 could not be found. Please install Python 3."
    exit 1
fi

# Run the main Python script.
# All output will be automatically handled by the logging configuration (e.g., to console and news_bot.log).
python3 main.py

echo "========================================="
echo "News Bot run finished at $(date)"
echo "========================================="

# --- Cron Job Instructions ---
#
# To run this script automatically, use 'crontab -e' and add a line like this.
# This example runs the script every 10 minutes.
#
# */10 * * * * /path/to/your/news_bot/run.sh
#
# To log cron output to a file, you can append a redirect:
# */10 * * * * /path/to/your/news_bot/run.sh >> /path/to/your/news_bot/cron.log 2>&1
#
# Note: Using absolute paths in cron is always a good practice.
