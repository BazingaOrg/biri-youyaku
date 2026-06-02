# 部署到公网 / Deploy to the internet

[中文](#部署到公网) | [English](#deploy)

---

## 部署到公网

一种常见架构：

- 前端部署到 Vercel；
- 后端跑在自己的机器（VPS / 树莓派 / 工作站）；
- 用 Cloudflare Tunnel 暴露后端为 HTTPS 域名；
- 邮件走 Cloudflare Worker + Resend（见 `examples/email-worker/`）。

后端 `server/.env`：

```env
API_TOKEN=用 `openssl rand -hex 32` 生成
APP_CORS_ORIGINS=https://your-frontend-domain.example.com
```

Vercel 前端：

```text
Framework: Vite
Root Directory: web
Build Command: npm run build
Output Directory: dist
```

Vercel 环境变量：

```env
VITE_API_BASE_URL=https://your-api-domain.example.com
VITE_API_TOKEN=与后端 API_TOKEN 一致；若走 Vercel Protection / Cloudflare Access 可留空
```

> ⚠️ `VITE_API_TOKEN` 会**打进前端 JS bundle**，任何访问页面的人都能在 devtools 看到。
> 当成「弱口令」用，公网部署最好叠一层 Vercel Protection / Cloudflare Access。

Cloudflare Tunnel：

```text
your-api-domain.example.com -> http://localhost:17821
```

公网部署强烈建议同时配上 `MAX_VIDEO_DURATION_SECONDS`、`MAX_INFLIGHT_JOBS` 和
`LLM_BASE_URL_ALLOWED_HOSTS`（详见 `CONFIG.md`）。

---

## Deploy

A common setup:

- Frontend on Vercel.
- Backend on your own machine (VPS / Raspberry Pi / workstation).
- Cloudflare Tunnel to expose the backend as HTTPS.
- Email via Cloudflare Worker + Resend (see `examples/email-worker/`).

Backend `server/.env`:

```env
API_TOKEN=$(openssl rand -hex 32)
APP_CORS_ORIGINS=https://your-frontend-domain.example.com
```

Vercel frontend:

```text
Framework: Vite
Root Directory: web
Build Command: npm run build
Output Directory: dist
```

Vercel env:

```env
VITE_API_BASE_URL=https://your-api-domain.example.com
VITE_API_TOKEN=same as backend API_TOKEN; leave empty if using Vercel Protection / Cloudflare Access
```

> ⚠️ `VITE_API_TOKEN` is **baked into the frontend JS bundle** — anyone visiting
> the page can read it in devtools. Treat it as a weak shared secret; on the
> public internet layer Vercel Protection or Cloudflare Access on top.

Cloudflare Tunnel:

```text
your-api-domain.example.com -> http://localhost:17821
```

For public deployments you almost certainly want `MAX_VIDEO_DURATION_SECONDS`,
`MAX_INFLIGHT_JOBS`, and `LLM_BASE_URL_ALLOWED_HOSTS` (see `CONFIG.md`).
