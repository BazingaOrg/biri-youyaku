# Biri-Youyaku 性能 / 解耦 / 缓存 / 清理 / 体验 优化方案

> 文档目的：在不重写整体架构的前提下，把后端流水线的**热点**、模块边界、缓存命中率、磁盘 / 数据库占用、以及前端每一处微交互逐项收紧。与 `docs/optimization-plan.md`（侧重 UI 重设计与产品规划）互补，本文聚焦工程性优化。

---

## 0. 当前痛点速写

通读 `server/biri_youyaku/`、`web/src/` 与 `docs/optimization-plan.md` 后，未被覆盖或仅停留在「待做」的工程痛点：

1. **URL 解析在前端只去引导文字、不去追踪参数**：`web/src/lib/url.ts` 的 `extractBiliUrl` 只截 `https?://[^\s）)\]]+`，PC 分享链尾的 `share_source / vd_source` 直接进入 `createJob` → 落 DB；`b23.tv` 短链解析每次都走 `httpx` 重定向，没有任何缓存。
2. **B 站元信息 / 字幕请求无缓存层**：`meta.fetch` 每次同步打 `view` + `player/wbi/v2`，同一个 BV 多次任务会重复请求。
3. **SenseVoice / FasterWhisper 实例化策略不一致**：`SenseVoiceTranscriber` 借 `@lru_cache` 缓存模型；`pipeline.transcribe_audio` 仍 `FasterWhisperTranscriber() if ...` 每次 new，且两个后端都没显式 warmup。
4. **yt-dlp 进度回调有线程安全风险**：`audio.download` 在 `progress_hook` 里 `loop.call_soon_threadsafe(asyncio.create_task, on_progress(...))` —— `on_progress(...)` 在 worker 线程中就被调用并立即返回一个 coroutine；事件循环只能勉强 schedule，未捕获异常时会丢事件。
5. **`EventBus.publish` 是 async 但很多调用方用同步 lambda 包了一层**：`runner.py` 里多处 `lambda payload: event_bus.publish(...)` 返回的 coroutine 没被 await，直接被 yt-dlp / ASR 当回调丢掉，运行时会有 `RuntimeWarning: coroutine was never awaited`。
6. **`repo` 每次单查 / 单写都 `with connect()`，且 SQLite 连接共享**：`connect()` 是单例 + WAL，所以 `with connect()` 退出时 `Connection.__exit__` 会 COMMIT，但**不会 close**，看起来 OK；问题是它把整个 jobs 表当成一个大文档表，长 JSON（`transcript_json` / `chapters_json` / `stage_timings_json`）每次 `SELECT *` 都一起拉，列表页 30 条一拉就是十几兆。
7. **历史文件清理只删 `audio_path` 与 `summary_path`**：`data/audio/` 与 `data/summaries/` 下还会残留：(a) 任务被手动 DELETE 后忘记同步落盘的 cookie 临时文件 `biri-youyaku-bili-*.cookies.txt`（tempfile 路径异常时不会清）；(b) `tempfile.TemporaryDirectory(prefix="biri_asr_")` 异常退出时通常被回收，但 Python OOM kill 时残留；(c) `db_path` 的 WAL / SHM 文件无 vacuum。
8. **`recover_unfinished_jobs` 启动同步并发 `start_job`**：所有非终态任务一次性 create_task，没有节流，启动期容易把 LLM / 显存打满。
9. **SSE 在终态后 close 但 `notifiedRef` / `clearActive` 仅前端兜底**：服务端 `stream_finished_at` 已经记录，前端拿不到的话会重复触发 toast。
10. **前端历史抽屉每次开重新拉 30 条**：`refreshKey` 切换 → 整列表重拉，没有用 ETag / `If-Modified-Since`，移动端弱网会感到迟滞。
11. **任务卡片 / 进度文案的多个分支散在 `Workspace.tsx` 600+ 行单文件**：`buildSteps` / `renderStep` / `IdleView` / `RunningView` / `DoneView` 全堆一起，hot reload 受影响，未来加状态非常容易引入回归。

---

## 1. 性能优化

### 1.1 后端 IO 热点

