#!/usr/bin/env bash
# macOS LaunchAgent helper for the biri-youyaku API (host-native uv, no --reload).
#
# Usage:
#   bash scripts/mac-service.sh install|uninstall|start|stop|restart|status|logs|help
#
# Production on an always-on Mac Mini with frequent MLX ASR: keep the API under
# launchd so Ghostty/dev terminal need not stay open. Use scripts/dev.sh only
# while coding — stop the service first to free port 17821.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_DIR="${REPO_ROOT}/server"
TEMPLATE="${REPO_ROOT}/scripts/macos/com.biri-youyaku.api.plist.template"

LABEL="com.biri-youyaku.api"
PLIST_DST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs/biri-youyaku"
DOMAIN="gui/$(id -u)"
API_HOST="127.0.0.1"
API_PORT="17821"
HEALTH_URL="http://${API_HOST}:${API_PORT}/healthz"

die() {
  echo "error: $*" >&2
  exit 1
}

info() {
  echo "→ $*"
}

resolve_uv() {
  if [ -n "${UV:-}" ] && [ -x "${UV}" ]; then
    echo "${UV}"
    return
  fi
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return
  fi
  die "uv not found. Install: https://docs.astral.sh/uv/  (or set UV=/absolute/path/to/uv)"
}

require_template() {
  [ -f "${TEMPLATE}" ] || die "missing plist template: ${TEMPLATE}"
}

require_env() {
  [ -f "${SERVER_DIR}/.env" ] || die "missing ${SERVER_DIR}/.env — copy from server/.env.example and set LLM_API_KEY"
}

service_loaded() {
  launchctl print "${DOMAIN}/${LABEL}" >/dev/null 2>&1
}

port_listener_pids() {
  # Print PIDs listening on API_PORT (best-effort; empty if none / lsof missing).
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi
  lsof -nP -iTCP:"${API_PORT}" -sTCP:LISTEN -t 2>/dev/null || true
}

warn_port_conflict() {
  local pids pid our_pid
  pids="$(port_listener_pids | tr '\n' ' ' | xargs 2>/dev/null || true)"
  [ -z "${pids}" ] && return 0

  our_pid=""
  if service_loaded; then
    our_pid="$(launchctl print "${DOMAIN}/${LABEL}" 2>/dev/null | awk '/pid = / { print $3; exit }' || true)"
  fi

  for pid in ${pids}; do
    if [ -n "${our_pid}" ] && [ "${pid}" = "${our_pid}" ]; then
      continue
    fi
    # Also accept children of our launchd job (uv → uvicorn).
    if [ -n "${our_pid}" ] && ps -o ppid= -p "${pid}" 2>/dev/null | tr -d ' ' | grep -qx "${our_pid}"; then
      continue
    fi
    echo "warning: port ${API_PORT} is in use by PID ${pid} (not this LaunchAgent)." >&2
    echo "         stop that process or run: $0 stop  /  free the port before install/start." >&2
    return 0
  done
}

# PATH for launchd: interactive shells include Homebrew; LaunchAgents do not.
service_path() {
  local path_extra=""
  # Prefer dirs that actually exist so we don't mislead debugging.
  for d in /opt/homebrew/bin /opt/homebrew/sbin /usr/local/bin /usr/local/sbin; do
    if [ -d "${d}" ]; then
      path_extra="${path_extra}${d}:"
    fi
  done
  # Keep user login PATH tail if set, else standard system paths.
  echo "${path_extra}${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"
}

check_ffmpeg() {
  local path_for_which
  path_for_which="$(service_path)"
  if ! PATH="${path_for_which}" command -v ffmpeg >/dev/null 2>&1 \
    || ! PATH="${path_for_which}" command -v ffprobe >/dev/null 2>&1; then
    echo "warning: ffmpeg/ffprobe not found on service PATH." >&2
    echo "         Audio download (yt-dlp) and some ASR paths need them." >&2
    echo "         Install: brew install ffmpeg" >&2
    echo "         Then:    bash scripts/mac-service.sh install   # rewrite PATH in plist" >&2
  fi
}

write_plist() {
  local uv_path svc_path
  uv_path="$(resolve_uv)"
  svc_path="$(service_path)"
  require_template
  require_env
  mkdir -p "${LOG_DIR}"
  mkdir -p "$(dirname "${PLIST_DST}")"

  # Escape nothing special — absolute paths only; sed substitutes placeholders.
  # Use | delimiter; PATH may contain : but not typically |.
  sed \
    -e "s|__LABEL__|${LABEL}|g" \
    -e "s|__UV__|${uv_path}|g" \
    -e "s|__SERVER_DIR__|${SERVER_DIR}|g" \
    -e "s|__LOG_DIR__|${LOG_DIR}|g" \
    -e "s|__PATH__|${svc_path}|g" \
    -e "s|__HOME__|${HOME}|g" \
    "${TEMPLATE}" > "${PLIST_DST}"

  info "wrote ${PLIST_DST}"
  info "uv=${uv_path}"
  info "WorkingDirectory=${SERVER_DIR}"
  info "PATH=${svc_path}"
  info "logs=${LOG_DIR}"
  check_ffmpeg
}

bootout_if_loaded() {
  if service_loaded || [ -f "${PLIST_DST}" ]; then
    launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || \
      launchctl bootout "${DOMAIN}" "${PLIST_DST}" 2>/dev/null || \
      launchctl unload "${PLIST_DST}" 2>/dev/null || true
  fi
}

bootstrap_service() {
  [ -f "${PLIST_DST}" ] || die "plist not installed: ${PLIST_DST} (run: $0 install)"
  if launchctl bootstrap "${DOMAIN}" "${PLIST_DST}" 2>/dev/null; then
    return 0
  fi
  # Older macOS fallback
  if launchctl load "${PLIST_DST}" 2>/dev/null; then
    return 0
  fi
  die "launchctl bootstrap/load failed. macOS may be too old or the plist is invalid."
}

