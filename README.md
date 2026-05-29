# biri-youyaku

[中文](README.md) | [English](README.en.md)

粘贴 B 站视频链接，先获取字幕；没有字幕时自动转写音频。确认内容后，一键生成摘要，也可以把摘要发送到邮箱。

## 名字

`要約`（ようやく / yōyaku）在日语里是“摘要、总结”，而同音的 `ようやく` 又有“终于、好不容易”的意思，所以这个名字有个小双关：点一下就把视频总结出来，终于不用从头看到尾也能看懂了。`biri` 来自 Bilibili 的日语口语叫法 `ビリビリ`，合在一起就是 `biri-youyaku`。

## 灵感来源

- [linzzzzzz/openclip](https://github.com/linzzzzzz/openclip)
- [IndieKKY/bilibili-subtitle](https://github.com/IndieKKY/bilibili-subtitle)

## 项目结构

- `web/`：前端页面。
- `server/`：后端服务，负责获取字幕、下载音频、转写音频、生成摘要、发送邮件和保存任务记录。

## 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js 18+
- npm

## 后端安装与启动

```bash
cd server
cp .env.example .env
uv sync
uv run uvicorn biri_youyaku.app:app --reload --host 0.0.0.0 --port 17821
```

如果需要本地 ASR 转文字：

```bash
cd server
uv sync --extra asr
```

后端 `.env` 常用配置：

```env
API_TOKEN=
LLM_API_KEY=你的大模型 API Key
LLM_BASE_URL=你的 OpenAI 兼容接口地址
LLM_MODEL=你要使用的模型名
APP_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

如果要让公网前端访问后端，把正式前端域名也加到 `APP_CORS_ORIGINS`。如果后端 `API_TOKEN` 留空，接口不会校验 Bearer token；部署到公网时建议一定配置。

建议部署时配置 `API_TOKEN`。可以这样生成：

```bash
openssl rand -hex 32
```

然后把生成结果填入后端 `.env`：

```env
API_TOKEN=生成出来的随机字符串
```

邮件功能是可选的：

```env
EMAIL_ENABLED=true
EMAIL_WEBHOOK_URL=https://your-mail-worker.example.com
EMAIL_WEBHOOK_TOKEN=你的邮件 webhook token
EMAIL_DEFAULT_RECIPIENT=you@example.com
EMAIL_SUBJECT_TEMPLATE=[Video Summary] {{title}}
```

部分视频可能需要登录态才能获取字幕或下载音频，可以按需配置 `BILI_SESSDATA`、`BILI_BUVID3` 和 `BILI_BILI_JCT`。

## 前端安装与启动

```bash
cd web
cp .env.example .env
npm install
npm run dev
```

本地访问：

```text
http://localhost:5173
```

前端 `.env`：

```env
VITE_API_BASE_URL=http://localhost:17821
# 后端 API_TOKEN 留空时这里也留空；如果后端有 API_TOKEN，这里填同一个值
VITE_API_TOKEN=
```

前端不会再弹窗让你输入 token。token 完全走环境变量，构建时注入。本地开发时建议两端都留空，免去鉴权；公网部署再配合反向代理（Vercel Protection、Cloudflare Access 等）做访问控制。

## 构建

```bash
cd web
npm run build
```

## 部署

一种常见部署方式：

- 前端部署到 Vercel。
- 后端运行在自己的机器或服务器上。
- 用 Cloudflare Tunnel 把后端暴露成一个 HTTPS API 域名。
- 邮件发送可以用 Cloudflare Worker + Resend。

Vercel 前端配置：

```text
Framework: Vite
Root Directory: web
Build Command: npm run build
Output Directory: dist
```

Vercel 环境变量：

```env
VITE_API_BASE_URL=https://your-api-domain.example.com
# 与后端 API_TOKEN 一致；若用反向代理鉴权可以留空
VITE_API_TOKEN=和后端一致的随机字符串
```

注意：`VITE_API_TOKEN` 会被打进前端 JS bundle，任何能访问页面的人都能在 devtools 里看到。把它当成「弱口令」处理，公网部署最好叠一层 Vercel Protection / Cloudflare Access。

Cloudflare Tunnel 示例：

```text
your-api-domain.example.com -> http://localhost:17821
```

邮件 Worker 的 `BIRI_YOUYAKU_TOKEN` 需要和后端 `EMAIL_WEBHOOK_TOKEN` 一致。后端会用 `Authorization: Bearer <EMAIL_WEBHOOK_TOKEN>` 调用 Worker。

后端部署时请同步设置：

```env
APP_CORS_ORIGINS=https://your-frontend-domain.example.com
API_TOKEN=生成出来的随机字符串
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
