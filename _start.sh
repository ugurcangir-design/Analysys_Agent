#!/bin/bash
PORT=5002
URL="http://localhost:$PORT"
cd "/Users/dt/brd-analyst-agent"

if curl -s --max-time 1 "$URL" > /dev/null 2>&1; then
    open "$URL"
    exit 0
fi

source venv/bin/activate
DESKTOP_MODE=true nohup python app.py >> /tmp/brd-agent-desktop.log 2>&1 &
disown

for i in $(seq 1 30); do
    sleep 0.5
    curl -s --max-time 1 "$URL" > /dev/null 2>&1 && break
done
open "$URL"
