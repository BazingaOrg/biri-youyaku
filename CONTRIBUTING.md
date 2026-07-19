# 贡献指南

欢迎 PR / issue（中文或英文都行）。这是一个个人维护的开源项目，规则尽量轻。

## 环境

- Python 3.11+、Node.js 22+（见 `.nvmrc`）、[uv](https://docs.astral.sh/uv/)、`npm`
- 可选：`ffmpeg`（本地 ASR 转写需要）

## 本地起服务

```bash
cp server/.env.example server/.env   # 至少填 LLM_API_KEY
bash scripts/dev.sh                  # macOS / Linux / WSL
# Windows：powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

## 跑测试 / lint

```bash
cd server
uv sync --extra dev
uv run pytest -q
uv run ruff check .          # lint
# uv run ruff format .       # 可选：想统一格式自己跑

cd ../web
npm install
npm run build           # 包含 tsc 类型检查
```

提交前请确保上面这套本地检查全绿。

## Commit / PR

- 一个 PR 解决一件事。重构 + 功能混在一起的会被拆开。
- 改后端路由签名或对外 JSON 契约（尤其是加/改 `request: Request` 形参、增删响应字段）
  务必本地 `uv run pytest -q` 再提。`tests/` 里多数路由用例是**直接调用路由函数**的
  单测，签名漂移不会在类型层暴露，只会被 pytest 抓到。
- Commit message 现在时祈使句即可，中英文皆可，无强制规范（`fix: ...` / `feat: ...` 欢迎但不强求）。
- 涉及配置项变更，记得同步改 `server/.env.example` 和 [`CONFIG.md`](CONFIG.md) 的配置表。

## 风格

- Python：`ruff format`、`ruff check`，行宽 100，目标 py311。
- TypeScript：2 空格缩进。目前未配 ESLint，类型检查由 `npm run build` 里的 `tsc` 兜底；提交前请确保 `tsc` 不报错。
- 注释写「为什么」而不是「做了什么」，能从代码看出来的就别注释。

## 不要做的事

- 不要往项目里加遥测 / 统计 / 第三方上报。
- 不要把 `server/data/` 里的东西 commit 上来。
- 不要 commit `.env`、API key、cookie。
- 不要把 `*.egg-info/` / `__pycache__/` / `.DS_Store` 加进版本控制（`.gitignore` 已覆盖）。

## 报 bug 请附

- `curl http://127.0.0.1:17821/v1/version` 的输出
- 触发问题的视频 URL（如果不涉及私享视频）
- 后端日志最后 50 行
- 你的 `LLM_BASE_URL` 和 `LLM_MODEL`（**不要**贴 `LLM_API_KEY`）
