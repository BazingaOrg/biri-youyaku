# 全量代码评审 — 2026-06-14

> 范围：clean code / UI / UX / 样式统一 / 性能 / 文档对齐。覆盖 server、web、部署脚本、文档。
> 优先级：**P0** = 影响功能或有数据风险；**P1** = 体验/可维护性硬伤；**P2** = 抛光。
> 修复方式：本文件只列发现，不动代码。你勾选要做的我再批量改。

> **2026-06-14 进度更新**：6 个批次已全部落地。条目里以 ✅ 标记的是已修复，
> 未标记的多数是 P2 抛光（圆角 / 颜色 token / shadow 进一步收敛、CF Access 方案、
> ReactMarkdown 流式优化、b/p 各项小抛光），保留作为后续随手清单。CHANGELOG.md
> `[Unreleased]` 段有完整改动列表。

---

## TL;DR（如果只看一段）

1. ✅ **数据竞态 / 状态错位**：`useJob` 切换 jobId 时不清空旧数据 + 无 AbortController（P0）；`stream_job` snapshot 与 subscribe 之间存在窗口（P1）。
2. ✅ **`docs/improvement-plan.md` 已严重过期**：顶部加归档标记 + 按完成状态打勾。
3. ✅ **`CONTRIBUTING.md` 引用 `.eslintrc.cjs`**：改成「未配 ESLint，tsc 兜底」。
4. ✅ **`DEPLOY.md` 加 `vercel.json` 说明**：CF Access 方案仍未落地（单独的大改动，留 P2）。
5. ✅ **`tailwind.config.cjs` 死色**：`accent`/`accentSoft`/`pink` + 死 `shadow-surface` 一并删。
6. ✅ **`Workspace.tsx` 916 行 → 370 行**：抽 `useStickToBottom` / `useTerminalToast` / `useAutoResume` + `MetaBar` / `steps` / `IdleView` / `RunningView` / `DoneView`。

---

## 后端（Python / FastAPI）

### P0 — 风险或语义错误

✅ **B-P0-1. `/v1/jobs/{id}/stream` 的 snapshot 与 subscribe 之间有窗口** *（已修，批次 1）*
- 修法：把 `repo.get_job` 移到 `async with event_bus.subscribe(...)` 之后再读 snapshot，
  并抽 `_snapshot_payload` 去重两处 JSON 拼接。

**B-P0-2. `create_job` 的 inflight 检查 + INSERT 不在事务里**
- `routes/jobs.py:122-151`：`count_jobs_excluding_status` → 比对 → `create_job` 是三步分开的，多请求并发时都能通过检查再各自 insert。`MAX_INFLIGHT_JOBS` 实际是「软上限」。
- 在「只有你自己用」场景下不致命，但 README 把它宣称为硬上限。要么改成事务里 SELECT FOR UPDATE 风格的 INSERT…SELECT，要么诚实地把文档说成「近似上限」。

### P1 — clean code / 可维护性

✅ **B-P1-1. `runner.py` 模块级 dict 收成 Registry** *（已修，批次 6）*
- 4 个 dict 合到 `_JobRegistry` 类；`forget(job_id)` 一次性清；`clear_job_state` 改成它的薄包装（routes 外部 API 不变）；`reset_for_tests()` 给测试用。

✅ **B-P1-2. `run_until_transcript` / `run_after_resume` 收尾抽象** *（已修，批次 6）*
- 抽 `_job_lifecycle(job_id, initial_stage)` async context manager，统一处理 CancelledError / Exception / finally；主体只关心业务步骤。`_RunStage` 可变对象在 with 块内传递当前阶段。

✅ **B-P1-3. `repo.py` setter 抽象 + `_row_to_job` 合并** *（已修，批次 6，519 → 444 行）*
- 抽 `_set(job_id, **fields)` 通用 setter；11 个简单 setter 改成 1-3 行。
- `_row_to_job` / `_row_to_job_lite` 合并为同一函数 + `lite=True` 参数；缺列读抽 `_opt_col` / `_opt_json` helper。
- `update_status` 里两次 `now_ms()` 的小瑕疵未改（无功能影响）。

