# Subtraction Plan — 2026-08-05

> 对 biri-youyaku 做减法：砍掉未使用/未验证的功能、精简过度设计的交互、清理死代码。
> 原则：**删代码比加代码更需要谨慎**——每个删除项都注明"为什么"和"如何验证不影响现有功能"。
> **文档同步是每个批次的硬性步骤**：README / README.en / CONFIG.md / DEPLOY.md 与代码是一体的，
> CONFIG.md 与 config.py 逐字段对齐，改配置必须同步改文档；README 的 mermaid 架构图含 weekly 模块也要更新。

---

## 文档对齐规则（适用于所有批次）

| 文档 | 对齐要求 |
|---|---|
| `README.md` / `README.en.md` | 功能列表、mermaid 架构图、快速开始、Docker 引用、特性描述 |
| `CONFIG.md` | **逐字段对齐 `config.py`**：删设置项必须同步删文档行；`JOB_URL_ALLOWED_HOSTS` 等新增项要补 |
| `DEPLOY.md` | Docker 部署段落（dev compose 删除后）、邮件配置说明 |
| `server/.env.example` | 与 Settings 字段同步：删除的字段移除，新增的字段补齐 |
| `docs/` 各 plan/status 文档 | 已过时的计划标注 archived 或删除（如 Docker plan、cutover plan） |

---

## 总览

| # | 模块 | 行动 | 影响范围 | 风险 |
|---|---|---|---|---|
| 1 | Docker（dev compose） | 删除 | 低 | 无，dev.sh 已替代 |
| 2 | 邮件前端展示 | 精简 | 低 | 保留发送能力，仅缩小 UI |
| 3 | HistoryPage author/tag 筛选 | 删除 | 中 | 搜索框已覆盖同功能 |
| 4 | WeekNavigator | 简化 | 中 | 保留周切换，砍柱状条/status dot |
| 5 | WeeklySummary | 删除 | 中 | 每个视频已有独立总结 |
| 6 | 知识库文档管理 UI | 删除 | 低 | 保留后端内部调用链路 |
| 7 | 知识库 Chat | 删除 | 低 | 默认关闭，从未启用 |
| 8 | 蒸馏前端 | feature-gate | 低 | 隐藏按钮，后端保留 |
| 9 | config.py 维护类设置 | 移为常量 | 低 | 不影响 .env 已有配置 |
| 10 | 死脚本 + 冗余注释 | 删除 | 极低 | 一次性迁移脚本、WHAT 类注释 |

---

## 1. Docker dev compose — 删除

**为什么**：`scripts/dev.sh` 做了同样的事（env 检查 + `uv sync` + `npm run dev` + trap 清理），且项目 plan doc 自己承认"本机无 Docker CLI"。Docker 镜像默认不带 ASR extras——核心转写能力在 Docker 里不可用。

**具体**：
- 删除 `docker-compose.dev.yml`
- 保留 `docker-compose.yml`（生产自部署场景仍有价值）

**文档对齐**：
- `README.md:40`：删除"热重载用 `docker compose -f docker-compose.dev.yml up --build`"；保留 `docker compose up --build`（生产 compose 还在）
- `README.md:150` / `DEPLOY.md:13,66`：**保留**（引用的是生产 compose）
- `README.md:116` ASR 表格中 "跨平台、Docker" 措辞**保留**（生产镜像仍存在）
- 删除 `docs/plans/2026-07-29-clean-code-docs-docker.md`（本计划第 10 项）

**验证**：`scripts/dev.sh` 正常启动前后端；README 无 `docker-compose.dev` 残留引用。

---

## 2. 邮件前端展示 — 精简

**为什么**：用户偶尔用 Gmail 看总结，但邮件是投递通知而非交互功能。成功了不需要 UI（Gmail 已经收到了），只有失败时需要最小提示。

**具体**：
- **DoneView 操作栏**：删除重发邮件 IconButton（7→6 个按钮）
- **邮件错误 banner**：从整行 warning 卡片缩小为 JobStats 旁边的一行小字 `邮件未送达 · 重发`，点一下 trigger 重发
- **DoneView props**：删除 `onResendEmail`、`emailBusy` 两个 prop，改为 DoneView 内部 `useState` 自闭环
- **Workspace**：删除 `emailBusy` state + `resendCurrentEmail` 函数
- **保持不动**：步骤条的 EMAILING 步（"发送中…"→"已发送到邮箱"）、`resendEmail` API 函数、后端 webhook 模块、email-worker 示例

