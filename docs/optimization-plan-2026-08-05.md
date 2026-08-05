# Optimization Plan — 2026-08-05

> 对 biri-youyaku 全项目（web 前端、server 后端、文档、配置、Docker）的综合审计与优化建议。按优先级 P0–P3 排列。

---

## 总览

### 前端 (Web)

| # | 类别 | 事项 | 优先级 |
|---|---|---|---|
| F1 | UX | Workspace 加载失败时缺重试按钮 | P1 |
| F2 | UX | KnowledgePage 流式问答无法取消/中止 | P1 |
| F3 | UX | HitCard 展开逻辑 bug（全量文本+无 snippet 时出现无意义的展开按钮） | P1 |
| F4 | UX | 删除 running job 时不更新列表（行残留为"进行中"） | P1 |
| F5 | UX | 缺全应用 ErrorBoundary → 单组件崩溃白屏 | P1 |
| F6 | UX | Jump-to-bottom 浮标与 AppShell 工具区位置冲突 | P1 |
| F7 | UX | HistoryPage 移动端筛选藏太深、不可发现 | P2 |
| F8 | UX | SearchableSelect 缺键盘支持（Escape/箭头/aria） | P2 |
| F9 | UX | ScrollToTop 按钮无入场/退场动画 | P3 |
| F10 | UX | 缺少 404 页面 | P2 |
| F11 | UX | Tooltip span 与 aria-label 重复朗读 | P2 |
| F12 | UX | Toast 自动关闭不暂停于 hover | P3 |
| F13 | UX | main bundle 337KB 含 react-markdown → 首屏过大 | P2 |
| F14 | UX | WeekNavigator snap-mandatory 在桌面端滚动体验卡顿 | P3 |
| F15 | UX | UrlInput 缺 label、paste 按钮 loading 时不禁用 | P3 |
| F16 | Copy | Toast「清掉更早的 N 条」口语化 | P1 |
| F17 | Copy | ASR 误差提示文案不一致（两处不同说法） | P1 |
| F18 | Copy | KnowledgePage「块」/「产物」是后端术语 | P2 |
| F19 | Copy | KnowledgePage placeholder 两套文案风格冲突 | P2 |
| F20 | Copy | WeekNavigator 滑动提示在桌面端也显示 | P2 |
| F21 | Copy | WeeklySummaryCard FAILED 状态按钮显示「生成本周总结」而非重试 | P2 |
| F22 | Copy | MetaBar「字幕未定」语义不清 | P3 |
| F23 | Copy | status label 在 5 处重复定义 | P2 |
| F24 | Animation | HistoryPage 列表 animationDelay cap 在 6 → 7+ 项全同 | P2 |
| F25 | Animation | StepCarousel 过渡时长与 steps 进度条不一致 | P3 |
| F26 | Animation | WeekNavigator 柱高变化无过渡 | P3 |
| F27 | Code | 「返回」按钮在 3 页重复实现 | P1 |
| F28 | Code | `POP_OUT_FALLBACK_MS` 在两组件重复定义 | P1 |
| F29 | Code | `PROSE` 类字符串在 4 处定义（含跨层 import） | P1 |
| F30 | Code | HistoryPage.tsx 650 行单体组件 | P2 |
| F31 | Code | `newSummaryOptions` 在两页重复 | P2 |
| F32 | Code | dead code: `getLlmBalance`、`listJobs` 的 `offset` 参数 | P2 |
| F33 | Code | TERMINAL_STATUSES 在 4 处 re-declare | P2 |
| F34 | Code | 多个 magic number 未命名 | P2 |
| F35 | Code | MindmapView `as unknown as` 双重 cast | P3 |
| F36 | Code | `useStickToBottom` 中 dead eslint-disable 注释 | P3 |
| F37 | Code | DistillPanel 从 page 模块 import PROSE → 层违规 | P3 |
| F38 | Code | 3 个 week-label helper 各写一遍 | P2 |
| F39 | Code | `token_usage: Record<string, unknown>` 类型过宽 | P2 |
| F40 | Code | api.ts 近 400 行可按 domain 拆分 | P3 |
| F41 | Perf | `background-attachment: fixed` iOS Safari 滚动 jank | P1 |
| F42 | Perf | HistoryPage 所有行在任何 state 变化时全量重渲染 | P2 |
| F43 | Perf | KnowledgePage `locatorLabel` 每次调用创建 formatter | P3 |
| F44 | Perf | Inter 字体声明但未加载 | P3 |
| F45 | Perf | 缺 API_BASE_URL preconnect | P3 |

