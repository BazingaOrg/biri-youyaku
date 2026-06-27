# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- **重复视频去重**：`POST /v1/jobs` 创建时按 BV 号判重，命中「已完成」的同一视频直接复用旧总结
  （返回 `deduped: true`、不新建任务、不重复烧 token），前端 toast「这条之前总结过，已打开」。
- **按 UP 主浏览投稿**：`GET /v1/up/{mid}/videos`（WBI 签名 + 匿名 buvid/dm 指纹 + cookie jar
  规避风控）列出某 UP 全部投稿并标记哪些已总结，未总结可一键建任务（留在列表、乐观标「进行中」）；
  `GET /v1/up/resolve` 把主页链接 / UID / 视频链接解析成 mid。支持 最新/最热 排序、标题搜索、滚动加载。
  入口：视频页作者名 chip、历史每条作者名、首页「按 UP 主浏览投稿」。
- **主题标签**：总结完成后用一次轻量 LLM 调用提炼 3-6 个标签（`generate_tags` + `TAGS_PROMPT`），
  存 `tags_json` 列、完成页 chip 展示、历史页按标签筛选；启动时后台幂等回填历史无标签任务。
- **思维导图**：完成页「脑图」tab，用 mind-elixir 把已存 markdown 实时解析成只读导图（历史也能出图、
  不额外调 LLM），可导出 SVG/PNG，懒加载。
- **字幕原文 + 跳转**：完成页「字幕原文」tab，时间戳点击用 B 站 `?t=秒` 深链跳到对应时间；带行内搜索。
- **下载字幕（SRT）**：完成页新增按钮，导出标准 .srt（兜底缺失时间戳、清洗搜索高亮 HTML）。
- **完成页改版**：笔记 / 脑图 / 字幕原文 三 tab；笔记 tab 桌面端 TOC 目录侧边栏（滚动高亮 + 点击跳转）；
  全局「回到顶部」浮标；分段总结进度条；成本/耗时（tokens）一行。
- **`jobs` 加 `mid` 列**：抓 meta 时落 UP 的 uid，并回填同作者的历史任务，作者名可直接点开「全部投稿」。
- `GET /v1/version` 返回后端版本号，方便用户报 bug 时贴版本。
- `docker-compose.dev.yml`：开发模式带 hot reload。
- `scripts/dev.ps1`：Windows PowerShell 一键启动脚本。
- README 加入架构 Mermaid 图、ollama 本地 recipe、成本参考、隐私声明。
- `CONTRIBUTING.md` / `SECURITY.md` / `CHANGELOG.md` / `.github/` 模板。
- GitHub Actions CI：server lint + pytest、web typecheck + build、docker build 烟囱测试。
- `.pre-commit-config.yaml`：server 端 ruff format/check + trailing-whitespace / EOF / gitleaks 等通用钩子。
- `AGENTS.md`：给 LLM 编程辅助工具的代码库导览。
- `web/vercel.json` + `web/nginx.conf`：SPA fallback，刷 `/jobs/<id>` 不再 404。
- `web/nginx.conf` 开 gzip：仅压缩文本类资源。
- `docker-compose.yml` `VITE_API_BASE_URL` 支持环境变量覆盖（跨机部署用）；dev 文件挂载加 `:cached` 提升 macOS 性能。
- **后端 clean code**：
  - `jobs/runner.py` 4 个模块级 dict（`_tasks` / `_cancel_requested` / `_job_llm_api_keys` / `_stage_started_at`）收成 `_JobRegistry`；`forget(job_id)` 一次清理。
  - 抽 `_job_lifecycle` async context manager，收敛 `run_until_transcript` / `run_after_resume` 两份近乎一致的 `try/except (CancelledError) / except Exception / finally` 收尾。
  - `jobs/repo.py` `_row_to_job` / `_row_to_job_lite` 合并为同一函数（`lite=True` 参数），缺列读 helper 提取；setter 全过 `_set(job_id, **fields)` 通用辅助，删 90% UPDATE 模板。
  - 行数：`runner.py` 函数粒度更细、`repo.py` 519 → 444。
- 后端测试 `test_runner_pause.py` 改用 `runner._registry.reset_for_tests()` 替代直接 monkeypatch 4 个模块 dict。
- Toast 支持任务名副标题（终态相关提示带上视频标题，过长省略号截断）。
- `docs/code-review-2026-06-14.md`：全量评审报告（clean code / UI / UX / 样式 / 文档对齐）。

### Removed
- 清掉兼容/死代码，专注链路整洁：
  - 未接入前端的 endpoint：`POST /v1/jobs/preview`、`POST /v1/llm/models`、
    `POST /v1/jobs/{id}/transcript`、`GET /v1/usage`（去重已折进 create_job）。
  - 弃用字段 `api_token_required`（用 `auth_mode`）、死字段 `JobOptions.email_recipient`
    （webhook 永远发默认收件人）、`resolve_temperature` 的无用 `model` 参数。
  - 遗留列 `content_hash` / `segments_json`（启动时尽力 DROP，sqlite ≥3.35）。
  - 前端死代码 `resumeJob` client。

### Changed
- **总结/邮件改为服务端自动续跑**：拿到字幕后后端同一条 task 直接续到总结→标签→邮件→完成，
  不再停在 `TRANSCRIPT_READY` 等前端 `/resume`——关掉浏览器也会照常出总结、发邮件；重启恢复
  会自动续跑残留的 `TRANSCRIPT_READY`。前端移除 `useAutoResume`。
- 标签提炼加 60s 超时，避免拖慢「完成→发邮件」；`resend_email` 失败回 502 带真实原因并更新 `email_error`。
- README 拆分：主 README 只保留 Quickstart + 架构 + 主要特性；公网部署移到
  `DEPLOY.md`，完整配置参考表移到 `CONFIG.md`。
- 启动期未配 `LLM_API_KEY` 时打 WARN，job 失败时错误信息直接指向 `server/.env`。
- 「名字 / 灵感」放到 README 顶部。
- **Prompt 重写**：单段 / 合并 prompt 全改为「TL;DR + 时间脉络笔记 + 收束」结构，砍掉
  原「核心要点」「详细笔记」「结论」三层重复段。
- **Toast 触发条件收紧**：终态 toast 只在「本会话里见过 running 状态」的转移上弹；
  直接打开历史已完成 / 失败任务不再弹（状态已在 MetaBar 上展示）。
- **修复 race**：
  - `useJob` 切换 jobId 时清空旧 state + AbortController 取消上一个挂着的请求；
  - `routes/jobs.py:stream_job` 把 snapshot 移到 subscribe 之后，避免「snapshot
    与订阅之间状态跳转」导致前端永远停在中间态。
- Toast 图标 / 关闭按钮垂直对齐修正。
- `HistoryDrawer.onDeleted` 回调签名扩成 `(jobId, title?)`，让上层 toast 显示「已删除 · 视频标题」。
- `docs/improvement-plan.md` 归档：按 2026-06-14 实际状态标记完成 / 过期项。

### Removed
- 早期 `makunabe` 重命名残留（`server/data/makunabe.db` / `server/makunabe_server.egg-info/`）。
- `docs/` 目录中的设计/优化笔记（已归档）。

## [0.1.0] - 2026-05

首个内部可用版本：
- B 站字幕 / yt-dlp 音频下载 → 本地 ASR（SenseVoice / Parakeet / faster-whisper）→
  OpenAI 兼容 LLM 摘要的完整流水线。
- FastAPI + SQLite 后端，Vite + React 前端，SSE 流式输出。
- 可选 Cloudflare Worker 邮件转发。
- Docker / Compose 部署。
