---
name: atlassian-sync
description: Triggers a fresh Confluence + Jira reference sync via the local API and reports the result. Use when reference data seems stale or before starting a new analysis session.
disable-model-invocation: true
---

Run the following steps:

1. Start the sync:
```bash
curl -s -X POST http://localhost:5002/api/sources/sync
```

2. Poll until complete (sync can take 30–120 seconds):
```bash
for i in $(seq 1 30); do
  STATUS=$(curl -s http://localhost:5002/api/sources/sync/status)
  RUNNING=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('running', True))")
  if [ "$RUNNING" = "False" ]; then
    echo "$STATUS" | python3 -m json.tool
    break
  fi
  echo "Senkronizasyon devam ediyor... ($i)"
  sleep 5
done
```

3. Report:
- How many Confluence pages were synced (reference/confluence/ file count)
- How many Jira issues were synced (reference/jira/ file count)
- Any errors from the log field

If the app is not running (connection refused), say: "Uygulama çalışmıyor. `source venv/bin/activate && python app.py` ile başlatın."