| 位置 | 现状 | 改造 |
| --- | --- | --- |
| `meta.fetch` → `view` + `player/wbi/v2` | 每个新 job 都打 2 次外部 API | 加 **元信息 TTL 缓存**（key = `bvid+cid+page`，TTL 1h，进程内 + DB `content_hash` 二级查），preview / create 共用结果 |
| `resolve_short_url` | 每次新建任务走一次 302 | 同样加 LRU（key = b23 slug, TTL 24h）。 短链 → 长 URL 是确定性的，无需重复请求 |
| `subtitle.download` | 同步 GET，无重试 | 复用 `meta._get_with_retry` 的指数退避，并把 `httpx.AsyncClient` 改成模块级共享（连接池复用） |
| `email/webhook.send` | 每个请求 new 一个 client | 同上，模块级 `AsyncClient(http2=True, limits=...)` |
| LLM `_complete_stream` | 每次 `AsyncOpenAI(...)` 新建 client | 按 `(api_key, base_url)` LRU 缓存 client；当前每个 summarize 都创建，HTTP 连接复用率为 0 |

实施：在 `modules/_http.py`（新文件）里集中暴露 `bili_client()` / `email_client()` / `openai_client(...)`，所有调用方都拿单例。

### 1.2 ASR / 转写

- **`pipeline.transcribe_audio` 复用 transcriber 实例**：`SenseVoiceTranscriber` 已经靠 `@lru_cache` 缓存模型，但 `FasterWhisperTranscriber()` 每次 new。改成模块级单例 + 进入时 `await loop.run_in_executor(None, ensure_loaded)`，第一次 warmup，后续命中。
- **ffmpeg 切段并行化**：当前 `_slice_audio` → `_generate_sync` 严格串行。对 1h+ 视频，切段 IO 与推理 CPU 可并行：用一个 `asyncio.Queue` 让切段 producer 先跑 1-2 段，consumer 推理。预估 1h 视频可缩短 10-15% 总耗时（被推理瓶颈限）。
- **VAD 兜底走分段时也启用**：`_load_model()` 仅在「没 ffmpeg」时挂 VAD；建议增加 `ASR_ENABLE_VAD` 强制开关，对噪声音频质量更好。
- **预 detect 静音段跳过**：可选，用 `ffmpeg silencedetect` 在长视频里先标出 > 5s 的静音段直接跳过，进一步省 ASR 算力（v2 再做）。

### 1.3 LLM 调用

- **长字幕分段 → 合并的 prompt 模板已有**（`SUMMARY_MERGE_PROMPT`），但 `_summarize_chunked` 段总结里 `_complete_json_summary` 仍是非流式 + JSON 包装。改造：
  - 段级总结直接输出 markdown（去掉 JSON wrap），减少 1 轮 repair；
  - 段级总结并行（`asyncio.gather` 限并发 = 2-3），避免长视频 5-6 段串行 5-10 分钟；
  - 合并阶段保留流式（已实现）。
- **温度策略**：`resolve_temperature` 已经对 kimi / moonshot 硬编 1。建议改成 `LLM_FORCE_TEMP_ONE_PREFIXES` 环境变量，避免每加一家厂商就动代码。

### 1.4 数据库

- 给 `repo._row_to_job` 加 **lite 版本**：`SELECT id, url, bvid, title, author, duration, status, subtitle_source, created_at, updated_at, completed_at, options_json` —— 列表页 / 抽屉走 lite，详情页才走 `SELECT *`。
- 已开 WAL，但 `repo.add_stage_timing` / `add_token_usage` 走「读 → JSON 解析 → 写」三步，长任务 N 次读写。把 `stage_timings` 改成 **append-only 子表** `job_stage_timings(job_id, stage, started_at, ended_at, duration_ms)`，写就是一行 INSERT，读走 `JOIN` 或独立查询。`token_usage_json` 同理拆出去。
- 给 `jobs(updated_at)`、`jobs(bvid, cid, status)` 加索引，cleanup / dedup 才能走 index seek。

### 1.5 SSE / 实时性

- `EventBus.publish` 当前 `await queue.put(...)`，订阅端断流但队列没被 drain 时会**永久阻塞 publish**，导致 runner 卡住。改成 `queue.put_nowait`，满了就 drop 最老一条（保留 status 类事件，丢 progress 类事件）。
- `routes/jobs.py::stream_job` 已经发 `:keepalive`，但 `EventSourceResponse` 自带 `ping=25`，重复了。统一为单一心跳源。
- 前端 `useJobStream` 已经做了指数退避重连。补一条：重连成功后再 `getJob(jobId)` 拉全量 → 修正状态漂移。

### 1.6 前端渲染