**B-P1-4. `db.py` schema 漂移管理脆弱**（降级到 P2，未改）
- `migrations` 是顺序无关 dict，未来若需要「先加列、再迁数据、再 drop」就走不通。
- 当前 fork / 在跑实例都依赖这套兼容路径，重构风险高于收益。先记着，等真需要破坏性 schema 变更时再做版本化迁移。

**B-P1-5. `_http.openai_client` 缓存淘汰用 `fire-and-forget create_task`**
- `_http.py:84-92` 当 `len > 16` 时 `loop.create_task(old.close())` 但没保存 task 引用，gc 可能在 close 完成前回收。pragmatic 来说 openai SDK 自己也会兜底，但严谨点应该 `await` 或维护一个待关闭集合。

**B-P1-6. `bilibili/audio.py` 的进度回调线程不安全**
- `progress_hook` 在 yt-dlp 工作线程里跑，通过 `loop.call_soon_threadsafe(asyncio.create_task, on_progress(payload))` 安排回调；但 `on_progress(payload)` 在工作线程里**先被调用**返回 coroutine，`create_task` 才在 event loop 里跑。 这种写法 Python 3.11+ 能 work，但每次都会发出 `RuntimeWarning: coroutine ... was never awaited` 如果 loop 已经关闭。更稳：`loop.call_soon_threadsafe(lambda: asyncio.create_task(on_progress(payload)))`。

**B-P1-7. `sensevoice.py` 用 `subprocess.run(..., check=True)` 切片，没有显式 cleanup**
- 在 `tempfile.TemporaryDirectory` 上下文内是 OK 的；但 `_slice_audio` 失败时整个段被 `except Exception: ... continue` 掉，没区分「该段音频破损」vs「ffmpeg 不存在」。后者应直接 abort 整段任务，否则用户拿到一份「丢了 3 段没解释」的字幕。

### P2 — 抛光

**B-P2-1. `events.py:81` `for sub in list(self._subscribers.get(job_id, ()))`**：`set` 已经支持安全迭代（拷贝是为了 finally remove 阻塞），但所有 push 是 `await`，如果某个 sub 满了会阻塞所有 sub。考虑 `asyncio.gather(*pushes, return_exceptions=True)` 并行。

**B-P2-2. `auth.py:require_token` 使用 `==` 比较 token**：可走 `hmac.compare_digest` 防时序攻击。单人场景非致命，但成本极低。

**B-P2-3. `app.py:127` `_unhandled_exception_handler` 注册到 `Exception`**：会吞掉 FastAPI 内部异常的特殊处理（如 RequestValidationError 仍能命中？测一下）。FastAPI 默认 handler 注册顺序：通常更具体的先匹配，但显式注册 `Exception` 是兜底，若用户传入非法 JSON 仍会得到 422，但建议白名单一下 logger 输出避免重复打。

**B-P2-4. `routes/jobs.py:117` `_TERMINAL_JOB_STATUSES` 和 `cleanup.py:15` `TERMINAL_DELETE_STATUSES` 是两个不同概念但名字相似**。前者只 3 个，后者 4 个（含 `TRANSCRIPT_READY`）。当前都还能区分但 jobs.py 引用了 cleanup.py 的常量做 delete，本地又有 `_TERMINAL_JOB_STATUSES`。提到 `model.py` 里统一命名 `RUNNING_STATUSES` / `TERMINAL_STATUSES` / `DELETABLE_STATUSES`。

**B-P2-5. `config.py` 的 `cors_origins` / `llm_allowed_hosts` 是 `@property`**：每次访问都重新 split + strip。微优化但容易爆缓存（结合 lru_cache singleton 已经够，无需改）。

**B-P2-6. `llm/client.py:124` `_build_create_kwargs` 把 `skip_temperature` 写进 thinking dict 再 pop 出来**：用控制流耦合两件事；拆成显式 `thinking_extra, skip_temp = ...` 两返回值更直白。

