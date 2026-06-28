# biri-youyaku

[中文](README.md) | [English](README.en.md)

Paste a Bilibili video link and get a readable Markdown summary, a mind map, and a clickable transcript. Local-first, self-hosted, no telemetry.

> `要約` (yōyaku) is Japanese for "summary"; the homophone also means "finally". `biri` comes from `ビリビリ`, the Japanese nickname for Bilibili.
> Inspired by [linzzzzzz/openclip](https://github.com/linzzzzzz/openclip) and [IndieKKY/bilibili-subtitle](https://github.com/IndieKKY/bilibili-subtitle).

## ✨ Features

- **Subtitles first**: use official subtitles when present, otherwise download audio and transcribe locally (ASR).
- **Multi-view summary**: Markdown notes (with a table of contents) / mind map (export SVG·PNG) / topic tags / transcript (click a timestamp to jump back into the video).
- **Any LLM**: any OpenAI-compatible endpoint (DeepSeek by default; OpenAI / Gemini / local ollama all work).
- **Browse by uploader**: list an uploader's whole catalog, see which are summarized, one-click the rest.
- **Dedup to save tokens**: re-pasting an already-summarized video reuses the old result.
- **Local-first**: all data stays local, no telemetry; optional email delivery and optional API-token auth.

## 🚀 Quick start

Requires Python 3.11+, Node.js 22+ (see `.nvmrc`), [uv](https://docs.astral.sh/uv/), and `npm`.

```bash
cp server/.env.example server/.env   # set LLM_API_KEY (DeepSeek by default)
bash scripts/dev.sh                  # starts both servers (auto-copies .env, installs deps)
```

Open <http://127.0.0.1:5173> and paste a Bilibili link.

> Windows: `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1`
> Docker: `docker compose up --build` (hot-reload via `docker compose -f docker-compose.dev.yml up --build`).

<details>
<summary>Run the two servers manually</summary>

```bash
# backend
cd server && cp .env.example .env && uv sync
uv run uvicorn biri_youyaku.app:app --reload --host 0.0.0.0 --port 17821

# frontend (new terminal)
cd web && cp .env.example .env && npm install && npm run dev   # http://localhost:5173
```

</details>

## ⚙️ LLM configuration

Any OpenAI-compatible endpoint works. Set at least `LLM_API_KEY` in `server/.env`:

| Provider | `LLM_BASE_URL` |
| --- | --- |
| **DeepSeek** (default) | `https://api.deepseek.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` |
| Local ollama / vLLM | `http://localhost:11434/v1` |

Set `LLM_MODEL` to a model the provider supports (default `deepseek-v4-flash`). See [`CONFIG.md`](CONFIG.md) for more providers and every option.

> **Cost**: the default model summarizes a 20-minute video for about ¥0.02; go fully free with local ollama below.

<details>
<summary>Fully local / free / offline (ollama)</summary>

```bash
ollama pull qwen2.5:3b        # runs in 4GB RAM, fine for summaries; use qwen2.5:7b if you can
```

```env
# server/.env
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:3b
LLM_API_KEY=ollama            # ollama ignores it but it must be non-empty
LLM_BASE_URL_ALLOWED_HOSTS=   # leave empty for local only; never open the allowlist in production
```

Combined with local ASR below, this is fully offline (except fetching from Bilibili).

</details>

## 🧩 Optional features

- **Local ASR** (videos without subtitles): needs `ffmpeg`. Cross-platform `cd server && uv sync --extra asr`; on Apple Silicon use `--extra asr-mlx` (15-30× GPU/ANE speedup). Switch backends with `ASR_MODEL` (see table below).
- **Bilibili login** (private videos / better subtitles): copy `SESSDATA` from your browser cookies into `BILI_SESSDATA` in `server/.env`.
- **Email delivery** (off by default): use the bundled Cloudflare Worker template — follow [`examples/email-worker/README.md`](examples/email-worker/README.md), then enable `EMAIL_ENABLED` etc. in `server/.env`.

<details>
<summary>ASR backends</summary>

| `ASR_MODEL` | Best for | Notes |
| --- | --- | --- |
| `sensevoice` (default) | cross-platform, Docker | funasr CPU, slow but portable |
| `sensevoice-mlx` | Apple Silicon, CJK | same model/accuracy, uses GPU/ANE |
| `parakeet-mlx` | Apple Silicon, EN/EU | NVIDIA Parakeet TDT v3 |
| `auto` | don't want to choose | CJK → sensevoice-mlx, else → parakeet-mlx |
| `faster-whisper` | existing whisper setup | CTranslate2 build |

</details>

## 🏗️ Architecture

```mermaid
flowchart LR
    user([Browser]) -->|paste BV link| web[Vite + React]
    web -->|REST + SSE| api[FastAPI]
    api --> ytdlp[yt-dlp<br/>subtitles/audio]
    ytdlp -->|has subtitles| llm
    ytdlp -->|no subtitles| asr[local ASR<br/>SenseVoice / Parakeet]
    asr --> llm[LLM<br/>OpenAI-compatible]
    llm -->|streamed chunks| api
    api --> db[(SQLite)]
    api -. optional .-> mail[Cloudflare Worker → Resend]
```

> All data stays local (`server/data/`); nothing is reported to third parties besides the LLM endpoint and Bilibili. No telemetry.

## 📦 Deploy & docs

- [`DEPLOY.md`](DEPLOY.md) — public deployment (Vercel + Cloudflare Tunnel)
- [`CONFIG.md`](CONFIG.md) — every `server/.env` option
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — develop / test / commit
- [`AGENTS.md`](AGENTS.md) — codebase tour for AI coding assistants
- [`CHANGELOG.md`](CHANGELOG.md) — changes

Full API at `/docs` once the backend is running (auto-generated by FastAPI).

## License

MIT
