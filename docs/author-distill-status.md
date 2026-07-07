# author-distill 进度

规格：`docs/specs/author-distill.md`（已批准 2026-07-07）。

| Step | 内容 | 状态 | commit |
|---|---|---|---|
| 1 | 笔记 prompt 加两行原则（跳过插播恰饭；保留作者立场） | 完成 | `88df88f` |
| 2 | `_guard.py` 提取 + `dynamic.py` + dynamics 路由 | 完成 | `7202521` |
| 3 | distill 包 + distill_prompts + 迁移 + 路由 + 续跑 | 完成 | `ac0c165` |
| 4 | UpPage 蒸馏按钮/弹窗/SSE 进度/结果预览 | 完成 | 本文件同 commit |

## 关键决策（与 spec 描述不完全一致之处，已在代码注释里标注原因）

1. distill job 终态复用 `COMPLETED`（不新增枚举值），与 `task_type=="audio"` 一致。
2. 编排取消不用 `task.cancel()` 硬打断，靠 `distill_runs.status` + 每阶段边界检查——
   蒸馏没有需要立刻打断的长阻塞 IO。
3. 断点续跑（`recover_unfinished_runs`）整条 pipeline 重跑，靠每一步自身的幂等性
   （文件是否存在 / 转写是否可复用）跳过已完成的部分；`manifest.json` 只在
   assembling 步骤由 assembler.py 整体重写，不是运行时续跑依据。
4. 转写补齐在 orchestrator 里**顺序**处理每个视频（仍被现有 job 信号量限流）；
   观点提取按 spec 走 `asyncio.Semaphore(2)` 并发，单视频失败不影响其他视频。
5. bvid 去重两查询（`find_completed_by_bvid` / `summary_status_for_bvids`）默认排除
   distill job——它们 COMPLETED 但没有总结，否则会污染普通去重与 UP 页「已总结」
   标记；蒸馏编排器复用转写时显式传 `include_distill=True`。
6. `UpVideo.play` 解析容错 `"--"`（转码中/隐藏播放数），避免整页投稿列表失败。
7. `fetch_all_dynamics` 跳过「旧置顶动态」而不是把它当成「已翻到旧内容」的停止信号
   （置顶常年挂在第一页最前，pub_ts 可能早于时间窗）。
8. 前端 SSE 两种载荷形态（订阅时全量快照 vs 增量事件计数打平在顶层），
   `DistillPanel` 的合并逻辑同时处理。

## 验证状态

- `server/` `uv run pytest`：127 passed；`ruff check` 全过；触碰文件 `ruff format --check` 全过。
  （注意：跑 pytest 前需 unset 代理环境变量，否则 socksio 缺失会误报一个用例。）
- `web/` `npm run build`（tsc + vite）：通过。
- 应用装配冒烟：`create_app()` 成功，6 条 distill 路由全部注册。
- **未做**：真实 UP 主的浏览器端到端蒸馏（需要 SESSDATA + 本地 ASR 长时间跑）。
  首次真实验证建议：选一个投稿 10~20 个、多数带官方字幕的作者，UpPage 点「蒸馏语料」，
  观察 `data/distill/<mid>/` 产物与 SSE 进度；中途重启服务验证续跑。

## 语料包产物（给蒸馏 skill 的输入契约）

```
data/distill/<mid>/
  manifest.json      # 作者信息、参数、数量、时间范围、per-video 状态、failed 列表
  videos/<bvid>.md   # 每视频观点提取（frontmatter：title/bvid/pubdate/duration/play）
  dynamics.md        # 清洗后动态，时间线 + 类型标注
  corpus.md          # 组装后的单文件语料包（项目外创建蒸馏 skill 时直接喂这个）
```