- `Workspace.tsx` 把 `RUNNING_STATUSES` / `buildSteps` / `MetaBar` / `IdleView` / `RunningView` / `DoneView` 全堆在 600+ 行单文件。拆 `features/job/` 子目录后，每次 hot reload 的解析量与单组件 memo 命中率都会明显改善。
- `ReactMarkdown` 渲染长 markdown 每次都重排，应该用 `memo` + key=`job.id+summary.length` 切片。LLM 流式时 200 次 update 触发 200 次解析，建议 **节流到 60fps**（`requestAnimationFrame`）。
- `useJob` 与 `useJobStream` 都各自调 `setJob`，存在 race（流式 patch 后立即 refresh 覆盖）。补一个全局 `jobStore`（zustand 或自写 `useSyncExternalStore`），单一数据源。

---

## 2. 功能模块解耦

当前所有 pipeline 步骤都在 `runner.run_until_transcript` / `run_after_resume` 两个函数里硬编码状态机。建议把状态机抽出来：

```
biri_youyaku/
  jobs/
    state_machine.py   # 纯函数：(status, event) -> (next_status, side_effect_descriptor)
    stages/
      meta_stage.py    # fetch_meta → transition 的具体绑定
      audio_stage.py
      transcribe_stage.py
      summary_stage.py
      email_stage.py
    runner.py          # 只做调度：semaphore + timeout + 状态机驱动
```

收益：
- 测试可以脱离 `asyncio` 跑状态机断言；
- 加新阶段（如「翻译」「字幕清洗」）不再要在 700 行 runner 里改 if 链；
- timeout 配置移到 `settings.stage_timeouts` 字典，每阶段独立可调。

`modules/` 已经分得不错（`bilibili / asr / llm / email / storage`），但有几处倒灌依赖：

- `modules/asr/sensevoice.py` 直接 import `modules/bilibili/subtitle.py::TranscriptItem` —— `TranscriptItem` 应该升级到 `modules/transcript.py`（与 bilibili 解耦的纯领域类型），asr / subtitle / llm 都 import 它。
- `modules/llm/client.py` 在 `_summarize_chunked` 里 import `modules/asr/formatter`，方向反了。把 `transcript_to_text` 移到上面的 `modules/transcript.py` 旁边。
- `jobs/pipeline.py::transcribe_audio` 里 `FasterWhisperTranscriber() if settings.asr_model == "faster-whisper" else SenseVoiceTranscriber()`：策略选择写死。建议引入 `modules/asr/__init__.py::get_transcriber()` 工厂 + 注册表。

前端层面：

- `Workspace.tsx` 拆 `features/job/` 已在 §1.6 提到。
- `lib/url.ts` 升级为 `lib/biliUrl/`：拆 `extract.ts`（从粘贴文本里抠 URL）、`normalize.ts`（去 tracking 参数）、`validate.ts`（多端 host pattern）、`__tests__/`。
- `lib/errorMap.ts` 现状是「错误 → 文案」对照，建议加一层「错误 → 推荐操作回调」，让 UI 不再 hard-code「点这里去 .env」。

---

## 3. 代码运行速度（cold-start / 关键路径）

- **后端 cold start**：`SenseVoiceTranscriber` 第一次 `_load_model` 几秒到几十秒。在 `lifespan` 启动时**异步 warmup**（`asyncio.create_task(_warmup_asr())`）；同时把 `funasr` import 推迟到真正用到时（当前是模块顶级 import，启动直接吃 1-2s）。
- **`pydantic_settings` 在 `Settings()` 初始化时读 .env**：已用 `@lru_cache`。再把它从 `config.py` 顶级 `settings = get_settings()` 改为按需获取，避免在测试里 import 模块就触发文件 IO。
- **`db.init_db` 每次 SCHEMA + 一串 ALTER**：迁移完后写一个 `schema_version` 表，下次直接跳过 ALTER 探测。
- **前端首屏**：`vite.config.ts` 没看到 splitChunks 配置；建议把 `react-markdown` / `lucide-react` 单独分 chunk，首屏 idle 模式下不阻塞 URL 输入框可用。
- **前端 LLM 流式渲染**：`Workspace.renderSummary` 直接 `<ReactMarkdown>{job.summary}</ReactMarkdown>`，每个 chunk 重新解析整段 markdown。改成「上一段稳定块缓存 + 最后一段实时解析」可让 1k 字总结的流式渲染从 ~30ms/帧降到 ~5ms/帧。

---

