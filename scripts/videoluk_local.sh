#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/data/runtime"
PID_FILE="$RUNTIME_DIR/videoluk.pid"
LOG_FILE="$RUNTIME_DIR/videoluk.log"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
PORT="${VIDEOLUK_PORT:-4173}"
BASE_URL="http://127.0.0.1:$PORT"

mkdir -p "$RUNTIME_DIR"

running_pid() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(tr -dc '0-9' < "$PID_FILE")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      printf '%s' "$pid"
      return 0
    fi
    rm -f "$PID_FILE"
  fi
  return 1
}

health_check() {
  curl --fail --silent --show-error --max-time 3 "$BASE_URL/api/health"
}

start_server() {
  if pid="$(running_pid)"; then
    echo "Videoluk zaten çalışıyor (PID $pid): $BASE_URL"
    return 0
  fi
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Yerel ortam bulunamadı. Önce ./scripts/setup_local.sh çalıştırın." >&2
    return 1
  fi
  echo "Videoluk başlatılıyor…"
  (
    cd "$PROJECT_DIR"
    VIDEOLUK_PORT="$PORT" nohup "$PYTHON_BIN" server.py >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
  )
  for _attempt in {1..30}; do
    if health_check >/dev/null 2>&1; then
      echo "Videoluk hazır: $BASE_URL"
      echo "Günlük: $LOG_FILE"
      return 0
    fi
    sleep 0.25
  done
  echo "Videoluk başlatılamadı. Son günlük kayıtları:" >&2
  tail -n 20 "$LOG_FILE" >&2 || true
  return 1
}

stop_server() {
  if ! pid="$(running_pid)"; then
    echo "Videoluk çalışmıyor."
    return 0
  fi
  kill "$pid"
  for _attempt in {1..20}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      echo "Videoluk durduruldu."
      return 0
    fi
    sleep 0.25
  done
  echo "Videoluk kapanmayı tamamlamadı (PID $pid)." >&2
  return 1
}

status_server() {
  if pid="$(running_pid)"; then
    if health="$(health_check 2>/dev/null)"; then
      echo "Videoluk çalışıyor (PID $pid): $BASE_URL"
      echo "$health"
      return 0
    fi
    echo "İşlem çalışıyor fakat sağlık kontrolü başarısız (PID $pid)." >&2
    return 1
  fi
  echo "Videoluk çalışmıyor."
  return 1
}

case "${1:-start}" in
  start) start_server ;;
  stop) stop_server ;;
  restart) stop_server; start_server ;;
  status) status_server ;;
  logs) tail -n 80 "$LOG_FILE" ;;
  *)
    echo "Kullanım: $0 {start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