**文档对齐**：
- `README.md` / `README.en.md`：邮件特性描述改为"总结完成后发送到邮箱（可选，可配 `EMAIL_ENABLED`）"，删除任何暗示"重发"交互的措辞（若有）
- `CONFIG.md`：邮件 4 个配置项**保留**（`EMAIL_ENABLED`、`EMAIL_WEBHOOK_URL`、`EMAIL_WEBHOOK_TOKEN`、`EMAIL_DEFAULT_RECIPIENT`）——功能没删，只是 UI 精简
- `server/.env.example`：邮件段落保留不动

**验证**：配了邮件时 job 完成后自动发送；邮件失败时显示小字重发入口；未配邮件时不显示任何邮件 UI。

---

## 3. HistoryPage author/tag facet 筛选 — 删除

**为什么**：搜索框 placeholder 已经写了"搜标题、UP 主、BVID 或标签"——搜索本身就能匹配 UP 名和标签。两个 SearchableSelect + 移动端筛选面板 + 后端 `/v1/history/facets` 端点——约 150 行代码，提供的是搜索框已有的能力。

**具体**：
- 删除 `selectedAuthor`、`selectedTag`、`authorStats`、`tagStats` 四个 state
- 删除 `loadFacets`、`getHistoryFacets` import
- 删除桌面端 SearchableSelect + 移动端 filterPanel + chip 展示
- 删除 `hasFilters` 相关逻辑（只剩 `debouncedQuery`）
- 后端 `GET /v1/history/facets` 端点删除
- 搜索框变成唯一筛选入口（已经是了）

**文档对齐**：
- `README.md` 功能列表：如提到"按 UP 主/标签筛选"则删除，只留"搜索"
- `CONFIG.md`：无涉及（facet 无配置项）

**验证**：搜索 UP 主名/标签 → 结果正确过滤；历史页加载正常。

---

## 4. WeekNavigator — 简化

**为什么**：200 行的柱状条组件（比例高度、月份标、跨年标、snap 滚动、legend、status dot、脉冲动画）对个人工具是数据可视化的炫技。实际需要的是"切到上一周/下一周"。

**具体**：
- 删除柱状条的 bar 渲染、snap-scroll 容器、legend、status dot
- 保留 prev/next 箭头 + "本周"标签 + 周范围文字
- 后端 `/v1/weekly-summaries/statuses` 调用删除（前端不再需要 status dot）
- WeekNavigator 从 200 行压缩到 ~60 行

**验证**：历史页可以切换到不同周；周范围文字正确。

---

## 5. WeeklySummary — 删除

**为什么**：644 行代码维护一个功能——用 LLM 把本周所有 AI 总结再总结一遍。每个视频已有独立总结，按周分组的历史列表就在下方。边际价值极低，维护成本极高（6 状态机 + fingerprinting + lease + STALE 检测 + job 删除时的 mark_stale 钩子）。

**具体**：
- 删除 `server/biri_youyaku/weekly/`（repo.py 394 行 + orchestrator.py 185 行）
- 删除 `routes/weekly_summaries.py` 路由
- 删除 `web/src/components/WeeklySummaryCard.tsx`（259 行）
- 删除 HistoryPage 中 `WeeklySummaryCard` 的嵌入 + `weekSummaryStatuses` 状态 + `getWeeklySummaryStatuses` 调用
- 删除 job 删除链路中的 `mark_stale_for_job_ids` / `affected_week_starts_for_job_ids` 钩子
- 删除 `weekly_summary_sources` 和 `weekly_summaries` DB 表的创建语句（迁移保留，不删表）
- 删除 config 中 `weekly_summary_timezone` 设置

**文档对齐**：
- `README.md` mermaid 架构图（约 140 行）：删除 `api --> weekly[周报 weekly]` 节点和相关子节点
- `README.md` 功能列表：删除"周报/周总结"条目
- `CONFIG.md`：删除 `WEEKLY_SUMMARY_TIMEZONE` 行（中英两处）
- `server/.env.example`：删除 `WEEKLY_SUMMARY_TIMEZONE`
- `docs/plans/2026-07-28-history-cost-weekly-summary.md`：标注 archived（该计划主体是历史页，周报部分已砍）

**验证**：历史页正常显示按周分组的 job 列表；删除 job 不报错；后端启动正常；grep `weekly` 无代码残留引用。

---

## 6. 知识库文档管理 UI — 删除