## 4. 缓存策略

| 缓存层 | 作用域 | 失效策略 |
| --- | --- | --- |
| `bvid → VideoMeta` | 进程内 LRU 256，TTL 1h | LLM 不依赖元信息变动；视频改名 / 改作者罕见 |
| `b23.slug → canonical_url` | 进程内 LRU 1024，TTL 24h | 短链一旦发出基本永久不变 |
| `subtitle_url → TranscriptItem[]` | 进程内 LRU 64（带 size cap）+ 文件落盘 `data/subtitle_cache/{bvid}_{cid}.json` | 文件 TTL 7d；命中后省一次外部请求 |
| `(bvid, cid) → audio_path` | 已经隐式在 `jobs.audio_path` 上；新增**显式 dedup**：新建任务若发现已有相同 `content_hash` 的非过期音频，复用文件不再 yt-dlp | 复用前 `Path.exists()` 校验 |
| ASR 模型实例 | 进程内单例 | 进程生命周期 |
| LLM `AsyncOpenAI` 客户端 | `(api_key, base_url)` 单例 | 同上 |
| `defaults` / `runtime` 配置 | 前端 `localStorage` + ETag | 用户切环境时失效 |
| 历史列表 | 前端 `sessionStorage`（按 `next_cursor` 切片） | 任意 CRUD 后清掉对应切片 |

实现建议：
- 后端缓存统一封装到 `modules/_cache.py` 暴露 `ttl_lru(maxsize, ttl_seconds)` 装饰器；不要在每个模块各写一个。
- 字幕落盘缓存与音频缓存都受 `cleanup_loop` 控制：到达 `subtitle_retention_days` / `audio_retention_days` 自动清。
- LLM 响应**不**缓存：同样字幕用不同 prompt / 模型，结果应可重生成。

---

## 5. 历史文件 / DB 清理

### 5.1 现有 `cleanup_loop` 的缺口

`jobs/cleanup.py` 已经做了「按 `audio_retention_days` 清音频」「按 `job_retention_days` 整体删除任务」，但：

1. **只看终态任务**：`TERMINAL_DELETE_STATUSES` 不含「卡在 TRANSCRIBING 没动几天的僵尸」。建议加 **stale-running 兜底**：`updated_at < now - max(stage_timeout) * 3` 的非终态任务，置 FAILED 并加 `error_code=STAGE_STUCK`。
2. **不清孤儿文件**：`data/audio/`、`data/summaries/` 下的文件如果对应 job 已被外部脚本或 DB 重置删掉，会成为永远不被清理的孤儿。补一个 `scan_orphans()`：扫目录 → 对每个文件查 DB，无对应 job 且 mtime 距今 > retention，直接 unlink。
3. **不清 `tempfile` 残留**：`biri-youyaku-bili-*.cookies.txt`、`biri_asr_*/` 在异常退出（OOM、kill -9）时残留。`lifespan` 启动时 `glob` 一次 `tempfile.gettempdir()` 清掉。
4. **DB 不做 VACUUM**：长期使用后 WAL + 已删除行碎片化，DB 体积膨胀。每周 `PRAGMA wal_checkpoint(TRUNCATE)` + 月度 `VACUUM`。放到 `cleanup_loop` 的 daily / monthly 分支里。
5. **summary 文件单独清不掉**：当前 `audio_only` 分支单独清音频；缺一个对称的「保留音频但清旧 summary」逻辑，对希望长期保留音频做 reprocess 的用户无伤。

### 5.2 新增/调整的清理项

| 配置 | 默认 | 含义 |
| --- | --- | --- |
| `AUDIO_RETENTION_DAYS` | 7 | 已有 |
| `JOB_RETENTION_DAYS` | 180 | 已有 |
| `SUBTITLE_CACHE_RETENTION_DAYS` | 7 | 新增；§4 字幕缓存目录的 TTL |
| `ORPHAN_FILE_RETENTION_DAYS` | 3 | 新增；扫到孤儿文件多久后清 |
| `STALE_RUNNING_FAIL_HOURS` | 4 | 新增；非终态任务超过多久强制置 FAILED |
| `DB_VACUUM_INTERVAL_DAYS` | 30 | 新增；周期性 VACUUM |
| `WAL_CHECKPOINT_INTERVAL_HOURS` | 24 | 新增；周期性 wal_checkpoint(TRUNCATE) |

### 5.3 调度