### 后端 (Server)

| # | 类别 | 事项 | 优先级 |
|---|---|---|---|
| S1 | Correctness | `add_token_usage` / `update_counters` / `upsert_document` read-modify-write 竞态 → token 丢失/counter 覆盖 | P0 |
| S2 | Security | `POST /v1/jobs` 接受任意 URL 无 scheme/host 校验 → SSRF | P0 |
| S3 | Correctness | bulk-delete signing secret 每次重启轮换 + 多 worker 不兼容 | P1 |
| S4 | Correctness | SSE stream `wait_for(25s)` = `ping=25s`，keepalive 可能竞态断流 | P1 |
| S5 | API | `/v1/knowledge/chat` 无 rate limit → 可烧 LLM 配额 | P1 |
| S6 | API | `/v1/knowledge/documents` 无分页/limit | P1 |
| S7 | Perf | `weekly/repo.py` `sources_for_week` 用 `SELECT *` + fingerprint 每请求 re-hash | P1 |
| S8 | Perf | 阻塞 IO 在 event loop：reindex / backup / purge 同步执行 | P1 |
| S9 | API | `SoftDeleteBody.confirm` 声明但从不读取 | P2 |
| S10 | Code | ASR backend 间 `_probe_duration` / `_emit` 多处重复 | P2 |
| S11 | Code | `now_ms()` 在 `repo.py` 和 `usage.py` 各定义一次 | P2 |
| S12 | Code | `to_stored_path` / `rewrite_*_paths_in_db` 在 knowledge 和 storage 间重复 | P2 |
| S13 | Code | `modules/asr/whisper.py` progress callback `except Exception: pass` 静默吞错 | P2 |
| S14 | Code | stage timeout 全部硬编码（30/120/1800/3600/1200/120s）→ 应进 Settings | P2 |
| S15 | Code | `_EXTRACT_CONCURRENCY = 2` 硬编码，与 `distill_transcript_concurrency` 不一致 | P2 |
| S16 | Perf | `knowledge/index.py` FTS delete 逐行执行（N+1） | P2 |
| S17 | Perf | `find_completed_by_bvid` 用 `SELECT *`（仅需判断 summary_path） | P2 |
| S18 | Perf | `distill/orchestrator.py` `_is_cancelled` 每轮循环查 DB | P3 |
| S19 | API | 500 错误泄露内部路径（knowledge backup route `detail=str(exc)`） | P2 |
| S20 | Config | `PRAGMA foreign_keys` 未开启 → `ON DELETE CASCADE` 死配置 | P2 |
| S21 | Code | `input` 作为 query 参数名 shadow builtin（`routes/up.py`） | P3 |
| S22 | API | 响应 envelope 不一致（`/v1/version` 裸返回 vs 其他 `{"ok":...}`） | P3 |
| S23 | Config | rate_limit X-Forwarded-For 非 CF 部署可伪造 | P3 |
| S24 | Config | config 字段缺 `Field(ge=...)` bounds | P3 |

### 文档与配置 (Docs/Config)

| # | 类别 | 事项 | 优先级 |
|---|---|---|---|
| D1 | Docs | README pre-commit 命令缺少 `--extra dev` → fresh clone 跑不过 | P0 |
| D2 | Docs | README pre-commit 列表漏了 `npm test` | P2 |
| D3 | Docs | DEPLOY.md EN 版字面 token `$(openssl...)` bug | P1 |
| D4 | Docs | `docs/` 无 index/README，新读者无法区分 archived vs current | P2 |
| D5 | Docs | `enhancement-plan.md` 已 archived 但仍放在 docs/ 根 | P2 |
| D6 | Docs | 历史 plans 中有未清理的勾选框/过时架构图 | P3 |
| D7 | Docs | 缺少测试/SSE 协议/Docker troubleshooting 文档 | P3 |
| D8 | Config | ruff: pyproject 锁 `<0.5`（0.4.10）但 pre-commit 用 0.6.9 → format 规则冲突 | P1 |
| D9 | Config | `.npmrc` 强制 npmmirror → 非中国用户 breakage + 2024 恶意包风险 | P1 |
| D10 | Config | docker-compose `VITE_API_TOKEN` 从 shell env 而非 `server/.env` 读取 → 用户踩坑 | P1 |
| D11 | Config | Vite 3/React 18/TS 4.8 版本较老，Vite 3 已 EOL | P2 |
| D12 | Config | 无 CI/CD | P3 |
| D13 | Config | 前端无 ESLint/Prettier | P3 |
| D14 | Config | tsconfig: `moduleResolution: "Node"` → 应改为 `"Bundler"`；缺 noUnused 检查 | P2 |
| D15 | Config | package.json 缺 `engines`；`test` 脚本用 shell glob | P2 |
| D16 | Docker | server/Dockerfile uv 安装不锁版本 | P1 |
| D17 | Docker | 两个容器跑 root | P2 |
| D18 | Docker | compose 缺 healthcheck | P2 |
| D19 | Docker | dev compose `npm install`（非 `npm ci`）+ 无 cache volume | P2 |
| D20 | Docker | 缺 BuildKit cache mount | P3 |
| D21 | Docker | nginx 可加 brotli | P3 |