**B-P2-7. `modules/bilibili/audio.py:42-43` 错误提示嵌入 raw stderr**：在 cookie 未配的场景下，错误消息可能泄露 yt-dlp 的内部链接，对外暴露时考虑过滤。

**B-P2-8. `transcript.py` 仅 17 行（一个 dataclass）**：但被 `bilibili/subtitle.py` 重导出。注释说「升到独立模块」是对的；这文件可以保留，但 `subtitle.py` 那边的 re-export 应该加 `# noqa: F401` 或 explicit `__all__` 提醒别删。

**B-P2-9. `tests/` 缺**：
- 没看到针对 `/v1/jobs/{id}/stream` 的集成测试（SSE）；
- `events.py` 的 summary_sentinel 覆盖语义没测；
- `useJob` race 路径没测（前端无测试栈）。

---

## 前端（React / TypeScript / Tailwind）

### P0 — bug / 数据竞态

✅ **F-P0-1 + F-P0-2. `useJob` 切 jobId 清空旧 state + AbortController** *（已修，批次 1）*
- `useEffect` 切 jobId 时 `setJob(null) / setError(null)`；refresh 用 AbortController 取消上一个挂着的请求；catch 块用 `signal.aborted` 跳过状态写入。
- `getJob(jobId, init?)` 透传 fetch init 参数。

**F-P0-3. `'已开始'` toast 不带 taskName**（未改，最小影响）
- 提交时还没拿到标题，是有逻辑原因的。要做就提交后等 meta 返回再发，或干脆把这条 toast 去掉（导航本身已经是反馈）。

### P1 — clean code / 可维护性

✅ **F-P1-1. `Workspace.tsx` 拆分** *（已修，批次 3，916 → 370 行）*
- `pages/workspace/IdleView.tsx` / `RunningView.tsx` / `DoneView.tsx` / `MetaBar.tsx` / `steps.tsx`；
- `hooks/useStickToBottom.ts` / `useTerminalToast.ts` / `useAutoResume.ts`；
- `lib/jobStatus.ts` 顺手加 `RUNNING_STATUSES` / `TERMINAL_STATUSES` / `isRunning` / `isTerminal`；
- HistoryDrawer 删本地 `RUNNING` set，改用共享 `isRunning`。
- 实际剩 370 行（不到目标 200，但只剩 shell + actions + 路由分支，不再混视图）。

**F-P1-2. `useJobStream.ts` 的状态机有 4 个 ref + 1 个 throttler，可读性差**
- `terminalRef` / `onReconnectedRef` / `attempts` / `isReconnect` / `closed` 散在闭包里。`reconnectKey` 通过依赖数组触发 SSE 重建——能 work，但 effect 体很长。
- 提取 `class JobSseSubscription` 封装连接 + 重连 + throttler，hook 只 mount/unmount 它。

**F-P1-3. `HistoryDrawer.tsx` 半成品 / 可访问性**
- ✅ `const total = response.deleted_count + ...; void total` dead code 已删（批次 4）。
- 未改：`<button>` 嵌 `<span role="button">` 的 a11y 问题；单删无二次确认。要做需要重新设计交互（kebab menu / swipe）。

**F-P1-4. `Workspace.tsx` 各 action 重复模板**
- `cancel/retry/resendCurrentEmail/downloadAudio/copySummary/downloadMarkdown` 每个都是 `setBusy → try { ... toast.success } catch { toast.error } finally { setBusy }`。可以抽一个 `useJobAction(fn, {successTitle, taskName})` hook 收掉。

**F-P1-5. `ToastProvider.tsx:39` push 拿不到稳定 id**
- `Date.now() + Math.random()` 重复概率虽低，但严格不唯一。改 `useRef(0)` 单调递增。

✅ **F-P1-6. `ThemeProvider.tsx` 删** *（已修，批次 4）*