`cleanup_loop` 当前每小时跑一次 `cleanup_once`。建议改为：

```python
async def cleanup_loop():
    while True:
        await cleanup_files_once()         # 每 1h
        if hourly_tick % 24 == 0:
            await checkpoint_wal()         # 每 24h
        if daily_tick % 30 == 0:
            await vacuum_db()              # 每 30d
        await asyncio.sleep(3600)
```

并把每轮结果（删了多少、回收多少 MB）通过 `logger.info` 打出来，方便 ops 验证。

### 5.4 用户主动清理

前端历史抽屉补**「清理 30 天前任务」**与**「释放音频缓存」**两个按钮（弹 ConfirmDialog），后端复用 `cleanup_once(force=True)` + 接收 `older_than_days` 参数。

---

## 6. 用户每一步流程体验

按用户路径自上而下：

### 6.1 粘贴 URL → 创建任务

- 当前：粘贴时只在 `extracted !== text` 才覆盖输入；URL 上的 `share_source / vd_source` 等追踪参数原样进 DB。
- 改造（已随本次提交落地，见 §8）：
  - `extractBiliUrl` 兼容文本里有多个 URL 时取第一个 B 站域名的。
  - 新增 `normalizeBiliUrl`：去掉 `share_source / share_medium / vd_source / spm_id_from / from_source / from_spmid / bbid / ts / msource / refer_from / unique_k / buvid / mid` 等追踪参数；保留 `p / t / start_progress`。
  - paste handler **始终** normalize，不再依赖 `extracted !== text`。
  - 校验失败时在输入框下方提示「无法识别为 B 站链接」而不是吞掉。
- 后续可做：粘贴成功后立即跑 `/v1/jobs/preview`，在输入框下方显示「《标题》 · UP · 时长」预览卡，再点开始。

### 6.2 等待元信息 / 字幕

- 当前 `MetaBar` 在 `job.bvid` 拿到之前显示「识别中」。建议：
  - 把 `extractBvid(url)` 提前到客户端（已有正则），未拿到后端元信息前先把 BV 号显示出来。
  - `subtitle_source` 在切换瞬间会从 `null` 变 `'platform' | 'asr'`，UI 当前文案是「字幕未定」→「官方字幕」，过渡突兀。加 100ms `crossfade`。

### 6.3 转写进行中

- 当前 `transcribe_progress.preview` 是「最后一段 200 字」，但流式滚动到第三段后用户根本看不出新增哪段。建议显示「最近 1-2 段 + 累计 N 段」。
- 给 SenseVoice 分段进度补「预计剩余时间」：第一段耗时 × 剩余段数。

### 6.4 字幕就绪 → 总结

- `Workspace.tsx` 已经做了 TRANSCRIPT_READY 自动 resume。补一个**可关闭**的 settings：用户希望先看字幕、手动开始时关掉。
- 总结流式时把右下角加「跳到底部」浮标（用户向上滚动阅读不被新内容打断）。

### 6.5 邮件 / 完成

- 完成 toast 4s 自动消失没问题；但 `COMPLETED + email_enabled` 文案是「已发送到邮箱」，对邮件 webhook 失败的 case 不一定准确。建议邮件失败时把 status 留在 COMPLETED 但加 `email_error` 字段；UI 显示「总结完成，邮件未送达 ↻ 重发」。
- 「下载 Markdown」当前用 `Blob + anchor.click()`，文件名 fallback 是 `summary.md`。fallback 改成 `${bvid}-summary.md`，多文件下载更易区分。

> **契约变更（P6-a 已落地）**：邮件阶段的所有异常 —— 包括 webhook 4xx/5xx、超时
> (`StageTimeoutError`)、连接错误 —— **不再**把整个任务置 FAILED。任务状态保持
> COMPLETED，失败原因落到 `email_error`。前端展示黄色横幅 + ↻ 重发按钮。
> 取消（CancelledError）仍然会让任务进入 CANCELED，与旧契约一致。
> 旧 webhook 部署若依赖「邮件失败 → 任务 FAILED → 用户手动 retry」的工作流，
> 需要改为「邮件失败 → 查看 `email_error` 字段 → 点重发」。

### 6.6 历史 / 多任务

- 历史抽屉每次开都全量重拉。补 `If-Modified-Since` 或前端缓存（§4）。
- 删除单条用 `setJobs(current => current.filter(...))` 即时反馈，但删除全部没有反馈到抽屉。统一走 `mutate(jobs)`。
- 已确认任务记录排重在后端 `find_latest_by_video` 上做了；前端首页粘贴时如能联动 dedup 提示，可避免重复跑。

