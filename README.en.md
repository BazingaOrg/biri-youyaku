# biri-youyaku

[中文](README.md) | [English](README.en.md)

Paste a Bilibili video link, fetch subtitles when available, fall back to audio
transcription, and generate a Markdown summary in one click. Optionally email the
result.

## 60-second quickstart

You need Python 3.11+, Node.js 18+, [uv](https://docs.astral.sh/uv/), and `npm`.

```bash
# 1. Copy the env template and fill LLM_API_KEY (any OpenAI-compatible endpoint works)
cp server/.env.example server/.env
$EDITOR server/.env

# 2. Spin up backend + frontend dev servers (the script handles web/.env and npm install)
bash scripts/dev.sh
```

Open <http://127.0.0.1:5173> and paste any Bilibili video URL.

> Prefer Docker? `cp server/.env.example server/.env` then `docker compose up --build`.

---

## Project layout

- `web/` — Vite + React frontend.
- `server/` — FastAPI + SQLite backend.
- `examples/email-worker/` — optional Cloudflare Worker template for emailing summaries.
- `docs/` — design and optimization notes.
- `scripts/dev.sh`, `docker-compose.yml` — one-command local startup.

---

## Pick an LLM API key

Any OpenAI-compatible endpoint works:

| Provider | Sample `LLM_BASE_URL` | Notes |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | Standard |
| Moonshot / Kimi | `https://api.moonshot.cn/v1` | Backend auto-forces `temperature=1` |
| Tongyi Qianwen DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | |
| DeepSeek | `https://api.deepseek.com` | |
| Local ollama / vLLM | `http://localhost:11434/v1` | |

Set `LLM_MODEL` to whatever your provider supports (`gpt-4o-mini`, `moonshot-v1-32k`,
`qwen-plus`, …).

---

## Manual local dev

If you'd rather not use `scripts/dev.sh`:

```bash
# Backend
cd server
cp .env.example .env       # fill LLM_API_KEY
uv sync
uv run uvicorn biri_youyaku.app:app --reload --host 0.0.0.0 --port 17821

# Frontend (new terminal)
cd web
cp .env.example .env
npm install
npm run dev                # http://localhost:5173
```

---

## Optional features

### Bilibili login cookies (private / high-quality subtitles)

Log in on bilibili.com in your browser, copy `SESSDATA`, paste into `server/.env`:

```env
BILI_SESSDATA=your-sessdata
# Usually SESSDATA alone is enough; some endpoints want these too
# BILI_BUVID3=
# BILI_BILI_JCT=
```

### Local ASR (videos without subtitles)

You need `ffmpeg` / `ffprobe`; macOS `brew install ffmpeg`, Ubuntu `apt install ffmpeg`.

**Cross-platform (default) — funasr CPU backend:**

```bash
cd server
uv sync --extra asr     # installs funasr + torch
# server/.env
ASR_MODEL=sensevoice    # the default; can be omitted
```

**Apple Silicon Mac (M1+) — MLX backend (recommended, 15-30× faster):**

```bash
cd server
uv sync --extra asr-mlx # installs mlx-audio + parakeet-mlx
```

Available `ASR_MODEL` values:

| `ASR_MODEL` | Best for | Notes |
| --- | --- | --- |
| `sensevoice` | Cross-platform, Docker | funasr CPU, slow but portable |
| `sensevoice-mlx` | M-series Mac, CJK videos | Same weights, runs on GPU/ANE |
| `parakeet-mlx` | M-series Mac, English / European | NVIDIA Parakeet TDT v3, 6.34% WER (beats Whisper-Large-v3) |
| `auto` | Don't want to choose | Routes by job language: CJK → sensevoice-mlx, else → parakeet-mlx |
| `faster-whisper` | Existing whisper workflow | CTranslate2-optimized |

Mac mini M4 recommendation: `ASR_MODEL=auto`.

### Email delivery

> Email is **disabled by default** — you bring your own webhook. The repo ships a
> Cloudflare Worker template:

```bash
cd examples/email-worker
# Follow examples/email-worker/README.md, ~5 minutes
```

Then in `server/.env`:

```env
EMAIL_ENABLED=true
EMAIL_WEBHOOK_URL=https://biri-youyaku-mail.<account>.workers.dev
EMAIL_WEBHOOK_TOKEN=must match the Worker's BIRI_YOUYAKU_TOKEN
EMAIL_DEFAULT_RECIPIENT=you@example.com
```

If `EMAIL_ENABLED=true` but any of the required values are empty, the server logs
a WARN and refuses to create jobs to avoid sending to the wrong address.

---

## Public deployment

One common setup:

- Frontend on Vercel;
- Backend on your own machine (VPS / Raspberry Pi / workstation);
- Cloudflare Tunnel exposes the backend as an HTTPS domain;
- Email via Cloudflare Worker + Resend (see above).

Backend `server/.env`:

```env
API_TOKEN=generate with `openssl rand -hex 32`
APP_CORS_ORIGINS=https://your-frontend-domain.example.com
```

Vercel frontend settings:

```text
Framework: Vite
Root Directory: web
Build Command: npm run build
Output Directory: dist
```

Vercel environment variables:

```env
VITE_API_BASE_URL=https://your-api-domain.example.com
VITE_API_TOKEN=match backend API_TOKEN, or leave empty if a reverse proxy handles auth
```

> ⚠️ `VITE_API_TOKEN` is **bundled into the JS at build time**. Any visitor with
> devtools can read it; treat it as a weak credential and pair with Vercel
> Protection / Cloudflare Access for real public deployments.

Cloudflare Tunnel:

```text
your-api-domain.example.com -> http://localhost:17821
```

---

## API

- `GET /healthz`
- `GET /v1/config/defaults`
- `GET /v1/config/runtime` (public, reports what is configured)
- `GET /v1/usage?range=7d`
- `POST /v1/llm/models`
- `POST /v1/jobs`
- `POST /v1/jobs/preview`
- `GET /v1/jobs?limit=50&offset=0&cursor=...`
- `GET /v1/jobs/{id}`
- `GET /v1/jobs/{id}/stream` (SSE)
- `POST /v1/jobs/{id}/cancel`
- `POST /v1/jobs/{id}/resume`
- `POST /v1/jobs/{id}/retry`
- `POST /v1/jobs/{id}/transcript` (upload / replace subtitles)
- `GET /v1/jobs/{id}/audio`
- `DELETE /v1/jobs`
- `DELETE /v1/jobs/{id}`
- `POST /v1/jobs/{id}/email` (resend)

---

## Config reference

Every tunable in `server/.env` (defaults live in `server/biri_youyaku/config.py`):

| Group | Variable | Default | Notes |
| --- | --- | --- | --- |
| App | `APP_LOG_LEVEL` | `INFO` | uvicorn / app log level |
| App | `APP_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated |
| Auth | `API_TOKEN` | empty | Empty = no Bearer Token check |
| Bilibili | `BILI_SESSDATA / BILI_BUVID3 / BILI_BILI_JCT` | empty | Only when login needed |
| ASR | `ASR_MODEL` | `sensevoice` | Or `faster-whisper` |
| ASR | `ASR_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| ASR | `ASR_LANGUAGE_DEFAULT` | `auto` | |
| ASR | `SENSEVOICE_MODEL_DIR` | empty | Auto-download or path to local weights |
| LLM | `LLM_API_KEY` | empty | **Required** |
| LLM | `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| LLM | `LLM_MODEL` | `gpt-4o-mini` | |
| LLM | `LLM_TIMEOUT_SECONDS` | `300` | Per-request timeout |
| LLM | `LLM_MAX_RETRIES` | `2` | SDK-level retries |
| LLM | `LLM_TEMPERATURE` | empty | Empty uses provider-aware default |
| LLM | `LLM_CHUNK_TOKEN_THRESHOLD` | `30000` | Threshold for chunked summarization |
| LLM | `LLM_FORCE_TEMP_ONE_PREFIXES` | `kimi,moonshot` | Force `temperature=1` for matching model prefixes |
| LLM | `LLM_SEGMENT_CONCURRENCY` | `3` | Parallel segment summaries |
| Summary | `SUMMARY_LANGUAGE` | `中文简体` | Output language |
| Email | `EMAIL_ENABLED` | `false` | |
| Email | `EMAIL_WEBHOOK_URL / EMAIL_WEBHOOK_TOKEN / EMAIL_DEFAULT_RECIPIENT` | empty | |
| Email | `EMAIL_SUBJECT_TEMPLATE` | `[Biri-Youyaku] {{title}}` | Supports `{{title}}` / `{{author}}` |
| Storage | `AUDIO_STORAGE_DIR / SUMMARY_STORAGE_DIR / DB_PATH` | `data/...` | |
| Cleanup | `AUDIO_RETENTION_DAYS` | `7` | |
| Cleanup | `JOB_RETENTION_DAYS` | `180` | |
| Cleanup | `ORPHAN_FILE_RETENTION_DAYS` | `3` | How long an orphan file (no DB ref) lingers before cleanup |
| Cleanup | `STALE_RUNNING_FAIL_HOURS` | `4` | Non-terminal job is auto-FAILED after no heartbeat for N hours |
| Cleanup | `CLEANUP_INTERVAL_SECONDS` | `3600` | Cleanup loop period |
| Cleanup | `WAL_CHECKPOINT_INTERVAL_HOURS` | `24` | WAL truncation period |
| Cleanup | `DB_VACUUM_INTERVAL_DAYS` | `30` | VACUUM period |
| Concurrency | `MAX_CONCURRENT_JOBS` | `2` | Heavy IO/CPU cap |
| Concurrency | `MAX_CONCURRENT_SUMMARIES` | `2` | LLM summarize cap |

---

## Name / inspiration

`要約` (ようやく / yōyaku) means "summary" in Japanese; the same pronunciation
also means "at last". `biri` comes from `ビリビリ`, Japanese for Bilibili.

Inspired by:
- [linzzzzzz/openclip](https://github.com/linzzzzzz/openclip)
- [IndieKKY/bilibili-subtitle](https://github.com/IndieKKY/bilibili-subtitle)

## License

MIT
