# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- `GET /v1/version` 返回后端版本号，方便用户报 bug 时贴版本。
- `docker-compose.dev.yml`：开发模式带 hot reload。
- `scripts/dev.ps1`：Windows PowerShell 一键启动脚本。
- README 加入架构 Mermaid 图、ollama 本地 recipe、成本参考、隐私声明。
- `CONTRIBUTING.md` / `SECURITY.md` / `CHANGELOG.md` / `.github/` 模板。
- GitHub Actions CI：server lint + pytest、web typecheck + build、docker build 烟囱测试。
- `.pre-commit-config.yaml`：server 端 ruff format/check + trailing-whitespace / EOF / gitleaks 等通用钩子。
- `AGENTS.md`：给 LLM 编程辅助工具的代码库导览。

### Changed
- README 拆分：主 README 只保留 Quickstart + 架构 + 主要特性；公网部署移到
  `DEPLOY.md`，完整配置参考表移到 `CONFIG.md`。
- 启动期未配 `LLM_API_KEY` 时打 WARN，job 失败时错误信息直接指向 `server/.env`。
- 「名字 / 灵感」放到 README 顶部。

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