**为什么**：KnowledgePage 下半部分是"已登记文档"管理区——软删除、恢复、永久删除（输入标题确认）、显示已删除 toggle。SaaS 级别的生命周期管理，对个人工具过度。删视频总结 = 删 job → 知识库自动同步删除。

**具体**：
- 删除 KnowledgePage 下半部分的文档列表 + 操作按钮（~150 行）
- 删除 `showDeleted` toggle、`softDeleteTarget`、`purgeTarget` 等 7 个 state
- 删除 `handleSoftDelete`、`handleRestore`、`handlePurge` 3 个函数
- 删除 `listKnowledgeDocuments`、`softDeleteKnowledgeDocument`、`restoreKnowledgeDocument`、`purgeKnowledgeDocument` 4 个前端 API 函数
- **后端保留**：`knowledge/lifecycle.py` 的 soft_delete/purge/restore 函数（job 删除链路需要内部调用），但删除独立的前端路由消费
- **保持不动**：知识库搜索（整个项目最有用的功能）

**文档对齐**：
- `README.md` 知识库段落：删除"文档管理/回收站/恢复"相关描述，只留"搜索总结与转写"
- `CONFIG.md`：删除 `KNOWLEDGE_SOFT_DELETE_DAYS` 行（随 lifecycle 简化不再暴露）；`KNOWLEDGE_BACKUP_DIR` 保留
- `server/.env.example`：同步删除对应行

**验证**：知识库页面搜索功能正常；删除 job 后知识库对应文档消失。

---

## 7. 知识库 Chat — 删除

**为什么**：`knowledge_chat_enabled` 默认 `false`——从第一天就没启用过。搜索已经能回答"我看过关于 X 的内容吗"。Chat 是同样的检索 + 多一层 LLM 调用 + 一套 chat UI + SSE 流。287 行后端 + citations 前端——纯炫技。

**具体**：
- 删除 `server/biri_youyaku/knowledge/chat.py`（287 行）
- 删除 `routes/knowledge.py` 中 `/v1/knowledge/chat` 路由
- 删除 KnowledgePage 中 chat 相关：`mode` state、`chatAnswer`、`citations`、`chatPhase`、`chatBusy`、`hasAsked`、`runChat`、`runAsAsk`、`activeMode` 逻辑、提问按钮
- 删除 `web/src/lib/sse.ts` 中 `openKnowledgeChatStream` 函数
- 删除 `knowledge_chat_enabled` 配置项
- 搜索框恢复为单一搜索模式（无需搜索/提问切换）

**文档对齐**：
- `README.md` 知识库段落：删除"提问/知识问答（RAG）"描述，只留"搜索"
- `CONFIG.md`：删除 `KNOWLEDGE_CHAT_ENABLED` 行（中英两处）
- `server/.env.example`：删除对应行
- `docs/plans/2026-07-29-personal-knowledge-base-rag.md`：标注 B 阶段（chat）已砍，仅 search 保留

**验证**：知识库搜索正常；页面无 chat 残留 UI；grep `knowledge_chat` 无残留引用。

---

## 8. 蒸馏前端 — feature-gate 隐藏

**为什么**：status doc 自己写"未做：真实 UP 主的端到端蒸馏"。`corpus.md` 的消费者是一个还不存在的项目外 skill。DistillButton 向用户暴露了一个从未验证的功能。

**具体**：
- 加 `VITE_DISTILL_ENABLED` 环境变量（默认 false）
- DistillButton 和 DistillPanel 用此变量 gating
- **后端保持不动**：distill 包代码是好的，不占运行时资源，将来启用只需改 env
- 删掉 UP 页的蒸馏按钮渲染

**文档对齐**：
- `README.md` 蒸馏段落：标注"实验性功能，默认隐藏（`VITE_DISTILL_ENABLED=true` 启用）"
- `docs/author-distill-status.md`：补充一行——前端已 gate，启用需 env
- `CONFIG.md` / `.env.example`：新增 `VITE_DISTILL_ENABLED` 注释行（web 侧）

**验证**：UP 主页面无蒸馏按钮；后端 distill 路由照常工作（API 调用不受影响）。

---

## 9. config.py 维护类设置 — 移为常量

**为什么**：176 行中约 30% 是单用户永远不会改的运维调参项。

**具体**：以下设置从 `Settings` 类删除，改为模块级常量：

