#!/usr/bin/env bash
# macOS LaunchAgent helper for the biri-youyaku API (host-native uv, no --reload).
#
# Usage:
#   bash scripts/mac-service.sh install|uninstall|start|stop|restart|status [--verbose]|logs|help
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
  local candidate=""
  if [ -n "${UV:-}" ] && [ -x "${UV}" ]; then
    candidate="${UV}"
  elif command -v uv >/dev/null 2>&1; then
    candidate="$(command -v uv)"
  else
    die "uv not found. Install: https://docs.astral.sh/uv/  (or set UV=/absolute/path/to/uv)"
  fi
  # Launchd needs an absolute ProgramArguments path.
  if command -v realpath >/dev/null 2>&1; then
    candidate="$(realpath "${candidate}")"
  elif [[ "${candidate}" != /* ]]; then
    candidate="$(cd "$(dirname "${candidate}")" && pwd)/$(basename "${candidate}")"
  fi
  if [[ "${candidate}" != /* ]]; then
    die "uv path must be absolute for launchd (got: ${candidate}); set UV=/absolute/path/to/uv"
  fi
  if [ ! -x "${candidate}" ]; then
    die "uv not executable: ${candidate}"
  fi
  echo "${candidate}"
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

# Returns 0 if free or only our service; 1 if a foreign listener holds the port.
port_conflict_exists() {
  local pids pid our_pid
  pids="$(port_listener_pids | tr '\n' ' ' | xargs 2>/dev/null || true)"
  [ -z "${pids}" ] && return 1

  our_pid=""
  if service_loaded; then
    our_pid="$(launchctl print "${DOMAIN}/${LABEL}" 2>/dev/null | awk '/pid = / { print $3; exit }' || true)"
  fi

  for pid in ${pids}; do
    if [ -n "${our_pid}" ] && [ "${pid}" = "${our_pid}" ]; then
      continue
    fi
    if [ -n "${our_pid}" ] && ps -o ppid= -p "${pid}" 2>/dev/null | tr -d ' ' | grep -qx "${our_pid}"; then
      continue
    fi
    # Parent may be uv; grandparent launchd job — still foreign if not our tree.
    echo "${pid}"
    return 0
  done
  return 1
}

require_port_free_or_ours() {
  local foreign
  foreign="$(port_conflict_exists || true)"
  if [ -n "${foreign}" ]; then
    die "port ${API_PORT} is in use by PID ${foreign} (not this LaunchAgent). Stop it or: $0 stop"
  fi
}

check_asr_extra() {
  # Best-effort: warn if neither mlx-audio nor funasr is importable in the project env.
  if ! (
    cd "${SERVER_DIR}" && uv run --no-dev python -c "
import importlib.util
ok = importlib.util.find_spec('mlx_audio') or importlib.util.find_spec('funasr')
raise SystemExit(0 if ok else 1)
" >/dev/null 2>&1
  ); then
    echo "warning: neither mlx_audio nor funasr is importable in server env." >&2
    echo "         No-subtitle ASR will fail. On Apple Silicon:" >&2
    echo "           cd server && uv sync --extra asr-mlx" >&2
    echo "         Linux/CPU: cd server && uv sync --extra asr" >&2
  fi
}

wait_healthz() {
  local i code
  if ! command -v curl >/dev/null 2>&1; then
    echo "warning: curl missing; skip healthz probe" >&2
    return 0
  fi
  for i in 1 2 3 4 5 6 7 8 9 10; do
    code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 1 "${HEALTH_URL}" 2>/dev/null || echo "000")"
    if [ "${code}" = "200" ]; then
      info "healthz OK (HTTP ${code})"
      return 0
    fi
    sleep 0.5
  done
  echo "warning: healthz not ready at ${HEALTH_URL} (last HTTP ${code:-000})" >&2
  echo "         check: $0 logs / $0 status" >&2
  return 1
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

  check_ffmpeg
  check_asr_extra
}

bootout_if_loaded() {
  local service_pid=""
  local tracked_pid
  local tracked_pids=""
  local tracked_alive
  local stop_attempt

  if service_loaded; then
    service_pid="$(launchctl print "${DOMAIN}/${LABEL}" 2>/dev/null | awk '/pid = / { print $3; exit }' || true)"
    if [[ "${service_pid}" =~ ^[0-9]+$ ]]; then
      tracked_pids="$(collect_process_tree "${service_pid}")"
    fi
  fi

  if service_loaded || [ -f "${PLIST_DST}" ]; then
    launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || \
      launchctl bootout "${DOMAIN}" "${PLIST_DST}" 2>/dev/null || \
      launchctl unload "${PLIST_DST}" 2>/dev/null || true
  fi

  for stop_attempt in {1..60}; do
    tracked_alive=false
    if [ -n "${tracked_pids}" ]; then
      while IFS= read -r tracked_pid; do
        if [[ "${tracked_pid}" =~ ^[0-9]+$ ]] && kill -0 "${tracked_pid}" 2>/dev/null; then
          tracked_alive=true
          break
        fi
      done <<<"${tracked_pids}"
    fi
    if ! service_loaded && [ -z "$(port_listener_pids)" ] && [ "${tracked_alive}" = false ]; then
      return 0
    fi
    if [ "${stop_attempt}" -lt 60 ]; then
      sleep 0.25
    fi
  done
  die "service did not fully stop; check: $0 status --verbose"
}

collect_process_tree() {
  local parent_pid="$1"
  local child_pid
  echo "${parent_pid}"
  while IFS= read -r child_pid; do
    [[ "${child_pid}" =~ ^[0-9]+$ ]] && collect_process_tree "${child_pid}"
  done < <(pgrep -P "${parent_pid}" 2>/dev/null || true)
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
  require_port_free_or_ours
  write_plist
  bootout_if_loaded
  bootstrap_service
  launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
  if ! service_loaded; then
    die "install wrote plist but launchd job is not loaded; see ${LOG_DIR}"
  fi
  if ! wait_healthz; then
    die "service started but /healthz failed; see $0 logs"
  fi

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
  require_port_free_or_ours
  if [ ! -f "${PLIST_DST}" ]; then
    die "not installed. Run: $0 install"
  fi
  if service_loaded; then
    kickstart_service
  else
    bootstrap_service
    launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
  fi
  if ! service_loaded; then
    die "start failed: launchd job not loaded; see ${LOG_DIR}"
  fi
  wait_healthz || die "started but /healthz failed; see $0 logs"
  info "started ${LABEL}"
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
  if [ ! -f "${PLIST_DST}" ]; then
    die "not installed. Run: $0 install"
  fi
  # Rewrite plist (uv/PATH), then full bootout + bootstrap so ProgramArguments reload.
  write_plist
  bootout_if_loaded
  require_port_free_or_ours
  bootstrap_service
  launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
  if ! service_loaded; then
    die "restart failed: launchd job not loaded; see ${LOG_DIR}"
  fi
  wait_healthz || die "restarted but /healthz failed; see $0 logs"
  info "restarted ${LABEL}"
}

cmd_status() {
  local verbose="${1:-}"
  local foreign
  local listener_pids
  if [ -n "${verbose}" ] && [ "${verbose}" != "--verbose" ]; then
    die "unknown status option: ${verbose}"
  fi

  echo "service: ${LABEL}"
  if [ -f "${PLIST_DST}" ]; then
    echo "plist:  present"
  else
    echo "plist:  missing (not installed)"
  fi

  if service_loaded; then
    local service_details state pid
    service_details="$(launchctl print "${DOMAIN}/${LABEL}" 2>/dev/null || true)"
    state="$(awk '/state = / { print $3; exit }' <<<"${service_details}")"
    pid="$(awk '/pid = / { print $3; exit }' <<<"${service_details}")"
    echo "state:   ${state:-loaded}"
    if [ -n "${pid}" ]; then
      echo "pid:     ${pid}"
    fi
    if [ "${verbose}" = "--verbose" ]; then
      echo
      printf '%s\n' "${service_details}"
    fi
  else
    echo "state:   not loaded"
  fi

  listener_pids="$(port_listener_pids | tr '\n' ' ' | xargs 2>/dev/null || true)"
  if [ -z "${listener_pids}" ]; then
    if service_loaded; then
      echo "port:    no listener (starting or unhealthy)"
    else
      echo "port:    free (API offline)"
    fi
  elif port_conflict_exists >/dev/null 2>&1; then
    foreign="$(port_conflict_exists || true)"
    if [ -n "${foreign}" ]; then
      echo "port:    FOREIGN listener PID ${foreign} on ${API_PORT}"
    fi
  else
    echo "port:    listening (owned by this service)"
  fi

  if command -v curl >/dev/null 2>&1; then
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 "${HEALTH_URL}" 2>/dev/null || echo "000")"
    echo "healthz: HTTP ${code}  (${HEALTH_URL})"
  else
    echo "healthz: curl not available"
  fi
  echo "logs:    ${LOG_DIR}"
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
  install     Write plist and bootstrap under ${DOMAIN}
  uninstall   Bootout and remove plist
  start       Restart the loaded service, or bootstrap if needed
  stop        Bootout service
  restart     Full bootout and bootstrap
  status      Concise service state + healthz (add --verbose for launchctl details)
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
    status)    cmd_status "${2:-}" ;;
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
