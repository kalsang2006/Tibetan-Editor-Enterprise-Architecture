#!/usr/bin/env bash
# Restart the TEEA daemon (PowerShell Start-Process) and verify the fix.
set -u
cd "$(dirname "$0")/.." || exit 1

echo "=== stopping any daemon on 50505 ==="
PID=$(netstat -ano 2>/dev/null | grep ':50505' | grep LISTENING | awk '{print $NF}' | head -1)
if [ -n "$PID" ]; then
  echo "killing PID $PID"
  powershell -NoProfile -Command "Stop-Process -Id $PID -Force -ErrorAction SilentlyContinue"
  sleep 3
fi

echo "=== starting fresh daemon ==="
powershell -NoProfile -ExecutionPolicy Bypass -File scratch/restart_daemon.ps1

echo "=== waiting for readiness ==="
up=0
for i in $(seq 1 150); do
  if netstat -ano 2>/dev/null | grep -q ':50505.*LISTENING'; then
    echo "daemon listening after ~$((i * 2))s"
    up=1
    break
  fi
  sleep 2
done

if [ "$up" -ne 1 ]; then
  echo "=== daemon did not become ready ==="
  echo "--- stdout ---"; tail -40 scratch/daemon_start.log 2>/dev/null
  echo "--- stderr ---"; tail -40 scratch/daemon_err.log 2>/dev/null
  exit 1
fi

echo "=== startup log ==="
tail -6 scratch/daemon_start.log 2>/dev/null

echo "=== verification (user's PowerShell-equivalent request) ==="
./.venv/Scripts/python scratch/verify_daemon.py