---

## P0 — 立即建议（数据正确性 & 安全）

### S1. 并发 token 计数 & distill counter & document upsert 的 read-modify-write 竞态

**文件**：`server/biri_youyaku/jobs/repo.py:625-659`、`distill/repo.py:159-184`、`knowledge/repo.py:41-98`

- `add_token_usage` 做 SELECT → Python 加总 → UPDATE，无事务。分段总结的并发 `_summarize_chunked` 可同时调用，导致 segment token 丢失。
- `update_counters`/`add_failed_bvid` 同样 SELECT+UPDATE 无事务，并发蒸馏阶段间计数器丢失或 failed_bvids 被覆盖。
- `upsert_document` SELECT-then-INSERT 非原子，并发 register 命中 UNIQUE constraint。

**建议**：`add_token_usage` 改为 `UPDATE ... SET token_usage_json = json_set(..., '$.total_tokens', json_extract(...) + ?)` 原子自增。`update_counters` 同理。`upsert_document` 改用 `INSERT ... ON CONFLICT DO UPDATE`。

### S2. `POST /v1/jobs` 接受任意 URL 无校验 → SSRF

**文件**：`server/biri_youyaku/routes/jobs.py:70`

`CreateJobPayload.url` 无 scheme/host 校验，yt-dlp 会对任意 host（含 `file://`）发起请求。LLM base URL 有 `llm_url.py` SSRF 防护，job URL 没有。

**建议**：拒绝非 http/https scheme，限制 hosts 为 bilibili.com + b23.tv（加 config override）。

### D1. README pre-commit 命令缺 `--extra dev`

**文件**：`README.md:154`、`README.en.md:154`

`cd server && uv run pytest -q && uv run ruff check .` — pytest/ruff 在 `dev` optional extra 中，fresh clone 直接跑会失败。

**建议**：改为 `uv sync --extra dev` 后运行，或两步指令写清楚。

---

## P1 — 尽快做

### 前端

#### F1. Workspace 加载失败时缺重试按钮

**文件**：`web/src/pages/Workspace.tsx:366-376`

错误状态只渲染「新建」和「历史」按钮，无重试——但 `useJob` 暴露了 `refresh()`。加一个「重试」IconButton。

#### F2. KnowledgePage 流式问答无法取消

**文件**：`web/src/pages/KnowledgePage.tsx:215-272,441-449`

chatBusy 时 input 和两个按钮全 disabled，LLM 长回答无法中断（只能离开页面）。加「停止」按钮调用 `streamRef.current?.close()`。

#### F3. HitCard 展开按钮逻辑 bug

**文件**：`web/src/pages/KnowledgePage.tsx:49-50`

`needsExpand = full.length > preview.length || full.length > 160` — 当后端不发 snippet（preview===full）且 full>160 字符时，展开按钮出现但展开/收起内容完全相同。

**建议**：`needsExpand = full.length > preview.length`（仅 snippet 截断时才可展开）。

#### F4. 删除 running job 不更新列表

**文件**：`web/src/pages/HistoryPage.tsx:399-401`

删除运行中任务调 `deleteJob` 但不从列表移除行（不像终态任务有乐观删除+撤销）。行残留为"进行中"直到下次 reload。

**建议**：至少加 toast 提示，最好一致处理（从列表移除或显示 pending-deletion 态）。

