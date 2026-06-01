# biri-youyaku

[中文](README.md) | [English](README.en.md)

> `要約`（ようやく / yōyaku）在日语里是「摘要、总结」，同音 `ようやく` 又有「终于」之意。
> `biri` 来自 Bilibili 的日语口语叫法 `ビリビリ`。
>
> 灵感：[linzzzzzz/openclip](https://github.com/linzzzzzz/openclip) · [IndieKKY/bilibili-subtitle](https://github.com/IndieKKY/bilibili-subtitle)

粘贴 B 站视频链接，先取字幕；没字幕则下载音频转写。一键生成摘要，也可以发到邮箱。

## 60 秒快速开始

需要 Python 3.11+、Node.js 18+、[uv](https://docs.astral.sh/uv/)、`npm`。

```bash
# 1. 拷一份配置 + 填你的 LLM_API_KEY（OpenAI / 通义 / Moonshot 等 OpenAI 兼容接口都行）
cp server/.env.example server/.env
$EDITOR server/.env

# 2. 一键起前后端 dev server（脚本会自动 cp web/.env、装依赖）
bash scripts/dev.sh
```

打开 <http://127.0.0.1:5173>，粘贴一个 B 站视频链接即可。

> 想用 Docker？`cp server/.env.example server/.env` 之后 `docker compose up --build`。

---

## 项目结构

- `web/`：前端（Vite + React）。
- `server/`：后端（FastAPI + SQLite）。
- `examples/email-worker/`：可选的 Cloudflare Worker 模板，把总结发到邮箱。
- `scripts/dev.sh`、`docker-compose.yml`：本地一键启动。

---

## 准备一份 LLM API Key

任何 OpenAI 兼容接口都行。常见选择：

| 供应商 | `LLM_BASE_URL` 示例 | 备注 |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | 标准接口 |
| Moonshot / Kimi | `https://api.moonshot.cn/v1` | 后端会强制 `temperature=1` |
| 通义千问 DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | |
| DeepSeek | `https://api.deepseek.com` | |
| 本地 ollama / vLLM | `http://localhost:11434/v1` | 模型名按本地实际 |

`LLM_MODEL` 填供应商支持的模型名（`gpt-4o-mini` / `moonshot-v1-32k` / `qwen-plus` 等）。

---

## 本地开发（手动）

不想用 `scripts/dev.sh`？分别起：

```bash
# 后端
cd server
cp .env.example .env       # 填 LLM_API_KEY
uv sync
uv run uvicorn biri_youyaku.app:app --reload --host 0.0.0.0 --port 17821

# 前端（新终端）
cd web
cp .env.example .env
npm install
npm run dev                # http://localhost:5173
```

---

## 可选功能

### B 站登录态（取私享视频 / 高画质字幕）

浏览器登录 B 站后，从 cookie 复制 `SESSDATA`，写到 `server/.env`：

```env
BILI_SESSDATA=你的-sessdata
# 大多数情况只配 SESSDATA 就够；某些接口需要再补
# BILI_BUVID3=
# BILI_BILI_JCT=
```

### 本地 ASR 转写（无字幕的视频）

需要 `ffmpeg` / `ffprobe`；Mac `brew install ffmpeg`，Ubuntu `apt install ffmpeg`。

**跨平台（默认）—— funasr CPU 后端**：

```bash
cd server
uv sync --extra asr     # 装 funasr + torch
# server/.env
ASR_MODEL=sensevoice    # 默认就是这个，可省
```

**Apple Silicon Mac（M1+）—— MLX 后端（推荐，15-30× 加速）**：

```bash
cd server
uv sync --extra asr-mlx # 装 mlx-audio + parakeet-mlx
```

可选 ASR 后端：

| `ASR_MODEL` | 适合 | 备注 |
| --- | --- | --- |
| `sensevoice` | 跨平台、Docker | funasr CPU，慢但兼容 |
| `sensevoice-mlx` | M 系列 Mac、中日韩视频 | 同模型同精度，吃 GPU/ANE |
| `parakeet-mlx` | M 系列 Mac、英语 / 欧语 | NVIDIA Parakeet TDT v3，WER 6.34%（超 Whisper-Large-v3） |
| `auto` | 不想纠结 | 按任务语言路由：CJK → sensevoice-mlx，其余 → parakeet-mlx |
| `faster-whisper` | 已有 whisper 工作流 | CTranslate2 优化版 |

Mac mini M4 推荐：`ASR_MODEL=auto`。

### 邮件发送

> 邮件**默认关闭**，需要自己起一个 webhook。仓库里给了一个 Cloudflare Worker 模板：

```bash
cd examples/email-worker
# 跟着 examples/email-worker/README.md 走，5 分钟部完
```

部完后到 `server/.env`：

```env
EMAIL_ENABLED=true
EMAIL_WEBHOOK_URL=https://biri-youyaku-mail.<account>.workers.dev
EMAIL_WEBHOOK_TOKEN=与 Worker 的 BIRI_YOUYAKU_TOKEN 一致
EMAIL_DEFAULT_RECIPIENT=you@example.com
```

启动时若开了 `EMAIL_ENABLED` 但任一必填值为空，后端会打 WARN；创建任务时也会拒
绝，避免发到错误地址。

---

## 部署到公网

一种常见架构：

- 前端部署到 Vercel；
- 后端跑在自己的机器（VPS / 树莓派 / 工作站）；
- 用 Cloudflare Tunnel 暴露后端为 HTTPS 域名；
- 邮件走 Cloudflare Worker + Resend（见上面）。

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

---

## API

- `GET /healthz`
- `GET /v1/config/defaults`
- `GET /v1/config/runtime`（公开，返回各项是否已配置）
- `GET /v1/usage?range=7d`
- `POST /v1/llm/models`
- `POST /v1/jobs`
- `POST /v1/jobs/preview`
- `GET /v1/jobs?limit=50&offset=0&cursor=...`
- `GET /v1/jobs/{id}`
- `GET /v1/jobs/{id}/stream`（SSE）
- `POST /v1/jobs/{id}/cancel`
- `POST /v1/jobs/{id}/resume`
- `POST /v1/jobs/{id}/retry`
- `POST /v1/jobs/{id}/transcript`（上传 / 覆盖字幕）
- `GET /v1/jobs/{id}/audio`
- `DELETE /v1/jobs`
- `DELETE /v1/jobs/{id}`
- `POST /v1/jobs/{id}/email`（重发邮件）

---

## 配置参考

`server/.env` 的所有可调项（默认值见 `server/biri_youyaku/config.py`）：

| 类别 | 变量 | 默认 | 说明 |
| --- | --- | --- | --- |
| 应用 | `APP_LOG_LEVEL` | `INFO` | uvicorn / 应用日志级别 |
| 应用 | `APP_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 多个用逗号分隔 |
| 鉴权 | `API_TOKEN` | 空 | 空 = 不校验 Bearer Token |
| B 站 | `BILI_SESSDATA / BILI_BUVID3 / BILI_BILI_JCT` | 空 | 仅在需要登录态时填 |
| ASR | `ASR_MODEL` | `sensevoice` | 或 `faster-whisper` |
| ASR | `ASR_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| ASR | `ASR_LANGUAGE_DEFAULT` | `auto` | |
| ASR | `SENSEVOICE_MODEL_DIR` | 空 | 自动下载 / 指定本地路径 |
| LLM | `LLM_API_KEY` | 空 | **必填** |
| LLM | `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容接口 |
| LLM | `LLM_MODEL` | `gpt-4o-mini` | |
| LLM | `LLM_TIMEOUT_SECONDS` | `300` | 单请求超时 |
| LLM | `LLM_MAX_RETRIES` | `2` | SDK 层重试 |
| LLM | `LLM_TEMPERATURE` | 空 | 留空走代码默认 |
| LLM | `LLM_CHUNK_TOKEN_THRESHOLD` | `30000` | 长字幕分段阈值 |
| LLM | `LLM_FORCE_TEMP_ONE_PREFIXES` | `kimi,moonshot` | 命中前缀强制 `temperature=1` |
| LLM | `LLM_SEGMENT_CONCURRENCY` | `3` | 段级总结并发数 |
| 摘要 | `SUMMARY_LANGUAGE` | `中文简体` | 输出语言 |
| 邮件 | `EMAIL_ENABLED` | `false` | |
| 邮件 | `EMAIL_WEBHOOK_URL / EMAIL_WEBHOOK_TOKEN / EMAIL_DEFAULT_RECIPIENT` | 空 | |
| 邮件 | `EMAIL_SUBJECT_TEMPLATE` | `[Biri-Youyaku] {{title}}` | 支持 `{{title}}` / `{{author}}` |
| 存储 | `AUDIO_STORAGE_DIR / SUMMARY_STORAGE_DIR / DB_PATH` | `data/...` | |
| 清理 | `AUDIO_RETENTION_DAYS` | `7` | |
| 清理 | `JOB_RETENTION_DAYS` | `180` | |
| 清理 | `ORPHAN_FILE_RETENTION_DAYS` | `3` | DB 不引用的孤儿文件多久后清 |
| 清理 | `STALE_RUNNING_FAIL_HOURS` | `4` | 非终态任务多久无心跳就置 FAILED |
| 清理 | `CLEANUP_INTERVAL_SECONDS` | `3600` | 清理循环周期 |
| 清理 | `WAL_CHECKPOINT_INTERVAL_HOURS` | `24` | WAL 截断周期 |
| 清理 | `DB_VACUUM_INTERVAL_DAYS` | `30` | VACUUM 周期 |
| 并发 | `MAX_CONCURRENT_JOBS` | `2` | 重 IO/CPU 段并发上限 |
| 并发 | `MAX_CONCURRENT_SUMMARIES` | `2` | LLM 总结并发上限 |

---

## License

MIT