kickstart_service() {
  if launchctl kickstart -k "${DOMAIN}/${LABEL}" 2>/dev/null; then
    return 0
  fi
  if launchctl kickstart "${DOMAIN}/${LABEL}" 2>/dev/null; then
    return 0
  fi
  # Not loaded yet — try bootstrap
  bootstrap_service
  launchctl kickstart -k "${DOMAIN}/${LABEL}" 2>/dev/null || \
    launchctl start "${LABEL}" 2>/dev/null || \
    die "kickstart failed for ${DOMAIN}/${LABEL}"
}

cmd_install() {
  warn_port_conflict
  write_plist
  bootout_if_loaded
  bootstrap_service
  # Prefer enable + kickstart when available
  launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
  kickstart_service || true

  info "installed and started ${LABEL}"
  echo
  echo "Next steps:"
  echo "  • After code / dependency changes:  bash scripts/mac-service.sh restart"
  echo "  • Before scripts/dev.sh (port ${API_PORT}):  bash scripts/mac-service.sh stop"
  echo "  • ASR on Apple Silicon: host uv with  cd server && uv sync --extra asr-mlx"
  echo "  • Logs:  bash scripts/mac-service.sh logs   (${LOG_DIR})"
  echo "  • Status: bash scripts/mac-service.sh status"
  echo
  echo "Production runs without a terminal. Keep Ghostty only while developing."
}

cmd_uninstall() {
  bootout_if_loaded
  if [ -f "${PLIST_DST}" ]; then
    rm -f "${PLIST_DST}"
    info "removed ${PLIST_DST}"
  else
    info "plist already absent: ${PLIST_DST}"
  fi
  info "uninstalled ${LABEL} (logs kept under ${LOG_DIR})"
}

cmd_start() {
  warn_port_conflict
  if [ ! -f "${PLIST_DST}" ]; then
    die "not installed. Run: $0 install"
  fi
  if service_loaded; then
    kickstart_service
  else
    bootstrap_service
    launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
    kickstart_service || true
  fi
  info "start requested for ${LABEL}"
}

cmd_stop() {
  if service_loaded || [ -f "${PLIST_DST}" ]; then
    bootout_if_loaded
    info "stopped ${LABEL} (bootout)"
  else
    info "${LABEL} not loaded"
  fi
}

cmd_restart() {
  warn_port_conflict
  if [ ! -f "${PLIST_DST}" ]; then
    die "not installed. Run: $0 install"
  fi
  if ! service_loaded; then
    bootstrap_service
    launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
  fi
  if launchctl kickstart -k "${DOMAIN}/${LABEL}" 2>/dev/null; then
    info "restarted ${LABEL} (kickstart -k)"
    return 0
  fi
  # Fallback: bootout + bootstrap
  bootout_if_loaded
  bootstrap_service
  launchctl kickstart -k "${DOMAIN}/${LABEL}" 2>/dev/null || \
    launchctl start "${LABEL}" 2>/dev/null || \
    die "restart failed"
  info "restarted ${LABEL}"
}

cmd_status() {
  echo "label:  ${LABEL}"
  echo "domain: ${DOMAIN}"
  echo "plist:  ${PLIST_DST}"
  if [ -f "${PLIST_DST}" ]; then
    echo "plist:  present"
  else
    echo "plist:  missing (not installed)"
  fi

  if service_loaded; then
    echo "launchd: loaded"
    launchctl print "${DOMAIN}/${LABEL}" 2>/dev/null | head -n 40 || \
      launchctl list | grep -F "${LABEL}" || true
  else
    echo "launchd: not loaded"
    launchctl list 2>/dev/null | grep -F "${LABEL}" || true
  fi

  warn_port_conflict

  if command -v curl >/dev/null 2>&1; then
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 "${HEALTH_URL}" 2>/dev/null || echo "000")"
    echo "healthz: HTTP ${code}  (${HEALTH_URL})"
  else
    echo "healthz: curl not available"
  fi
}

cmd_logs() {
  mkdir -p "${LOG_DIR}"
  local out="${LOG_DIR}/api.out.log"
  local err="${LOG_DIR}/api.err.log"
  touch "${out}" "${err}"
  info "tail -n 50 -f ${out} ${err}"
  echo "---- (Ctrl+C to stop) ----"
  tail -n 50 -f "${out}" "${err}"
}

cmd_help() {
  cat <<EOF
macOS LaunchAgent for biri-youyaku API (no --reload, host uv).

Usage: bash scripts/mac-service.sh <command>

Commands:
  install     Write plist, bootstrap + kickstart under ${DOMAIN}
  uninstall   Bootout and remove plist
  start       Kickstart (bootstrap if needed)
  stop        Bootout service
  restart     launchctl kickstart -k
  status      launchctl print/list + healthz curl
  logs        tail -f ${LOG_DIR}/api.{out,err}.log
  help        This message

Env:
  UV=/path/to/uv   Override uv binary (must be absolute for launchd)

Docs: docs/runbooks/macos-service.md
EOF
}

main() {
  local cmd="${1:-help}"
  case "${cmd}" in
    install)   cmd_install ;;
    uninstall) cmd_uninstall ;;
    start)     cmd_start ;;
    stop)      cmd_stop ;;
    restart)   cmd_restart ;;
    status)    cmd_status ;;
    logs)      cmd_logs ;;
    help|-h|--help) cmd_help ;;
    *)
      echo "unknown command: ${cmd}" >&2
      cmd_help >&2
      exit 1
      ;;
  esac
}

main "$@"
