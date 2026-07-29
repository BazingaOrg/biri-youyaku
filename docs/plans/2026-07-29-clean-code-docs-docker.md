# 2026-07-29 Clean Code + 文档对齐 + Docker 自部署检查

## 背景

2026-07-26 clean-code 审计后，项目又落地知识库、历史费用/周报、蒸馏 video-only。本轮目标：文档与代码对齐、配置三方同步、Docker 路径一致、P1 surgical clean code。不做大重构、不做依赖大版本升级。

## 默认决策

- Docker Node → **22**（对齐 `.nvmrc` / README）
- LICENSE 版权行 **暂不动**
- 不拆 `web/src/lib/api.ts`、不引入 vitest
- Docker 以静态校验 + 注释对齐为主；有环境再 compose build

## 执行步骤

1. [x] 建立基线：pytest / ruff / web build
2. [x] 文档对齐：README 中/英、CONFIG.md、.env.example、DEPLOY.md 轻量补丁
3. [x] Surgical clean code：history 筛选 DRY、summary 原子写、LLM/auth 公开 API、dynamics 卫生
4. [x] Docker 对齐：Node 22、ASR/鉴权注释、web/.dockerignore
5. [x] 全量验证 + 本文件 implementation notes

## 成功标准

- [x] README 含知识库与历史内统计/周报；无独立 stats 页误导
- [x] CONFIG / .env.example 与 Settings 关键字段对齐；backup 示例端口 17821
- [x] Docker Node 与文档一致；ASR 默认行为文档可见
- [x] bulk-delete 与 history 筛选共享逻辑；summary 原子写；无跨包 `_private` LLM/auth 依赖
- [x] 验证命令通过或既有环境问题已隔离

## Implementation notes

### Baseline（Batch 0）

- 初检：`275 passed, 1 failed`（`test_delete_removes_terminal_job_and_files` → 缺 `knowledge_job_links`）；ruff F811（`routes/knowledge.py` 函数名遮蔽 import）；web build 通过。
- 上述失败为本轮前既有缺陷，本轮一并修复。

### 文档（Batch 1）

- `README.md` / `README.en.md`：知识库特性；历史页用量/周报（非独立 stats）；mermaid 增加 knowledge/weekly；compose vs Vercel 拆分；Docker 默认无 ASR extras。
- `CONFIG.md`：补 `OPENROUTER_MANAGEMENT_API_KEY`、`USAGE_FINGERPRINT_SECRET`、`WEEKLY_SUMMARY_TIMEZONE`、`KNOWLEDGE_TRANSCRIPT_INDEX_ENABLED`；backup curl 端口 8000→17821。
- `server/.env.example`：advanced / knowledge 提示补齐。
- `DEPLOY.md`：同机 compose 备选 + 默认 CORS 说明。
- `docs/enhancement-plan.md`、`docs/author-distill-status.md`：产品真相以 README 为准。

### Clean code（Batch 2 + baseline fixes）

- `jobs/repo.py`：`list_bulk_delete_candidates` 复用 `_history_filter_clauses`。
- 新增 `modules/storage/atomic.py`；`summary` / `distill` 共用原子写。
- LLM：公开 `complete` / `build_create_kwargs`；保留 `_complete` 等别名。
- auth：公开 `expected_token`；`app.py` 改用公开 API。
- ruff F811：`create_knowledge_backup` 重命名路由 handler。
- `routes/jobs.delete`：knowledge unlink best-effort，不阻断删任务。
- 测试：`test_delete_removes_terminal_job_and_files` mock unlink；`test_list_jobs_scope_cursor_response_contract` 在 COMPLETED 后 re-fetch job（修 flaky 1ms cursor）。
- P3：`@vitejs/plugin-react` 移至 devDependencies。

### Docker（Batch 3）

- `web/Dockerfile`、`docker-compose.dev.yml`：Node **22** alpine。
- `server/Dockerfile` / compose 注释：ASR 默认未装、`VITE_API_TOKEN` 弱密钥、端口说明。
- 新增 `web/.dockerignore`。
- 本机无 Docker CLI，未跑 `docker compose config` / build。

### Final validation

- `276 passed`（proxy cleared）
- `ruff check .` All checks passed
- `npm run build` OK（基线与中途均通过；devDep 调整后应仍通过）
- `git diff --check` OK

## Deviations

- 未执行完整 `docker compose build`（环境无 docker）。
- 未改 LICENSE 版权行。
- 未拆 `api.ts` / 未加 vitest。
- knowledge `atomic_write_bytes` 未与 text helper 合并（字节 vs 文本，保持不动）。

## Review issues and root causes

| 问题 | 根因 | 处理 |
| --- | --- | --- |
| 删除任务测失败 | unit test 打到真实 DB 的 knowledge unlink；旧库可能无表 | route best-effort + test mock |
| ruff F811 | 路由函数与 backup 模块 import 同名 | 重命名 handler |
| history cursor flaky | 用 create 时的 Job 对象算 terminal cursor，未含 completed_at | update 后 get_job |
| README 与代码漂移 | 知识库/周报后文档未跟 | 文档对齐本轮 |

## 未纳入本轮（后续可开）

- 前端 pure-function 测试 / ESLint
- GitHub Actions CI
- Vite/TS 大版本升级
- `to_thread` 真取消、trusted proxy
- enhancement-plan 剩余 UX
- LICENSE 作者信息
