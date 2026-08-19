#!/bin/sh

# Background startup routine used by the macOS launcher.
set -eu

PROJECT_PATH="/Users/tg/trade-intelligence-platform"
LOG_PATH="/tmp/trade-intelligence-dashboard.log"
PORT="8501"

if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    open "http://localhost:$PORT"
    exit 0
fi

cd "$PROJECT_PATH"

if ! python3 -c 'import streamlit, pandas, plotly'; then
    python3 -m pip install -r requirements.txt
fi

python3 -m scraper.scraper --source all
nohup python3 -m streamlit run dashboard/app.py --server.headless true >"$LOG_PATH" 2>&1 &

attempt=0
while [ "$attempt" -lt 20 ]; do
    if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        open "http://localhost:$PORT"
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done

exit 1