✅ **F-P1-7. `lib/url.ts` shim 删** *（已修，批次 4）* — 两个调用方迁到 `lib/biliUrl`。

✅ **F-P1-8. 三个未用 API 删** *（已修，批次 4）* — `previewJob` / `discoverLlmModels` / `replaceTranscript`；留 comment 说明需要时去后端看签名重加。

**F-P1-9. `useStickToBottom` 直接操作 `window.scrollTo`，与 `Workspace` 强耦合**
- 抽出来后 API 应该是 `useAutoFollow(ref, active)` 而非依赖全局 scroll。当前实现 SSR 兼容判定 (`typeof window !== 'undefined'`) 写了两次，但项目本就没 SSR，纯 noise。

**F-P1-10. `lib/api.ts:request()` 对 401 没处理**
- 401 会落到 `throw new Error(message)` 走通用 toast，看不出「token 错了」。补一个 `if (response.status === 401)` 友好提示「鉴权失败：检查 VITE_API_TOKEN」。

### P2 — UI / 样式 / 可访问性

✅ **F-P2-1. Tailwind 死色 / 死 shadow** *（已修，批次 4）* — `accent` / `accentSoft` / `pink` + `shadow-surface` 一并删。

**F-P2-2. 颜色 token 散乱使用**
- `text-muted/55` / `bg-panel/85` / `bg-panel/40` / `bg-canvas/...` 这类 opacity 后缀在不同文件不同密度。建议：
  - 一套语义化叫法（`bg-overlay-strong / bg-overlay-soft`）；
  - 透明度只允许 0/40/60/80 几档，避免 55/70/85 这种「拍脑袋」。

**F-P2-3. 圆角不统一**（部分修，仍可继续收敛）
- ✅ `rounded-lg`（错误卡的两个小按钮）已统一到 `rounded-xl`。
- 未改：完整 4 档化（`xl/2xl/3xl` + tooltip 用 `md`）需要设计决策，留 P2。

✅ **F-P2-4. shadow token 死名删** *（已修，批次 4）* — `shadow-surface` 零引用删；保留 `card` / `cardHover` 两个配对名。

**F-P2-5. `StepCarousel` 卡片高度写死 `h-[220px]`**
- 第 79 行。短内容大段留白，长内容溢出滚条。建议 `min-h-[180px]` + `max-h-[40vh]`。

**F-P2-6. `MetaBar` 与 step `renderMeta` 信息重复**
- 第 0 步「识别视频」里又显示一次标题 / UP / 时长，跟顶部 `MetaBar` 重了。建议：第 0 步要么换成显示「BV / cid / 视频源链接」这类元数据，要么干脆隐藏第 0 步等 meta 就绪。

**F-P2-7. `IdleView` 错误消息位置反直觉**
- `UrlInput` 的 `error` 显示在 `actions` 之下（按钮之下），用户视线习惯先看按钮、再看错误。把 error 放回 input 之下、actions 之上。

**F-P2-8. `IconButton` 的 tooltip 在 mobile 不显示**
- `group-hover` 触发，移动端无 hover。`title` attribute 在 iOS Safari 也不显示。如果要在 mobile 上有提示，得用 long-press 或 visible label。当前的 label 也通过 `aria-label` 给 a11y 工具，但 sighted mobile 用户不知道「Plus 图标 = 新建」。建议至少在主页面入口按钮（Idle 的两个 lg 按钮）下方显示文字标签。

**F-P2-9. `HistoryDrawer` 关闭抽屉的层级**
- 整个 overlay `onClick={onClose}`，aside 上有 `e.stopPropagation()`。OK。但 ESC 键监听写在 `useEffect`（line 70-77）依赖 `[open, onClose]`，每次 `open` toggle 都装拆一次。微优化可改成在 aside 上 `onKeyDown`。

