#!/usr/bin/env bash
# start-dramaclaw.sh — bring up the whole DramaClaw stack and open the web UI.
#
# One command, no Hermes needed. Checks each service, starts whatever is
# missing, waits for it to become healthy, then opens the XiaHua web UI.
#
# Usage:  ./start-dramaclaw.sh          (defaults)
#         DRAMA_DIR=/path ./start-dramaclaw.sh
#
# Services:
#   :8780 DramaClaw API       (uv run novelvideo api)
#   :8790 drama-gateway       (agy-shim -> G-Labs + Voice Studio)
#   :8080 XiaHua frontend     (pnpm dev)
#   :8765 G-Labs Automation   (desktop app — detect only)
#   :8766 G-Labs Voice Studio (desktop app — detect only)
set -uo pipefail

API_PORT="${API_PORT:-8780}"
GATEWAY_PORT="${GATEWAY_PORT:-8790}"
FE_PORT="${FE_PORT:-8080}"
GLABS_PORT=8765
VOICE_PORT=8766

DRAMA_DIR="${DRAMA_DIR:-$HOME/Code/drama-claw}"
HERMES_DIR="${HERMES_DIR:-$HOME/Code/drama-claw-hermes}"
LOG_DIR="${LOG_DIR:-$HERMES_DIR/logs}"
PYTHON3="${PYTHON3:-/usr/bin/python3}"
FE_URL="http://127.0.0.1:$FE_PORT"
API_URL="http://127.0.0.1:$API_PORT"
GATEWAY_URL="http://127.0.0.1:$GATEWAY_PORT"

mkdir -p "$LOG_DIR"

is_listening() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# start_service <name> <port> <cmd...>
# If the port is free, launch the command detached with nohup + log file.
start_service() {
  local name="$1" port="$2"
  shift 2
  if is_listening "$port"; then
    echo "  [ok]   $name already running on :$port"
    return 0
  fi
  echo "  [start] $name on :$port ..."
  nohup "$@" >>"$LOG_DIR/$name.log" 2>&1 &
  disown
  echo "         log -> $LOG_DIR/$name.log"
}

# wait_http <name> <url> [tries] — polls until curl succeeds.
wait_http() {
  local name="$1" url="$2" tries="${3:-40}"
  for _ in $(seq 1 "$tries"); do
    if curl -fsS -m 2 "$url" >/dev/null 2>&1; then
      echo "  [ok]   $name healthy"
      return 0
    fi
    sleep 1
  done
  echo "  [warn] $name not responding at $url (giving up after ${tries}s)"
  return 1
}

echo ""
echo "== DramaClaw stack =="
echo "  workspace: $DRAMA_DIR"
echo "  overlay:   $HERMES_DIR"
echo ""

# Desktop apps (can't launch from CLI — warn if missing).
if is_listening "$GLABS_PORT"; then
  echo "  [ok]   G-Labs Automation :$GLABS_PORT"
else
  echo "  [warn] G-Labs Automation not running on :$GLABS_PORT — open the app + check Accounts tab"
fi
if is_listening "$VOICE_PORT"; then
  echo "  [ok]   G-Labs Voice Studio :$VOICE_PORT"
else
  echo "  [warn] G-Labs Voice Studio not running on :$VOICE_PORT — open the app"
fi

# DramaClaw API.
start_service api "$API_PORT" bash -lc "cd '$DRAMA_DIR' && ST_EDITION=ce uv run novelvideo api --port $API_PORT"
wait_http "DramaClaw API" "$API_URL/healthz" 60 || true

# drama-gateway.
start_service gateway "$GATEWAY_PORT" "$PYTHON3" "$HERMES_DIR/agy-shim/drama_gateway.py" --port "$GATEWAY_PORT"
wait_http "drama-gateway" "$GATEWAY_URL/healthz" 60 || true

# XiaHua frontend.
start_service frontend "$FE_PORT" bash -lc "cd '$DRAMA_DIR/frontend' && pnpm dev --port $FE_PORT"
wait_http "XiaHua frontend" "$FE_URL" 90 || true

echo ""
if is_listening "$FE_PORT"; then
  echo "✅ Stack is up — opening $FE_URL"
  open "$FE_URL"
else
  echo "⚠️  Frontend did not come up — see $LOG_DIR/frontend.log"
fi
echo ""
echo "Quick checks:"
echo "  API health:   $API_URL/healthz"
echo "  Gateway:      $GATEWAY_URL/healthz"
echo "  Config JSON:  $API_URL/api/v1/model-gateway/config"
