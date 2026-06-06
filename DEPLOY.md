# 部署到公网 / Deploy to the internet

[中文](#部署到公网) | [English](#deploy)

---

## 部署到公网

一种常见架构：

- 前端部署到 Vercel；
- 后端跑在自己的机器（VPS / 树莓派 / 工作站）；
- 用 Cloudflare Tunnel 暴露后端为 HTTPS 域名；
- 邮件走 Cloudflare Worker + Resend（见 `examples/email-worker/`）。

### 推荐方案：Cloudflare Access（SSO 白名单）

适合**只给自己 / 几个朋友用**的部署。后端不用维护 token，浏览器走 SSO 自动鉴权。

1. CF Zero Trust → Access → Applications → **Add an application** → Self-hosted。
2. Application domain 填后端 tunnel 域名（如 `api.example.com`）。
3. Add a policy：Action = Allow，Include 选 `Emails`，填你自己邮箱（要给朋友用就一起加）。
4. Session duration 建议 24h 或更长——你自己用没必要短。
5. 创建完后到该 application 的 Overview，复制 **Application Audience (AUD) Tag**。

后端 `server/.env`：

```env
CF_ACCESS_TEAM_DOMAIN=your-team.cloudflareaccess.com  # 不带 https://
CF_ACCESS_AUD=<上一步复制的 AUD tag>
APP_CORS_ORIGINS=https://your-frontend-domain.example.com
# API_TOKEN 留空——CF Access 已经处理鉴权
```

Vercel 前端：

```env
VITE_API_BASE_URL=https://your-api-domain.example.com
# VITE_API_TOKEN 留空——浏览器走 CF SSO 自动带 cookie
```

> 首次访问前端：CF 会弹 SSO 登录页 → 完成后跳回应用 → 浏览器自动带 `CF_Authorization` cookie。
> 之后 session duration 内无感。

> 本地 dev 不受影响：直接跑 `localhost:5173 → localhost:17821`，`.env` 里 CF_ACCESS_*
> 和 `API_TOKEN` 都留空即可。

### 兜底方案：静态 Bearer Token（VITE_API_TOKEN）

后端 `server/.env`：

```env
API_TOKEN=用 `openssl rand -hex 32` 生成
APP_CORS_ORIGINS=https://your-frontend-domain.example.com
```

Vercel 环境变量：

```env
VITE_API_BASE_URL=https://your-api-domain.example.com
VITE_API_TOKEN=与后端 API_TOKEN 一致
```

> ⚠️ `VITE_API_TOKEN` 会**打进前端 JS bundle**，任何访问页面的人都能在 devtools 看到。
> 当成「弱口令」用，挡爬虫够；想认真防滥用请走上面的 CF Access 方案。

### Vercel 前端项目设置

```text
Framework: Vite
Root Directory: web
Build Command: npm run build
Output Directory: dist
```

### Cloudflare Tunnel

```text
your-api-domain.example.com -> http://localhost:17821
```

公网部署强烈建议配上 `MAX_VIDEO_DURATION_SECONDS`、`MAX_INFLIGHT_JOBS` 和
`LLM_BASE_URL_ALLOWED_HOSTS`（详见 `CONFIG.md`）。

---

## Deploy

A common setup:

- Frontend on Vercel.
- Backend on your own machine (VPS / Raspberry Pi / workstation).
- Cloudflare Tunnel to expose the backend as HTTPS.
- Email via Cloudflare Worker + Resend (see `examples/email-worker/`).

### Recommended: Cloudflare Access (SSO allow-list)

Best fit when the deployment is just for **you and a few friends**. No tokens
to manage; the browser handles SSO transparently.

1. CF Zero Trust → Access → Applications → **Add an application** → Self-hosted.
2. Set Application domain to your backend tunnel domain (e.g. `api.example.com`).
3. Add a policy: Action = Allow, Include = `Emails`, fill in your own email
   (plus any friends you want to share with).
4. Session duration: 24h or longer — there's no reason for it to be short for
   personal use.
5. After creating the application, open its Overview tab and copy the
   **Application Audience (AUD) Tag**.

Backend `server/.env`:

```env
CF_ACCESS_TEAM_DOMAIN=your-team.cloudflareaccess.com   # no https://
CF_ACCESS_AUD=<the AUD tag you just copied>
APP_CORS_ORIGINS=https://your-frontend-domain.example.com
# Leave API_TOKEN empty — CF Access handles auth.
```

Vercel frontend env:

```env
VITE_API_BASE_URL=https://your-api-domain.example.com
# Leave VITE_API_TOKEN empty — the browser carries the CF SSO cookie automatically.
```

> First visit: CF shows the SSO page → you sign in → browser is redirected back
> with the `CF_Authorization` cookie set. Within the session duration it's
> completely invisible afterwards.

> Local dev is unaffected: keep running `localhost:5173 → localhost:17821` and
> leave the CF_ACCESS_* and `API_TOKEN` values blank.

### Fallback: static Bearer Token (VITE_API_TOKEN)

Backend `server/.env`:

```env
API_TOKEN=$(openssl rand -hex 32)
APP_CORS_ORIGINS=https://your-frontend-domain.example.com
```

Vercel env:

```env
VITE_API_BASE_URL=https://your-api-domain.example.com
VITE_API_TOKEN=same as backend API_TOKEN
```

> ⚠️ `VITE_API_TOKEN` is **baked into the frontend JS bundle** — anyone visiting
> the page can read it in devtools. It's a weak shared secret; good enough to
> deter crawlers but not actual abuse. For real protection use the CF Access
> path above.

### Vercel project settings

```text
Framework: Vite
Root Directory: web
Build Command: npm run build
Output Directory: dist
```

### Cloudflare Tunnel

```text
your-api-domain.example.com -> http://localhost:17821
```

For public deployments you almost certainly want `MAX_VIDEO_DURATION_SECONDS`,
`MAX_INFLIGHT_JOBS`, and `LLM_BASE_URL_ALLOWED_HOSTS` (see `CONFIG.md`).
