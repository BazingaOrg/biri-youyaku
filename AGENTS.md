# AGENTS.md

给 AI 编程助手（Cursor / Claude Code / Aider / Copilot Workspace 等）的代码库导览。
人类贡献者请优先看 `README.md` + `CONTRIBUTING.md`，本文档可补充全局视图。

## 项目一句话

粘 B 站视频 URL，后端拉字幕或转写音频，调 LLM 出 Markdown 摘要；前端实时流式显示，可选转邮件。

## 技术栈

- **后端**：FastAPI + SQLite，Python 3.11+，包管理用 [uv](https://docs.astral.sh/uv/)。流式走 SSE（`sse-starlette`）。
- **前端**：Vite + React + TypeScript + Tailwind。
- **抓数据**：`yt-dlp` 拿字幕 / 音频。
- **ASR**：`funasr`（CPU 通用）/ `mlx-audio`（Apple Silicon 加速）/ 可选 `faster-whisper`。
- **LLM**：`openai` SDK，任何 OpenAI 兼容 base_url。

## 目录速查

```
server/
  biri_youyaku/
    app.py            # FastAPI 入口、lifespan、全局异常处理
    config.py         # 单一 Settings（pydantic-settings），所有 env 都在这里
    auth.py           # 可选的 Bearer Token
    rate_limit.py     # slowapi 限流
    db.py             # SQLite 连接 + schema 迁移
    events.py         # SSE 事件总线
    logging.py        # 日志配置
    routes/           # FastAPI router：jobs / config / healthz
    jobs/             # 业务核心：repo / runner / pipeline / cleanup / model
    modules/
      bilibili/       # 抓视频元信息、字幕、音频
      asr/            # ASR 后端抽象（sensevoice / parakeet / faster-whisper）
      llm/            # LLM client + 分段总结 + 流式合并
      email/          # 转发到 Cloudflare Worker
      storage/        # 文件落盘（summaries / audio）
      transcript.py   # 字幕 / 转写结果的统一表示
  tests/              # pytest，asyncio_mode=auto

web/
  src/
    App.tsx
    pages/            # 各页面
    components/       # UI 组件
    hooks/            # 自定义 hooks（SSE 订阅、轮询等）
    lib/              # API client、工具
```

## 数据流（一个任务从 PENDING 到 COMPLETED）

1. `POST /v1/jobs`（`routes/jobs.py`）→ `jobs/repo.create_job` 入库 → `jobs/runner.start_job`。
2. `runner.run_until_transcript`：调 `modules/bilibili` 取元信息 + 字幕；没字幕则下音频 + 调 `modules/asr` 转写。
3. 拿到 transcript → `pipeline.summarize` → `modules/llm/client` 分段并流式输出。
4. 流过程中通过 `events.publish` 推 SSE chunk → 前端订阅 `GET /v1/jobs/{id}/stream`。
5. 完成后写 `data/summaries/<id>.md`，可选触发 `modules/email`。
6. `jobs/cleanup` 后台循环：清孤儿文件、checkpoint WAL、置僵尸任务。

## 关键约束

- **没有用户系统**：单后端就是单用户，靠可选 `API_TOKEN` 防外人。
- **SQLite WAL 模式**：`db.py` 里设了 `journal_mode=WAL`。改 schema 必走 `init_db` 里的 ALTER 兼容路径。
- **配置全集中在 `config.py`**：加新环境变量要同步改 `server/.env.example` + `CONFIG.md`（配置表）。
- **SSE 用 `sse-starlette`**：不要换 raw `StreamingResponse`，事件总线在 `events.py`。
- **LLM 调用统一过 `modules/llm/client.openai_client`**：HTTP client 按 `(api_key, base_url, timeout, max_retries)` 缓存复用。
- **防 SSRF**：用户传入的 `llm_base_url` 必须过 `routes/config._validate_llm_base_url`。
- **rate limit**：路由上 `@limiter.limit("...")` 标注，慎调阈值。

## 常做的事 → 走哪条路

- **加一个 LLM 供应商**：通常只改 `LLM_BASE_URL_ALLOWED_HOSTS` 默认值 + README 的供应商表。代码层 OpenAI 兼容就不用动。
- **加一个 ASR 后端**：在 `modules/asr/` 加新文件 + 注册到 `get_transcriber`，env 用 `ASR_MODEL=xxx` 切换。
- **加一个 API endpoint**：在 `routes/` 对应文件加路由，注意 `Depends(require_token)` 和 `@limiter.limit`。同时更新 README API 列表 + `CHANGELOG.md`。
- **加一个 env 配置**：`config.py` 加字段 → `.env.example` 加注释行 → `CONFIG.md` 加一行。
- **改 schema**：`db.py` 的 `SCHEMA` + `migrations` 字典里加 ALTER，记得允许旧库继续打开。

## 不要做的事

- 不要引入 ORM（SQLAlchemy / SQLModel）—— 仓库刻意只用裸 sqlite3，保持轻。
- 不要把任何遥测 / 统计 / 第三方 ping 加进去。
- 不要 commit `server/data/*`、`.env`、`*.egg-info/`、`__pycache__/`、`.DS_Store`。
- 不要在 `runner.py` 里同步阻塞 LLM/ASR 调用 —— 一切重 IO 必须走 `asyncio.to_thread` 或异步 client。
- 不要扩 README 长度 —— 公网部署细节去 `DEPLOY.md`，完整配置表去 `CONFIG.md`。

## 跑测试

```bash
cd server
uv sync --extra dev
uv run pytest -q
uv run ruff check .
# uv run ruff format .  # 可选：想统一格式自己跑，CI 不强制 format

cd ../web
npm install
npm run build
```

CI（`.github/workflows/ci.yml`）跑同一套。

## 排查 bug 的常用入口

- 后端日志：`logging.py` 里 logger 名都是 `biri_youyaku.<module>` 前缀，按需 `APP_LOG_LEVEL=DEBUG`。
- 任务状态：`sqlite3 server/data/biri_youyaku.db "SELECT id, status, error_stage, error_message FROM jobs ORDER BY created_at DESC LIMIT 10;"`
- 流事件历史：SSE 是无状态推送，要重放只能看 DB 的 `stage_timings_json` 和 `token_usage_json`。
- 版本号：`curl /v1/version`。