**F-P2-10. 暗色模式细节**
- `--color-fg` 对 `--color-bg` 在浅色对比度 12.9:1 OK；暗色 `#ede7db on #15131a` ~14:1 也 OK；
- 但 `text-muted/55` 这种 lighter-muted 在暗色下接近 #9b95a4 × 0.55 ≈ 不可读（对比度 ~3:1，AA 不达标）。`.placeholder:text-muted/55` 等地方建议改成 `placeholder:text-muted`。

**F-P2-11. `prose-sm` 与 `prose` 混用**
- `RunningView` summary 用 `prose-sm`、`DoneView` 用 `prose`，两个视图字号不一致。统一一档。

**F-P2-12. 全局 body 背景图**
- `styles.css:62-71` 三层 background-image 叠加在 `background-attachment: fixed` 上。在低端机 / iOS Safari 滚动卡。fixed attachment 在 Safari 上是出名的性能黑洞。建议只在桌面（`@media (min-width: 768px)`）启用 fixed，移动端 disable 或换更轻量的纹理。

### P2 — 性能

**F-P2-13. `ReactMarkdown` 每次 chunk 都全量重渲染**
- 流式总结时哪怕节流到 60fps，每帧仍然是 ReactMarkdown 拿完整字符串 re-parse。长视频累计到 5k+ tokens 后 GC pressure 明显。考虑：
  - 用 `react-markdown` v9（你现在是 v8）+ `remark-gfm` lazy；
  - 或者只在流式期间渲染 `<pre>{summary}</pre>`，COMPLETED 之后再 swap 成 ReactMarkdown。

**F-P2-14. `tailwind.config.cjs` 没开 `purge` content glob 之外的范围**
- 现在 `content: ['./index.html', './src/**/*.{ts,tsx}']` 没问题。但项目用了 dynamic class string（`text-${type}`?）—— grep 一下确认无变量类名。

---

## 文档

### P0 — 严重过期或误导

✅ **D-P0-1. `docs/improvement-plan.md` 归档** *（已修，批次 2）* — 顶部加归档标记，列出完成 / 过期 / 未做项，C 章节标「方案已偏离」。

✅ **D-P0-2. DEPLOY 加 `vercel.json` 说明 + Root Directory 提示** *（已修，批次 2）* — VITE_API_TOKEN 弱口令段落保留（仍是当前推荐姿势），CF Access 完整方案未落地（需要后端 `auth.py` 改造，单独的大改动留 P2）。

### P1 — 内容漂移 *（全部已修，批次 2 / 5）*

✅ **D-P1-1.** CONTRIBUTING.md 改成「未配 ESLint，tsc 兜底」；CI workflow 注释精简。
✅ **D-P1-2.** DEPLOY.md 中英文都加 `vercel.json` + Root Directory 段落。
✅ **D-P1-3.** AGENTS.md `pipeline.summarize_transcript` → `summarize`。
✅ **D-P1-4.** README 中英文 dev.sh 说明改成「自动 cp server/.env + web/.env + deps」。
✅ **D-P1-5.** CONFIG.md 中英文都拆 BILI cookie 三行、邮件三行，注明 `MAX_CONCURRENT_*` 对应哪个 semaphore。
✅ **D-P1-6.** CHANGELOG `[Unreleased]` 补 8+ 条最近改动（含本次评审 6 批次的全部产出）。

### P2 — 抛光

**D-P2-1. README + README.en 几乎完全镜像**
- 内容同步靠人工，长期会漂。考虑只留中文版 README，英文版用 `<details>` 折叠或独立短一些。

**D-P2-2. `examples/email-worker/README.md` 部署步骤里 `wrangler login` 后没说要选哪个 account，多 account 用户会卡**。

**D-P2-3. `SECURITY.md:23` 说 VITE_API_TOKEN「公网部署请叠 Vercel Protection / Cloudflare Access」**
- 跟 DEPLOY.md 说法一致但 plan 里说要换 CF Access 方案。三处一起更新或都不动。

---

## 部署 / 构建

### P0