#### F5. 缺全应用 ErrorBoundary

**文件**：`web/src/main.tsx` / `web/src/App.tsx`

ReactMarkdown 或 mind-elixir 单组件崩溃 → 整页白屏。加顶层 ErrorBoundary，友好中文 fallback + 刷新按钮。

#### F6. Jump-to-bottom 浮标与工具区位置冲突

**文件**：`web/src/pages/Workspace.tsx:389`、`web/src/components/AppShell.tsx:16`

Workspace 流式 jump floater 在 `bottom-5 right-20`，AppShell 工具在 `bottom-5 right-5`。短 viewport 时视觉冲突。

#### F16. Toast「清掉更早的 N 条」→ 文案统一

**文件**：`web/src/components/ToastProvider.tsx:100`

改为「清除更早的 N 条」与整体简洁风格对齐。

#### F17. ASR 误差提示文案不一致

**文件**：`web/src/pages/KnowledgePage.tsx:78,519`

命中卡片「ASR，可能有识别误差」vs 引用来源「ASR 转写，可能存在识别误差」——同一页面两种说法。统一为后者。

#### F27. 「返回」按钮在 3 页重复实现

**文件**：`web/src/pages/UpPage.tsx:23-39`、`HistoryPage.tsx:532`、`KnowledgePage.tsx:363-370`

UpPage 已有 `BackButton` 导出，HistoryPage 和 KnowledgePage 应复用。

#### F28. `POP_OUT_FALLBACK_MS` 重复定义

**文件**：`web/src/components/ConfirmDialog.tsx:4`、`ToastProvider.tsx:5`

提取到 `lib/animation.ts` 共享。

#### F29. `PROSE` 类字符串在 4 处定义

**文件**：`SummaryTabs.tsx:15-16`、`WeeklySummaryCard.tsx:15`、`steps.tsx:146`、`KnowledgePage.tsx:500-509`

且 `DistillPanel.tsx:17` 从 page 模块跨层 import PROSE。提取到 `lib/prose.ts`。

#### F41. `background-attachment: fixed` iOS Safari jank

**文件**：`web/src/styles.css:102`

body 的两个 fixed 背景在 iOS Safari 每帧 scroll 都重绘。改 `fixed` → `scroll` 或移到 `position: fixed` 伪元素。

### 后端

#### S3. bulk-delete signing secret 重启轮换 + 多 worker 不兼容

**文件**：`server/biri_youyaku/routes/jobs.py:97-98`

`secrets.token_bytes(32)` 在 import 时生成 → 重启后所有 preview token 失效，多 worker 时 worker A 签发被 B 拒绝。

**建议**：从 settings 派生 secret，或文档说明单 worker 限制。

#### S4. SSE keepalive 竞态

**文件**：`server/biri_youyaku/routes/jobs.py:465-517`

client `wait_for(25s)` = server `ping=25s` → stream 可能因刚好和自己的 keepalive 超时而断。

**建议**：client 30s 或 ping 20s。

#### S5. `/v1/knowledge/chat` 无 rate limit

**文件**：`server/biri_youyaku/routes/knowledge.py:73-100`

所有 LLM-spend 端点有限流但 chat 没有 → token holder 可无限烧配额。

**建议**：`@limiter.limit("10/minute")`。

#### S6. `/v1/knowledge/documents` 无分页

**文件**：`server/biri_youyaku/routes/knowledge.py:141-146`

与 `GET /v1/jobs`（有 cursor）不同，documents 一次性加载全部。

**建议**：加 `limit`/`cursor`。

#### S7. weekly summary 每请求重算 + `SELECT *`

**文件**：`server/biri_youyaku/weekly/repo.py:62-103`

`sources_for_week` 用 `SELECT *`（含 transcript JSON），`fingerprint()` 每请求 re-hash 全部 summary 文件。

**建议**：lite column projection + LRU cache on `(week_start, updated_at)`。

#### S8. 阻塞 IO 在 event loop

**文件**：`server/biri_youyaku/routes/knowledge.py:119-135,241-251`、`knowledge/lifecycle.py:246-259`

FTS rebuild、`shutil.copytree`、`shutil.rmtree` 同步跑在 async 请求线程。

**建议**：`asyncio.to_thread()` 包裹（`cleanup.py` 已对 VACUUM 这样做）。

### 配置

