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
VITE_API_TOKEN=与后端 API_TOKEN 一致
```

> ⚠️ `VITE_API_TOKEN` 会**打进前端 JS bundle**，任何访问页面的人都能在 devtools 看到。
> 当成「弱口令」用，挡爬虫够；想认真防滥用就别公开 Vercel 域名，或上 Cloudflare Access / Vercel Protection 加一层。

**SPA 路由 fallback**：仓库自带 `web/vercel.json`，把所有路径 rewrite 到 `/index.html`，
由 wouter 接管路由。**Root Directory 必须设 `web/`**（与 `vercel.json` 同目录），否则
Vercel 找不到这个配置，直接刷 `/jobs/<id>` 会得到 Vercel 404 页（`hnd1::xxx-…` 那种）。

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
VITE_API_TOKEN=same as backend API_TOKEN
```

> ⚠️ `VITE_API_TOKEN` is **baked into the frontend JS bundle** — anyone visiting
> the page can read it in devtools. Treat it as a weak shared secret; good for
> deterring crawlers but not actual abuse. For real protection don't share the
> Vercel URL, or add Cloudflare Access / Vercel Protection on top.

**SPA routing fallback**: the repo ships `web/vercel.json` which rewrites every
path to `/index.html` so wouter can take over. **Root Directory must be `web/`**
(same folder as `vercel.json`), otherwise Vercel won't pick up the rewrite and
refreshing `/jobs/<id>` will hit Vercel's 404 page (the `hnd1::xxx-…` one).

Cloudflare Tunnel:

```text
your-api-domain.example.com -> http://localhost:17821
```

For public deployments you almost certainly want `MAX_VIDEO_DURATION_SECONDS`,
`MAX_INFLIGHT_JOBS`, and `LLM_BASE_URL_ALLOWED_HOSTS` (see `CONFIG.md`).