### 6.7 错误 / 兜底

- `friendlyError` 文案已经做。补**一键复制错误详情**按钮（含 jobId / stage / error_code / message），用户反馈成本下降。
- 长任务取消时 `cancel_job` 同步置 `_cancel_requested`，但 `runner` 的下一个 `_raise_if_canceled` 才真正中断。给 UI 加「取消中…」过渡，不要立刻显示已取消。

---

## 7. 实施顺序（建议）

| Phase | 工作量 | 内容 |
| --- | --- | --- |
| **P1 · 一次提交可做的小整治** | 0.5d | 本次：`url.ts` 改造 + `UrlInput` paste 始终 normalize（已合入）；`extractBiliUrl` 测试样例覆盖两种分享格式；后端 `_parse_video_url` 也补 tracking-param 去除作为防御。 |
| **P2 · 缓存与 client 共享** | 1d | `modules/_http.py`、`modules/_cache.py`；`meta / subtitle / b23 / openai` 全部走单例 + LRU；LLM client 复用。 |
| **P3 · 数据库 / 清理收紧** | 1-2d | jobs 表拆 `stage_timings` / `token_usage` 子表；lite row 查询；`cleanup_loop` 加孤儿扫描、stale-running 兜底、WAL checkpoint、VACUUM。 |
| **P4 · 模块解耦** | 2-3d | `jobs/state_machine.py` + `stages/`；`modules/transcript.py` 统一 TranscriptItem；前端 `Workspace.tsx` 拆 `features/job/`、`lib/biliUrl/`。 |
| **P5 · ASR / LLM 性能** | 2d | 切段 / 推理并行；段级总结并行；流式渲染节流；warmup。 |
| **P6 · 体验细节** | 1-2d | preview 卡、preview-after-paste；总结流式跳到底部浮标；错误一键复制；邮件失败状态；取消中 UI；历史增量刷新。 |

每个 phase 单独 PR，CI 跑现有 `pytest`；前端补 `vitest` + RTL 关键路径。

---

## 8. 本次提交的最小改动

随本计划提交：

1. `web/src/lib/url.ts`
   - `extractBiliUrl`：去掉 URL 尾部中英文标点；从含多个 URL 的文本中取第一个 B 站域名 URL；空文本兜底。
   - 新增 `normalizeBiliUrl`：剥离 `share_source / share_medium / vd_source / spm_id_from / from_source / from_spmid / bbid / msource / refer_from / unique_k / buvid / mid / ts` 等追踪参数；保留 `p / t / start_progress`。
   - `isValidBiliUrl`：在判断前先 normalize；增加对 `https://www.bilibili.com/list/...` / `https://www.bilibili.com/festival/...` 容错。

2. `web/src/components/UrlInput.tsx`
   - `handlePaste` **始终** 取 `normalizeBiliUrl(extractBiliUrl(text))` 写回，不再依赖 `extracted !== text`。
   - 「粘贴」按钮亦走相同 normalize。

3. 文档：本文件。

测试样例覆盖（手动验证 + 单测可在 P1 引入 vitest 时落库）：

| 输入 | 期望 |
| --- | --- |
| `【美国车价降了？车市降温—预兆规律现象—买车购车/新车/二手车】 https://www.bilibili.com/video/BV1hcV36EETV/?share_source=copy_web&vd_source=61409c2dae41a631a59035bdb553efba` | `https://www.bilibili.com/video/BV1hcV36EETV/` |
| `【美国车价降了？车市降温—预兆规律现象—买车购车/新车/二手车-哔哩哔哩】 https://b23.tv/euD2txJ` | `https://b23.tv/euD2txJ` |
| `https://www.bilibili.com/video/BV1xx411c7mD/?p=2&t=30&spm_id_from=333.788` | `https://www.bilibili.com/video/BV1xx411c7mD/?p=2&t=30` |
| `BV1xx411c7mD` | `BV1xx411c7mD`（原样，由 `isValidBiliUrl` 通过） |
| `随便聊聊 https://b23.tv/abc 复制本条信息打开「哔哩哔哩」APP` | `https://b23.tv/abc` |

后端 `_parse_video_url`（在 P2 也补一遍 normalize）：作为兜底，前端若漏过，后端再去一次，DB 中 `url` 列从此干净。
