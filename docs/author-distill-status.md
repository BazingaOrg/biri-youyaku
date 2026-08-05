# author-distill 进度

> 实施/进度笔记；产品真相以 README 为准。 / Progress notes; product truth is README.

规格：`docs/specs/author-distill.md`（已批准 2026-07-07；A2 修订为 video-only）。

| Step | 内容 | 状态 | commit |
|---|---|---|---|
| 1 | 笔记 prompt 加两行原则（跳过插播恰饭；保留作者立场） | 完成 | `88df88f` |
| 2 | `_guard.py` 提取 +（历史）`dynamic.py` + dynamics 路由 | 完成（A2 已移除动态） | `7202521` |
| 3 | distill 包 + distill_prompts + 迁移 + 路由 + 续跑 | 完成 | `ac0c165` |
| 4 | UpPage 蒸馏按钮/弹窗/SSE 进度/结果预览 | 完成 | 本文件同 commit |
| A2 | video-only 蒸馏：移除动态阶段与公开 dynamics API | 完成 | — |

## 关键决策（与早期 spec 描述不完全一致之处，已在代码注释里标注原因）

1. distill job 终态复用 `COMPLETED`（不新增枚举值），与 `task_type=="audio"` 一致。
2. 编排取消不用 `task.cancel()` 硬打断，靠 `distill_runs.status` + 每阶段边界检查——
   蒸馏没有需要立刻打断的长阻塞 IO。
3. 断点续跑（`recover_unfinished_runs`）整条 pipeline 重跑，靠每一步自身的幂等性
   （文件是否存在 / 转写是否可复用）跳过已完成的部分；`manifest.json` 只在
   assembling 步骤由 assembler.py 整体重写，不是运行时续跑依据。
4. 转写补齐 fan-out 受 `settings.distill_transcript_concurrency` 限制；
   观点提取按 `asyncio.Semaphore(2)` 并发，单视频失败不影响其他视频。
5. bvid 去重两查询（`find_completed_by_bvid` / `summary_status_for_bvids`）默认排除
   distill job——它们 COMPLETED 但没有总结，否则会污染普通去重与 UP 页「已总结」
   标记；蒸馏编排器复用转写时显式传 `include_distill=True`。
6. `UpVideo.play` 解析容错 `"--"`（转码中/隐藏播放数），避免整页投稿列表失败。
7. **A2**：流水线为 video-only（准备转写 → 提取 → 组装）。`FETCHING_DYNAMICS` 枚举
   与 SQLite 列 `dynamics_status` 保留作遗留兼容，新 run 不写入；不自动删除磁盘上
   已有的 `dynamics.md` / `corpus.md`。
8. 前端 SSE 两种载荷形态（订阅时全量快照 vs 增量事件计数打平在顶层），
   `DistillPanel` 的合并逻辑同时处理。

## 验证状态

- distill 相关 pytest + `from biri_youyaku.app import app` 冒烟见 A2 实现说明。
- **未做**：真实 UP 主的浏览器端到端蒸馏（需要 SESSDATA + 本地 ASR 长时间跑）。
- **2026-08-05 减法**：前端入口默认隐藏（`VITE_DISTILL_ENABLED=true` 启用）；后端 API 照常可用。

## 语料包产物（给蒸馏 skill 的输入契约）

```
data/distill/<mid>/
  manifest.json      # 作者信息、参数、数量、时间范围、per-video 状态、failed 列表
  videos/<bvid>.md   # 每视频观点提取（frontmatter：title/bvid/pubdate/duration/play）
  corpus.md          # 组装后的单文件语料包（video-only；项目外创建蒸馏 skill 时直接喂这个）
```