| 设置 | 默认值 | 改为 |
|---|---|---|
| `llm_timeout_seconds` | 300 | `_LLM_TIMEOUT_S = 300` |
| `llm_max_retries` | 2 | `_LLM_MAX_RETRIES = 2` |
| `llm_chunk_token_threshold` | 30000 | `_LLM_CHUNK_THRESHOLD = 30000` |
| `llm_segment_concurrency` | 3 | `_LLM_SEGMENT_CONCURRENCY = 3` |
| `llm_thinking_enabled` | False | 保留（用户可能想改） |
| `audio_retention_days` | 7 | `_AUDIO_RETENTION_DAYS = 7` |
| `job_retention_days` | 180 | `_JOB_RETENTION_DAYS = 180` |
| `orphan_file_retention_days` | 3 | `_ORPHAN_RETENTION_DAYS = 3` |
| `stale_running_fail_hours` | 4 | `_STALE_FAIL_HOURS = 4` |
| `db_vacuum_interval_days` | 30 | `_VACUUM_INTERVAL_DAYS = 30` |
| `wal_checkpoint_interval_hours` | 24 | `_WAL_CHECKPOINT_HOURS = 24` |
| `cleanup_interval_seconds` | 3600 | `_CLEANUP_INTERVAL_S = 3600` |
| `distill_transcript_concurrency` | 3 | `_DISTILL_CONCURRENCY = 3` |
| `knowledge_soft_delete_days` | 30 | `_KNOWLEDGE_SOFT_DELETE_DAYS = 30` |

**文档对齐**：
- `CONFIG.md` 设置表（中英两处）：**删除以上 14 行**——CONFIG.md 与 config.py 逐字段对齐，这是硬性要求
- `server/.env.example`：删除对应注释块
- `README.md`：如引用这些设置名则同步删

**验证**：`uv run pytest` 全部通过；服务启动正常；CONFIG.md 与 config.py 字段数一致。

---

## 10. 死脚本 + 冗余注释 — 删除

**具体**：
- 删除 `server/scripts/knowledge_rewrite_paths.py`（一次性 DB 迁移，已完成）
- 删除 `server/scripts/knowledge_eval.py` + `server/biri_youyaku/knowledge/eval.py`（开发期检索质量评测门，Chat 删除后无意义）
- 删除 `docs/plans/2026-07-29-clean-code-docs-docker.md`（Docker 相关已过时）
- 删除 `docs/plans/2026-07-30-cloud-cutover-prep.md` + `docs/runbooks/cutover.md`（已取消的迁移方案）
- 精简注释：`StepCarousel.tsx:35`、`useStickToBottom.ts:18/31/45`、`AppShell.tsx:9` 的 WHAT 类注释

**文档对齐**：
- `CONFIG.md`：若提及 `knowledge_rewrite_paths.py` / `knowledge_eval.py` 则删除对应引用（备份/恢复脚本引用保留）
- `docs/runbooks/cutover.md` 删除后，检查 README/DEPLOY 是否还有指向它的链接，一并改指向或删除
- `docs/README.md`（若批次 5 已建 index）同步移除被删文档条目

---

## 建议执行顺序（每批含文档对齐）

| 批次 | 内容 | 文档对齐 | 预计删除行数 |
|---|---|---|---|
| 1 | Docker dev compose + 死脚本 + 冗余注释 | README 去 dev compose 引用；DEPLOY.md 去 Docker 段落；删 Docker plan doc | ~200 |
| 2 | 邮件前端精简 | README/CONFIG.md 邮件描述改为"发送到邮箱"；.env.example 保持 | ~40 |
| 3 | HistoryPage facet 删除 + config 瘦身 | CONFIG.md 删除 14 个设置行 + 注释；.env.example 同步；README 功能列表微调 | ~250 |
| 4 | WeekNavigator 简化 + WeeklySummary 删除 | README mermaid 架构图去 weekly 节点；CONFIG.md 删 `WEEKLY_SUMMARY_TIMEZONE`；.env.example 同步 | ~1000 |
| 5 | 知识库文档管理 UI 删除 + Chat 删除 | README 知识库描述去 chat；CONFIG.md 删 `KNOWLEDGE_CHAT_ENABLED`；.env.example 同步 | ~650 |
| 6 | 蒸馏前端 feature-gate | README 蒸馏描述标注"实验性（默认隐藏）"；CONFIG.md 备注 | ~15 |

**合计删除 ~2150 行（含文档），约 2-2.5 小时。**

> 每批收尾时统一跑：`uv run pytest` + `uv run ruff check` + `npm test` + `npm run build`，
> 并 `grep` 检查被删功能的关键词是否还有残留引用（如 `weekly_summary`、`email_error`、`knowledge_chat`）。