#### D3. DEPLOY.md EN 版字面 token bug

**文件**：`DEPLOY.md:78`

`API_TOKEN=$(openssl rand -hex 32)` 直接放在 .env code block 里，用户照抄得到字面量字符串。CN 版写法正确。

#### D8. ruff 版本 pyproject vs pre-commit 冲突

**文件**：`server/pyproject.toml:37`、`.pre-commit-config.yaml:17`

pyproject 锁 `<0.5`（0.4.10），pre-commit 用 v0.6.9 → format 规则不一致。

**建议**：对齐。或锁 pre-commit 到 0.4.10，或升 pyproject cap + full re-format。

#### D9. `.npmrc` 强制 npmmirror

**文件**：`.npmrc:1`

非中国用户 breakage + 2024 恶意包事件。移除 committed registry override。

#### D10. compose `VITE_API_TOKEN` 来源陷阱

**文件**：`docker-compose.yml:32`

`VITE_API_TOKEN: ${API_TOKEN:-}` 从 shell env 读，非 `server/.env`。用户设 server/.env 后 compose build 静默产出空 token。

**建议**：compose 注释显式说明，或提供 root `.env.example`。

#### D16. server/Dockerfile uv 不锁版本

**文件**：`server/Dockerfile:16`

`curl ... | sh` 安装任意版本 uv。pin 到 `--version 0.8.x`。

---

## P2 — 值得做，不紧急

### 前端

- **F7. HistoryPage 移动端筛选** (`HistoryPage.tsx:549-556`)：在筛选按钮上显示选中数量徽标，或改 chip 行。
- **F8. SearchableSelect 键盘支持** (`SearchableSelect.tsx:39-53`)：加 Escape/箭头/aria。
- **F10. 缺 404 页面** (`App.tsx:19-43`)：加 catch-all 路由。
- **F11. Tooltip span 重复朗读** (`IconButton.tsx:53`等)：tooltip span 加 `aria-hidden`。
- **F13. main bundle 过大**：lazy-load react-markdown（Workspace 路由改 lazy，或 SummaryTabs 内 Suspense）。
- **F18.「块」「产物」术语** (`KnowledgePage.tsx`)：改「索引片段」「内容」。
- **F19. KnowledgePage placeholder** (`KnowledgePage.tsx:303-304,422-424`)：chatEnabled 时两套文案统一语气。
- **F20. WeekNavigator 滑动提示** (`WeekNavigator.tsx:196`)：仅 coarse pointer 显示。
- **F21. WeeklySummaryCard FAILED 按钮文案**：加「重试生成」标签。
- **F23. status label 5 处重复**：提取 `lib/statusLabels.ts`。
- **F24. 列表 animationDelay cap** (`HistoryPage.tsx:517`)：`Math.min(index, 6)` → 去掉或提高到 20。
- **F30. HistoryPage.tsx 拆分**：提取 `useHistoryFilters/Jobs/Delete/Restore` hooks + `JobRow`/`BulkDeleteDialog` 组件。
- **F31. `newSummaryOptions` 重复** (`Workspace.tsx:174-178`、`HistoryPage.tsx:478`)：移到 shared hook。
- **F32. dead code** (`api.ts:311-322,484-487`)：删除 `getLlmBalance` 和 `listJobs` 的 `offset`。
- **F33. TERMINAL_STATUSES 4 处 re-declare**：统一 import `lib/jobStatus`。
- **F34. magic numbers 命名**：600px/64px/24px/200ms/300ms/1200ms/15s → 命名常量。
- **F38. 3 个 week-label helper**：统一到 `lib/format.ts`。
- **F39. `token_usage` 类型** (`api.ts:68`)：定义 `TokenUsage` 接口。
- **F42. HistoryPage 全量重渲染**：`renderJob` 提取为 `React.memo(JobRow)`。

### 后端

