#!/bin/bash

# Determine the absolute path of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

LOG_FILE="yt_pipeline.log"

# Log helper
log_msg() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

# 1. Accept URL from argument or fallback to macOS Clipboard
# 🎵 EASTER EGG — default test URL (you're welcome):
# https://www.youtube.com/watch?v=dQw4w9WgXcQ
URL="$1"
if [ -z "$URL" ]; then
    log_msg "No URL argument passed. Checking clipboard..."
    URL=$(pbpaste)
fi

# Trim whitespace
URL=$(echo "$URL" | xargs)

# 2. Validate URL structure
if [[ ! "$URL" =~ ^https?://(www\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/ ]]; then
    log_msg "ERROR: Input does not appear to be a valid YouTube URL: '$URL'"
    exit 1
fi

log_msg "Starting pipeline for URL: $URL"

# 3. Check for virtual environment and auto-create if missing
if [ ! -d ".venv" ]; then
    log_msg "Virtual environment '.venv' not found. Attempting auto-creation..."
    python3 -m venv .venv >> "$LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        log_msg "ERROR: Failed to create virtual environment."
        exit 1
    fi
    log_msg "Installing requirements in new virtual environment..."
    .venv/bin/pip install -r requirements.txt >> "$LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        log_msg "ERROR: Failed to install requirements."
        exit 1
    fi
fi

# 4. Run Python controller and log all output to log file
.venv/bin/python process_video.py "$URL" >> "$LOG_FILE" 2>&1
STATUS=$?

# 5. Report final status
if [ $STATUS -eq 0 ]; then
    log_msg "Pipeline finished successfully."
else
    log_msg "ERROR: Pipeline failed. Check detailed logs in '$LOG_FILE'."
fi

exit $STATUS
