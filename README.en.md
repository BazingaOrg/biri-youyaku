# biri-youyaku

[中文](README.md) | [English](README.en.md)

Paste a Bilibili video link, fetch subtitles first, fall back to audio transcription when subtitles are unavailable, review the transcript, and generate a summary with one click. The summary can also be sent by email.

## Name

`要約` (ようやく / yōyaku) means "summary" in Japanese, while the same pronunciation `ようやく` can also mean "finally" or "at last". The name is a small pun: summarize the video and finally understand it without watching the whole thing. `biri` comes from the Japanese colloquial sound of Bilibili, `ビリビリ`, so together it becomes `biri-youyaku`.

## Inspired By

- [linzzzzzz/openclip](https://github.com/linzzzzzz/openclip)
- [IndieKKY/bilibili-subtitle](https://github.com/IndieKKY/bilibili-subtitle)

## Project Structure

- `web/`: frontend app.
- `server/`: backend service for subtitles, audio download, speech-to-text, summary generation, email delivery, and local job storage.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js 18+
- npm

## Backend Setup

```bash
cd server
cp .env.example .env
uv sync
uv run uvicorn biri_youyaku.app:app --reload --host 0.0.0.0 --port 17821
```

For local ASR support:

```bash
cd server
uv sync --extra asr
```

Common backend `.env` values:

```env
API_TOKEN=
LLM_API_KEY=your LLM API key
LLM_BASE_URL=your OpenAI-compatible base URL
LLM_MODEL=your model name
APP_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

If a public frontend needs to access the backend, add your production frontend domain to `APP_CORS_ORIGINS`. When backend `API_TOKEN` is empty, Bearer-token authentication is disabled; set it before exposing the API publicly.

For deployment, set `API_TOKEN`. You can generate one with:

```bash
openssl rand -hex 32
```

Then put the generated value in `server/.env`:

```env
API_TOKEN=the-generated-token
```

Email is optional:

```env
EMAIL_ENABLED=true
EMAIL_WEBHOOK_URL=https://your-mail-worker.example.com
EMAIL_WEBHOOK_TOKEN=your email webhook token
EMAIL_DEFAULT_RECIPIENT=you@example.com
EMAIL_SUBJECT_TEMPLATE=[Video Summary] {{title}}
```

Some videos may require login cookies for subtitle extraction or audio download. Configure `BILI_SESSDATA`, `BILI_BUVID3`, and `BILI_BILI_JCT` when needed.

## Frontend Setup

```bash
cd web
cp .env.example .env
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Frontend `.env`:

```env
VITE_API_BASE_URL=http://localhost:17821
VITE_API_TOKEN=same value as backend API_TOKEN
```

`VITE_API_TOKEN` must match the backend `API_TOKEN`; leave it empty when backend `API_TOKEN` is empty. This value is bundled into browser JavaScript and should not be treated as a real secret. For public deployments, use Vercel Protection, Cloudflare Access, or another access-control layer.

## Build

```bash
cd web
npm run build
```

## Deployment

A common setup:

- Deploy the frontend to Vercel.
- Run the backend on your own machine or server.
- Expose the backend through Cloudflare Tunnel as an HTTPS API domain.
- Send emails through Cloudflare Worker + Resend.

Vercel settings:

```text
Framework: Vite
Root Directory: web
Build Command: npm run build
Output Directory: dist
```

Vercel environment variables:

```env
VITE_API_BASE_URL=https://your-api-domain.example.com
VITE_API_TOKEN=same value as backend API_TOKEN
```

Cloudflare Tunnel example:

```text
your-api-domain.example.com -> http://localhost:17821
```

The Worker's `BIRI_YOUYAKU_TOKEN` must match the backend `EMAIL_WEBHOOK_TOKEN`. The backend calls the Worker with `Authorization: Bearer <EMAIL_WEBHOOK_TOKEN>`.

Set these backend values for deployment:

```env
APP_CORS_ORIGINS=https://your-frontend-domain.example.com
API_TOKEN=the-generated-token
```

## API

- `GET /healthz`
- `GET /v1/config/defaults`
- `POST /v1/llm/models`
- `POST /v1/jobs`
- `GET /v1/jobs?limit=50&offset=0`
- `GET /v1/jobs/{id}`
- `GET /v1/jobs/{id}/stream`
- `POST /v1/jobs/{id}/cancel`
- `POST /v1/jobs/{id}/resume`
- `GET /v1/jobs/{id}/audio`
- `DELETE /v1/jobs`
- `DELETE /v1/jobs/{id}`
- `POST /v1/jobs/{id}/email`

## License

MIT
