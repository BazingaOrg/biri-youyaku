# 2026-07-19 蒸馏转写并发化 + 轮询改 await

## 方案来源

deep-reasoner 与 Codex 独立设计后合成（对垒模式）。主体采用 deep-reasoner 的小切口方案；采信 Codex 的事实纠正：_guard 不覆盖 yt-dlp 下载、_io_semaphore 是下载/ASR 共用阶段级槽位、断点续跑依据 distill_runs+videos/*.md 而非 manifest。放弃（留作后续独立项）：下载/ASR 双信号量拆分、consumer_key schema 迁移、transcripts.py 边界模块。

## 设计要点

1. runner.py 新增完成信号 API（约 15 行）：
   - `_completion: dict[str, asyncio.Future]`；`async def await_job_completion(job_id) -> JobStatus`
   - 入口先查 DB：已终态直接返回（兜"复用已完成 job"与"抢先完成"竞态，也是 waiter 挂起的兜底）
   - 唯一解析点：`_spawn` 的 `add_done_callback` 中读 DB 终态解析 future（guard `if not fut.done()`），并清理 dict 条目
2. orchestrator.py：
   - `_do_prepare_transcripts` 改 gather + `asyncio.Semaphore(distill_transcript_concurrency)` fan-out；先过滤 `video_exists` 的视频
   - `_obtain_transcript` 改 create_job → start_job → `await runner.await_job_completion(job.id)` → 读 transcript；删 `_JOB_POLL_INTERVAL_SECONDS` 与轮询
   - 计数并发安全：同步自增 + 立即 `update_counters`，自增与写库之间不得有 await（实现纪律）
   - 单视频失败记 `add_failed_bvid` 跳过不中断；协程入口与拿到信号量后各查一次 `_is_cancelled`
   - `cancel_run` 联动 `runner.cancel_job()` 本 run 已 spawn 的 job（内存 `run_id -> set[job_id]`，不落库）
3. config.py：`distill_transcript_concurrency: int = 3`

## 步骤

1. [x] fast-worker 按上述实现 + 补测试（runner await 三态、fan-out 并发上限、失败不中断、取消传播、计数正确性、断点续跑回归）
2. [x] qa-runner：pytest（unset 代理）、ruff
3. [x] 文档：CONFIG.md 补 DISTILL_TRANSCRIPT_CONCURRENCY

## 实现记录

- 按方案落地：runner 新增 `_completion` dict + `await_job_completion`（DB 先查终态，`_spawn` done_callback 唯一解析并清理）；orchestrator fan-out（先滤 video_exists，Semaphore 控窗，保持原顺序，同步计数紧跟 update_counters）；`_run_job_ids` 记录 spawned job，cancel_run 联动 cancel_job，`_run_pipeline` finally 清理；config/CONFIG.md 加 DISTILL_TRANSCRIPT_CONCURRENCY=3。
- 偏离与理由：终态判断用严格 TERMINAL_JOB_STATUSES（不含 TRANSCRIPT_READY，后者对普通 job 是中间态，提前返回有风险）；job 跑完但 DB 查不到时 future 解析为 FAILED 而非挂起。
- 验证：pytest 143 passed、ruff 通过（fast-worker 与 qa-runner 各跑一遍）；orchestrator 新增/更新测试覆盖并发上限、失败隔离、跳过、取消传播。
- 遗留（后续独立项）：下载/ASR 双信号量流水线化；consumer_key 持久化 get-or-create（重启后可能重复建 in-flight 转写 job，代价为浪费一次转写，可接受）。

## 遗留项裁决（2026-07-19）

评估收益/成本后决定：
- 不做：双信号量流水线化（动 runner 核心，批量蒸馏低频，风险不对称）；consumer_key 迁移（触发罕见、代价仅一次转写）；transcripts.py 边界模块（耦合面已收敛到 await_job_completion 一个函数）；字幕落盘缓存（上层同视频复用已覆盖主场景，已删 config.py 过时注释）；列表行 memo（窗口化已压住）；web lint 脚本（无 eslint 栈，tsc 已在 build 中，不值得引入整套依赖）。
- 挂起观察：蒸馏续跑缓存动态清洗结果（省 token/调用），等实际频繁续跑出现痛感再做。
