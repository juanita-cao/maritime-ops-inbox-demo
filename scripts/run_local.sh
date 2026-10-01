#!/usr/bin/env bash
# Start the backend (and optionally the frontend) on one dataset.
#   scripts/run_local.sh mock            backend on port 8000 with the mock data
#   scripts/run_local.sh desanitized     backend with the original private data
#   scripts/run_local.sh mock --front    also start the frontend (port 5173)
# The chat model is gpt-4o-mini + gpt-5.5 as "Hybrid" unless E16_CHAT_OPTION says otherwise; drafts of the
# operation guides are on. Stop with Ctrl-C. Only one backend can use port 8000: the script stops an older one.
set -euo pipefail
DATASET="${1:-}"
case "$DATASET" in mock | desanitized) ;; *) echo "usage: $0 mock|desanitized [--front]" >&2; exit 2 ;; esac
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
# the clock of each dataset (the mock emails end on 12 Oct 2026; the original ones on 30 Jul 2026)
[ "$DATASET" = mock ] && export DEMO_NOW="${DEMO_NOW:-2026-10-12T18:00:00+08:00}"

old="$(lsof -ti ":$PORT" 2>/dev/null || true)"
if [ -n "$old" ]; then echo "stopping the backend already on port $PORT ($old)"; kill $old; sleep 2; fi

if [ "$DATASET" = mock ] && [ ! -f "$ROOT/datasets/mock/data/app.sqlite" ]; then
  echo "no mock database yet: run  python -m mockdata.build  and  python -m mockdata.load" >&2; exit 1
fi

if [ "${2:-}" = "--front" ]; then
  (cd "$ROOT/frontend" && npm run dev) &
  FRONT=$!
  trap 'kill $FRONT 2>/dev/null || true' EXIT
fi

echo "backend on http://127.0.0.1:$PORT with the $DATASET data  (add ?debug=1 to the page URL to see models)"
cd "$ROOT/backend"
DATASET="$DATASET" E16_V51_LLM_MODEL="${E16_V51_LLM_MODEL:-gpt-4o-mini}" E16_INCLUDE_DRAFT_PLAYBOOKS=1 \
  conda run -n somr --no-capture-output python -m uvicorn src.api:app --host 127.0.0.1 --port "$PORT"
