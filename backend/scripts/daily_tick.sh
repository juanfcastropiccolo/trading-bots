#!/bin/bash
# Tick diario del paper trader de momentum. Pensado para crontab (21:00 ART
# = 00:00 UTC, cierre de la vela diaria). Además pushea el estado a GitHub
# para que la rutina de análisis en la nube pueda leerlo.
set -e

REPO="/Users/juanfcastropiccolo/Documents/trading-bots"
PYTHON="/opt/miniconda3/envs/google-adk-agents/bin/python"
LOG="$REPO/backend/data/momentum_paper.log"

cd "$REPO/backend/scripts"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG"
"$PYTHON" momentum_paper.py >> "$LOG" 2>&1

cd "$REPO"
git add -f backend/data/momentum_state.json
if ! git diff --cached --quiet; then
    git commit -m "chore: momentum paper state $(date '+%Y-%m-%d')" >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1 || echo "push falló (se reintenta mañana)" >> "$LOG"
fi
