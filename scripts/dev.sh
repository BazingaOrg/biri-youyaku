#!/usr/bin/env bash
# 一键起前后端 dev server。
# 用法：bash scripts/dev.sh
#
# - 后端：uvicorn --reload，默认 17821
# - 前端：vite --port 5173
# - Ctrl+C 一起退（trap 后台 PID）

set -euo pipefail
cd "$(dirname "$0")/.."

# 启动前的最小化前置检查 ----------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "需要 uv：https://docs.astral.sh/uv/" >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "需要 npm（Node.js 22+）" >&2
  exit 1
fi
if [ ! -f server/.env ]; then
  echo "→ 拷一份 server/.env.example → server/.env，记得填 LLM_API_KEY"
  cp server/.env.example server/.env
fi
if [ ! -f web/.env ]; then
  cp web/.env.example web/.env
fi

# 后端 ---------------------------------------------------------------------
(
  cd server
  uv sync --quiet
  uv run uvicorn biri_youyaku.app:app --reload --host 127.0.0.1 --port 17821
) &
BACK_PID=$!

# 前端 ---------------------------------------------------------------------
(
  cd web
  if [ ! -d node_modules ]; then
    npm install
  fi
  npm run dev
) &
FRONT_PID=$!

cleanup() {
  echo
  echo "→ 关停 dev server (后端 $BACK_PID, 前端 $FRONT_PID)…"
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo
echo "→ 后端 http://127.0.0.1:17821"
echo "→ 前端 http://127.0.0.1:5173"
echo "→ Ctrl+C 退出"
echo

wait