**X-P0-1. Vercel build 命令不会自动认到 `vercel.json`**
- `vercel.json` 放在 `web/` 下而 Vercel 项目的 Root Directory 也设的是 `web/`，路径正确。但保险起见在 DEPLOY.md 里说明：「Root Directory 设 web/ 时，`vercel.json` 必须也放 web/」，避免有人改 Root Directory 后 SPA fallback 静默失效。

### P1

✅ **X-P1-1. nginx gzip** *（已修，批次 5）* — 仅压缩 text/css/js/json/svg；`worker_processes` 等参数留默认（单用户低流量足够）。

✅ **X-P1-2. `docker-compose.yml` `VITE_API_BASE_URL` 环境变量化** *（已修，批次 5）* — `${VITE_API_BASE_URL:-http://localhost:17821}`，注释写清「浏览器侧 URL，跨机部署必须显式覆盖」。

✅ **X-P1-3. `docker-compose.dev.yml` 挂载 `:cached`** *（已修，批次 5）* — macOS Docker Desktop 性能优化，Linux 忽略。完整切到只挂 src/ 需要拆每个配置文件，收益有限，没做。

✅ **X-P1-4. `server/Dockerfile` ASR extras 说明** *（已修，批次 5）* — 顶部注释说明默认不预装、需要时改 `--extra asr`。`ARG WITH_ASR` 没引入（增加用户决策成本，留默认更清爽）。

✅ **X-P1-5. CI ESLint 决策** *（已决定，批次 5）* — 决定不补 ESLint，CONTRIBUTING + CI workflow 已统一说明「tsc 兜底」。

**X-P1-6. pre-commit 前端 hook**（未做，P2）— 引入 prettier / dprint 是个偏好问题，与现有 tsc-only 策略一致，留默认。

### P2

**X-P2-1. Dockerfile 用 `python:3.11-slim`**：CI 也 `uv python install 3.11`。`AGENTS.md` 写 `Python 3.11+`。一致。
**X-P2-2. `scripts/dev.sh` `trap cleanup EXIT INT TERM`**：cleanup 后 `wait` 在 EXIT 阶段触发时已无后台任务，无害但冗余。
**X-P2-3. `pre-commit-config.yaml` 用 `gitleaks v8.18.4`**：建议升 v8.21+ 修了几个 false-positive。

---

## 测试覆盖（顺手）

- `server/tests/` 12 个文件，覆盖 ASR / bilibili / cleanup / config / email / job options / job repo / llm / runner / segmenter。
- 缺：
  - SSE 集成测试（`routes/jobs.py:stream_job` 的 race window）；
  - `events.py` summary_sentinel 覆盖语义；
  - 前端无测试栈。是否补取决于团队规模——单人维护可以不补。

---

## 建议落地顺序

| 批次 | 内容 | 状态 |
| --- | --- | --- |
| **1. 防回归** | F-P0-1 / F-P0-2（useJob race）、B-P0-1（stream snapshot race） | ✅ |
| **2. 文档对齐** | D-P0-1 / D-P0-2 / D-P1-1～6 一次清 | ✅ |
| **3. 拆 Workspace.tsx** | F-P1-1 拆 4 个视图 + 3 个 hook | ✅ |
| **4. 死代码 / 样式统一** | F-P1-3 / F-P1-7 / F-P1-8 / F-P2-1 / F-P2-4 / F-P1-6 | ✅ |
| **5. 部署收尾** | X-P1-1 / X-P1-2 / X-P1-3 / X-P1-4 / X-P1-5 | ✅ |
| **6. clean code 抽象** | B-P1-1 / B-P1-2 / B-P1-3（B-P1-4 降级到 P2） | ✅ |
| **后续抛光（P2 / 未做）** | CF Access 方案、Workspace `已开始` toast、HistoryDrawer a11y、圆角完整收敛、`prose-sm/prose` 统一、暗色模式人工切换 / 快捷键、ReactMarkdown 流式优化、`db.py` schema 版本化、`bilibili/audio.py` progress hook 线程安全细节、`auth.py` `hmac.compare_digest` 等 | — |