- **S9. `SoftDeleteBody.confirm` 不读取** (`routes/knowledge.py:33-35`)：校验或删除字段。
- **S10. ASR `_probe_duration`/`_emit` 重复**：提取到 `modules/asr/_util.py`。
- **S11. `now_ms()` 重复**：提取共享。
- **S12. stored-path 逻辑重复**：提取 `modules/storage/_paths.py`。
- **S13. whisper `except: pass`** (`whisper.py:62-69`)：加 `logger.exception`。
- **S14. stage timeout 硬编码** (`runner.py`)：移到 Settings 字段。
- **S15. `_EXTRACT_CONCURRENCY` 硬编码** (`orchestrator.py:46`)：加 config 项。
- **S16. FTS delete N+1** (`index.py`)：批量 delete。
- **S17. `find_completed_by_bvid` 用 `SELECT *`** (`repo.py:713-732`)：lite projection。
- **S19. 500 泄露路径** (`routes/knowledge.py:241-251`)：通用 500 + 日志。
- **S20. FK 死配置** (`db.py`)：启用 PRAGMA 或删 CASCADE + 文档。

### 文档/配置

- **D2. README 漏 web 测试**：补齐 `npm test`。
- **D4. `docs/` 无 index**：加 `docs/README.md`。
- **D5. `enhancement-plan.md` 归档**：移到 `docs/plans/`。
- **D11. 依赖升级**：至少 Vite 5/6 + TS 5（Vite 3 EOL）。
- **D14. tsconfig**：`moduleResolution: "Bundler"` + 开 `noUnusedLocals`。
- **D15. package.json**：加 `engines` + `test` 脚本改用 `node --test test/`。
- **D17. Docker root 容器**：切非 root user。
- **D18. compose healthcheck**：server 加 healthcheck，web 加 `condition: service_healthy`。
- **D19. dev compose `npm install`**：改 `npm ci` + cache volume。

---

## P3 — Nice to have

- **F9. ScrollToTop 动画**：加 `animate-pop`。
- **F12. Toast hover 暂停**：clear/reset timer on mouseenter。
- **F14. snap-mandatory → snap-proximity** 桌面端。
- **F15. UrlInput label + paste disabled**
- **F22. MetaBar「字幕未定」→「识别中…」**
- **F25. StepCarousel/steps 过渡时长统一**：`duration-200` → `duration-300`。
- **F26. WeekNavigator 柱高 transition**
- **F35. MindmapView 双重 cast**：proper type。
- **F36. dead eslint-disable** (`useStickToBottom.ts:47`)
- **F37. DistillPanel import PROSE 层违规** → 改 import `lib/prose`
- **F40. api.ts 拆分**：`lib/api/` 目录。
- **F43. Intl.DateTimeFormat 缓存**：模块级常量。
- **F44. Inter 字体未加载**：self-host 或移除。
- **F45. API preconnect**：加 `<link rel="preconnect">`。
- **S18. `_is_cancelled` 每轮查 DB**：内存 event。
- **S21. `input` shadow builtin** (`routes/up.py:17`)
- **S22. 响应 envelope 不一致**
- **S23. X-Forwarded-For 信任风险**
- **S24. config 缺 bounds 验证**
- **D6. 历史 plans 清理**
- **D7. 补 testing/SSE/Docker 文档**
- **D12. CI/CD**：`.github/workflows/ci.yml`
- **D13. ESLint/Prettier**
- **D20. BuildKit cache mount**
- **D21. nginx brotli**

---

## 已验证 OK ✅

- 全项目无 TODO/FIXME/HACK、无 `console.log`、无 `any` 类型
- ThemeToggle reduced-motion 正确处理、CSS 全局 reduced-motion kill-switch
- SSE 断流重连 + 竞态处理完善、ConfirmDialog 焦点陷阱正确
- 暗色模式 CSS 变量驱动全覆盖、API error 解析兼容 JSON/纯文本
- CONFIG.md ↔ config.py 逐字段一致、CN/EN README 同步
- 无硬编码 secret、无未使用的 npm 依赖
- HistoryPage 周导航 disabled 逻辑正确

---

## 建议落地顺序

1. **P0（半天）**：S1 并发竞态 → S2 job URL SSRF → D1 README 命令修正
2. **P1 前端（半天）**：F5 ErrorBoundary → F41 iOS jank → F3 HitCard bug → F4 delete running → F1/F2 缺按钮 → F27/F28/F29 代码去重 → F16/F17 文案
3. **P1 后端（半天）**：S3/S4 correctness → S5 rate limit → S6 pagination → S7/S8 perf
4. **P1 配置（半天）**：D3 → D8 → D9 → D10 → D16
5. **P2（2-4 天）**：前端大拆分（F30/F13/F42）+ 后端代码去重 + 文档补齐 + Docker 加固
6. **P3（按需）**：依赖升级 → CI/CD → 动画增强 → ESLint
