# author-distill 进度

规格：`docs/specs/author-distill.md`（已批准 2026-07-07）。

| Step | 内容 | 状态 | commit / 备注 |
|---|---|---|---|
| 1 | 笔记 prompt 加两行原则（跳过插播恰饭；保留作者立场） | 完成 | `88df88f` |
| 2 | `_guard.py` 提取 + `dynamic.py` + dynamics 路由 | 完成 | `7202521` |
| 3 | distill 包 + distill_prompts + 迁移 + 路由 + 续跑 | 完成，**未提交**（工作区改动，等待用户确认后 commit） | 见下方文件清单 |
| 4 | UpPage 蒸馏按钮/弹窗/SSE 进度/结果预览 | 未开始 | — |

## Step 3 交付（工作区，未 commit）

新增：
- `server/biri_youyaku/modules/llm/distill_prompts.py`（三个蒸馏 prompt）
- `server/biri_youyaku/modules/llm/distill.py`（`extract_video_viewpoints` / `clean_dynamics_batch`）
- `server/biri_youyaku/modules/storage/distill.py`（`data/distill/<mid>/` 目录 helpers）
- `server/biri_youyaku/distill/{__init__,model,repo,orchestrator,assembler}.py`
- `server/biri_youyaku/routes/distill.py`
- `server/tests/test_distill_{repo,assembler,orchestrator,routes,job_integration}.py`

改动：
- `server/biri_youyaku/db.py`：新表 `distill_runs`（+ mid/status 索引）
- `server/biri_youyaku/config.py`：`distill_storage_dir` 设置
- `server/biri_youyaku/jobs/repo.py`：`list_jobs` 默认用 `json_extract` 排除 `task_type="distill"`
- `server/biri_youyaku/jobs/runner.py`：`task_type=="distill"` 在 `TRANSCRIPT_READY` 后直接
  收尾到 `COMPLETED`（镜像 `task_type=="audio"` 的提前收尾），`run_until_transcript` 与
  `run_after_resume` 都加了这个分支（后者兜底崩溃窗口竞态）
- `server/biri_youyaku/routes/jobs.py`：`task_type` Literal 加 `"distill"`
- `server/biri_youyaku/modules/bilibili/space.py`：`UpVideo` 加 `play` 字段（蒸馏
  frontmatter 需要，原接口忽略过这个字段）
- `server/biri_youyaku/app.py` / `routes/__init__.py`：注册 distill 路由 +
  启动期调用 `recover_unfinished_runs()`

## 关键决策（与 spec 描述不完全一致之处，已在代码注释里标注原因）

1. distill job 终态复用 `COMPLETED`（不新增枚举值），与 `task_type=="audio"` 一致。
2. 编排取消不用 `task.cancel()` 硬打断，靠 `distill_runs.status` + 每阶段边界检查——
   蒸馏没有需要立刻打断的长阻塞 IO。
3. 断点续跑（`recover_unfinished_runs`）整条 pipeline 重跑，靠每一步自身的幂等性
   （文件是否存在 / 转写是否可复用）跳过已完成的部分，不做细粒度的「从哪一步继续」
   状态机；`manifest.json` 只在 assembling 步骤由 assembler.py 整体重写，不是运行时
   续跑依据。
4. 转写补齐（Step 2）在 orchestrator 里是**顺序**处理每个视频（逐个建 job/复用/等待），
   不是并发 `asyncio.gather`——仍然“自然被现有信号量限流”，但避免了在「按视频检查
   取消」和「并发调度」之间做取舍。观点提取（Step 3）按 spec 显式要求走
   `asyncio.Semaphore(2)` 并发，单视频失败不影响其他视频。

## 验证

`server/` 下 `uv run pytest`：126 passed（101 原有 + 25 新增）。
`uv run ruff check .`：全过。触碰到的文件 `ruff format --check`：全过。
