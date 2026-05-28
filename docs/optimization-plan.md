# Biri-Youyaku 优化方案

> 文档目的：在不重构整个项目的前提下，分阶段把 UI 重新设计得平衡、把交互理顺、把后端链路稳定下来，并让 Windows / Mac / iPhone 三端都能舒服地使用。

---

## 0. 现状速写

当前产品是一个三页的 SPA：HomePage（粘贴 URL）→ JobPage（看进度、确认字幕、生成总结）→ HistoryPage（查看历史）。后端是 FastAPI + SQLite，把整个流水线拆为「拉取元信息 → 取字幕或下音频转写 → 等待确认 → 总结 → 发邮件」7 个状态，通过 SSE 把状态推给前端。

实测下来，最影响体感的几类问题：

第一类是**视觉不平衡**：粉色（#fb7299）几乎贴满了所有 CTA、阴影、外发光、脉冲动画，没有视觉优先级。HomePage 上输入框带 `glowPulse` 持续呼吸光晕，按钮带类似 Bilibili 实体投影（`shadow-[0_10px_0_#d94f78,...]`），但 JobPage 又改成圆形扁平按钮，两种风格混在一起。AppShell 只是一个空容器，没有顶栏、没有品牌区，整页只看到一个孤立的输入框，桌面端大屏上很空。

第二类是**流程断点**：
- 用户在 TRANSCRIPT_READY 时需要主动点「开始总结」，但这一步只在卡片右上角放了个粉色按钮，没有强提示；
- 「高级选项」在页面最下方、字幕之后，要改模型或语言必须滚到底；
- 一旦总结进入 SUMMARIZING，UI 没有任何 token 流，只有一个 spinner 等几十秒到几分钟；
- HomePage → JobPage 切换没有过渡、没有 toast，只是 URL 一变；
- JobPage 上的「返回」直接去 History，不是返回上一个页面，违反直觉；
- 历史页只有「点击打开 / 删除」两个操作，没有搜索、筛选、分组。

第三类是**链路与跨端**：
- `recover_unfinished_jobs()` 启动时把所有未完成任务并发恢复，没有并发上限；
- yt-dlp、SenseVoice 模型每次重新加载，没有缓存；LLM 调用不流式；
- SQLite 每次操作 open/close，没开 WAL，SSE 长连接和写操作会互相阻塞；
- `AUDIO_RETENTION_DAYS` / `JOB_RETENTION_DAYS` 配了但没有清理逻辑；
- SSE 断流后前端不重连；
- 没有 PWA manifest，iPhone 无法 add to Home，Safari 体验只是个网页；
- `VITE_API_TOKEN` 直接打进前端 bundle，README 自己也承认不算秘密。

下面的方案围绕这三类问题来组织。

---

## 1. 设计原则

在动任何代码之前，先确立 5 条原则，让所有具体改动都能回到这几条上判断：

1. **一屏交付主任务**。粘贴链接、看到进度、看到总结、复制 / 下载 / 重发邮件，桌面端不需要滚动、移动端最多滚一屏。
2. **视觉优先级唯一**。同一屏只允许一个粉色实心 CTA，其它降为次级（描边、浅色背景）或图标按钮。
3. **状态自解释**。每个任务状态都附带「下一步该做什么」的引导文案和按钮，不让用户猜。
4. **跨端复用，不为单端做妥协**。所有页面默认响应式，桌面端走 12 列网格、移动端走单列；只在键盘快捷键、PWA、Share Extension 这类「能力差异」上做端内增强。
5. **降级优于失败**。SSE 断了走轮询；ASR 失败提示走字幕重试；邮件失败不阻断总结完成；总结失败保留字幕等用户重试。

---

## 2. 信息架构与导航重设计

当前没有持久导航，三页之间靠各自页面顶部的「返回」按钮跳。建议引入**单一顶栏 + URL-based 路由**：

**顶栏（AppShell 升级）**：左边是品牌（`biri-youyaku` 文字 logo + 一个 favicon），中间是当前页面 breadcrumb（首页 / 任务 / 历史 / 设置），右边是三个图标按钮（历史、设置、主题切换）。移动端塌缩为：左侧汉堡或返回箭头、中间标题、右侧单个图标。

**路由**：把当前手写的 `window.location.pathname` 判断换成 `react-router` 或更轻的 `wouter`，并补一个 `/settings` 页面。这样浏览器返回 / 转发可用，桌面端 cmd+[ / cmd+] 直接生效。

**页面集合**：
- `/`：首页（粘贴 URL + 最近任务），首页本身就显示 5 条最近历史的横向卡片，避免一打开就是空屏。
- `/jobs/:id`：任务详情，单页装下「视频信息 + 进度 + 字幕 + 总结 + 操作」。
- `/history`：历史列表（带筛选、搜索、分组）。

故意不做独立的 `/settings` 页面：LLM Key、邮件 webhook、Bilibili Cookie 这类系统配置仍在后端 `.env` 维护（这是 self-hosted 工具的合理选择，避免把秘密散落在多端浏览器里）；外观主题（亮 / 暗 / 跟随系统）只需要顶栏一个图标按钮 + `localStorage`；任务级偏好（模型、是否邮件、是否强制 ASR）已经在首页和任务页的「更多选项」里。这样就**不引入设置页**，省一个页面、省一套表单。

路由用 `wouter`（gzip 仅约 1KB，hooks 化的 API 和当前代码风格一致）。JobPage 的「返回」按钮去掉，统一靠浏览器后退或顶栏 breadcrumb。

---

## 3. UI 重设计

### 3.1 设计语言收敛

整体走「中性灰白底 + 小面积品牌色」。Bilibili 粉退场，只在需要主 CTA、强调态、当前进度高亮、品牌 logo 这些极少数地方点缀。

**品牌色：靛蓝 `#5B6DF0`**。挑这个色的理由有四：(1) 名字里 `biri` 是电流拟声词，靛蓝 / 紫的波段视觉上和「电」对得上；(2) 日本 `藍染` 的色彩血统，和 `youyaku` 的日式气质同源；(3) 和 Bilibili 粉差异够大，项目有自己的身份感；(4) 在 Linear / Notion / Vercel 这类生产力工具里是熟悉的家族，但又通过 logo 和排版做出自己的味道。在亮模式用 `#5B6DF0`，暗模式用 `#9099FF` 保证对比度过 AA。

把 `tailwind.config.cjs` 改成下面这套语义层（同时声明亮 / 暗两套）：

| 语义 token | 亮模式 | 暗模式 | 用途 |
| --- | --- | --- | --- |
| `bg` | `#fafafa` | `#0e0f12` | 页面底色 |
| `bg-elevated` | `#ffffff` | `#17181c` | 卡片、面板背景 |
| `bg-sunken` | `#f3f4f7` | `#0a0b0d` | 字幕预览、空状态等下沉区 |
| `fg` | `#18191c` | `#e8e9ee` | 主文本 |
| `fg-muted` | `#6d757a` | `#9099a3` | 辅助文本 |
| `border` | `#ececf0` | `#26272d` | 描边、分隔线（绝不再用粉色） |
| `brand` | `#5B6DF0` | `#9099FF` | 主 CTA、进度高亮、品牌色 |
| `brand-soft` | `#eef0ff` | `#1b1d3a` | 选中态、tag、active 行 |
| `success` | `#16a34a` | `#4ade80` | 完成 |
| `warning` | `#d97706` | `#fbbf24` | 等待确认（如 TRANSCRIPT_READY） |
| `danger` | `#dc2626` | `#f87171` | 失败、destructive 操作 |

主题切换实现：在 `<html>` 上挂 `data-theme="light|dark|system"`，CSS 用 `[data-theme="dark"]` 覆盖变量；`system` 模式跟 `prefers-color-scheme`。切换按钮放顶栏右侧，状态持久化到 `localStorage`，不上传后端。

把 `pinkGlow`、`pinkGlowStrong`、`glowPulse`、`shadow-bili`、`shadow-biliHover` **全部删掉**——输入框的常亮发光是当前最大的视觉噪声。卡片阴影统一为 1 套：`shadow-card` = `0 1px 2px rgba(0,0,0,.04), 0 8px 24px rgba(0,0,0,.06)`；`shadow-cardHover` 在此基础上 y+2。暗模式的阴影改用更弱的 `rgba(0,0,0,.4)` 加 1px 内描边来制造分层。

按钮分四档：**Primary**（实心 brand）、**Secondary**（描边 + 透明背景）、**Ghost**（仅图标 / 文字，hover 时显示底色）、**Danger**（实心 danger，仅用于删除 / 清空）。同一屏只允许 1 个 Primary。

字体保留 Avenir Next + 系统栈即可；行高从默认 1.5 调到 1.6，长段落更舒服。

### 3.2 HomePage 重做

目标：让首页同时承担「快速创建」和「最近任务概览」两件事，不再是只放一个孤立输入框。

布局自上而下（桌面单列居中，最大宽度 720px）：

1. **顶部 hero**：一行标题（`粘贴 B 站链接，要約一下`）+ 一行说明文字。去掉所有阴影按钮和发光，只留一个圆角中等大小的输入框。
2. **粘贴区**：输入框右侧内嵌一个「粘贴」icon button（调用 `navigator.clipboard.readText()`，iPhone Safari 上会弹权限请求）和一个清除按钮。回车 / Cmd+Enter 直接提交。校验失败时下方红字提示，不弹 toast。
3. **行动行**：1 个 Primary「开始」 + 1 个 Secondary「仅下载音频」（把当前只有后端能用的 `task_type=audio` 暴露出来）+ 折叠按钮「更多选项」（展开后只有 LLM 模型、是否邮件、是否强制 ASR 这三项快捷开关；其它系统级配置仍在后端 `.env` 维护）。
4. **最近任务**：横滚的 3-6 张卡片，每张显示封面占位、标题、状态徽章。空状态显示一段说明文字。

输入框删掉 `motion-safe:animate-glowPulse`、`shadow-pinkGlow*`，改为细灰描边 + 聚焦时切到 brand 描边（无外发光）。

### 3.3 JobPage 重做

当前最严重的问题是「关键操作（开始总结、选项）和正在看的内容（字幕）相隔很远」。改成两列 sticky 布局：

**桌面端（≥ lg）**：
```
+--------------------------------------------------------+
| 顶栏（标题 + BV + 作者 + 时长 + 视频源链接）             |
+--------------------------------------------------------+
| 左列（sticky, 360px）                | 右列（剩余宽度）  |
|  - 状态卡（进度条 / 时间线）          | - 总结面板        |
|  - 主操作（开始总结 / 取消 / 重发邮件）|  (Markdown 渲染) |
|  - 选项摘要（model / 邮件 / 语言）    |                  |
|  - 资源（下载音频 / 字幕 / Markdown）  |                  |
|                                       | - 字幕面板        |
|                                       |  (折叠/展开)      |
+--------------------------------------------------------+
```

**移动端（< md）**：单列，按「视频信息 → 状态 / 主操作（吸顶悬浮）→ 总结 → 字幕折叠 → 选项弹屉」排布。主操作做成 sticky bottom bar（参考 iOS Mail 的回信工具栏），保证手不离屏幕就能点。

具体调整点：
- **进度时间线**：当前 7 个步骤全部列出，但 EMAILING 在 `email_enabled=false` 时永远不点亮，会让用户怀疑出问题。改为动态步骤数：`[元信息, 字幕/转写, （可选）等待确认, 总结, （可选）邮件, 完成]`。每步右侧附带「耗时」展示，完成态显示 `12s`。
- **TRANSCRIPT_READY 引导**：把这一步变成一张「待你确认」卡片，里面是字幕预览（前 200 字 + 「展开全部」），下方两个并列按钮：`开始总结`（Primary）+ `重新走 ASR`（Secondary，触发 force_asr 重跑）。让用户清楚知道在等他做选择。
- **总结面板**：支持 LLM 流式输出（见 §5.3），打字机式渲染；完成后头部加「字数、模型、耗时、Token 用量」四个 stat。复制 / 下载按钮从孤立的 icon 改成「复制 Markdown / 下载 .md / 发送邮件」三个文字按钮。
- **字幕面板**：默认折叠，只显示「来源 + 行数 + 总时长」摘要；点开后显示带时间戳的列表（不再是 `<pre>`），每行可点击 → 复制 / 跳转到对应播放点（如果做了内嵌播放器，可联动；否则跳到 B 站 `?t=` 链接）。
- **操作集合**：「更多」菜单只放真正低频操作（重新拉取元信息、删除任务、复制任务 ID）。常用的「下载音频」「下载字幕」「下载总结」收到左列的「资源」分组，跟下载按钮放一起就行。

### 3.4 HistoryPage 重做

当前列表只有标题 + 删除。增强为：

- **顶部条**：搜索框（按标题 / 作者 / BV 号过滤）+ 状态筛选 chip（全部 / 进行中 / 待确认 / 已完成 / 失败）+ 排序（最新 / 时长）。
- **分组**：按日期分组（今天 / 昨天 / 本周 / 更早），每组下面才是任务卡。
- **批量操作**：长按或勾选进入多选模式，可批量删除 / 重发邮件。
- **分页 / 懒加载**：当前只 `limit=50`，改成无限滚动 + 后端 cursor。
- **「清除全部」按钮**：从粉色 Primary 改为 Ghost + 红字，避免和右上角主 CTA 抢视觉。
- **空状态**：插画 + 一句话引导「去首页粘贴一个链接试试」+ 跳转按钮。

### 3.5 ConfirmDialog / Toast 微调

ConfirmDialog 的「警告图标」当前是粉色 AlertTriangle，删除场景应该是红色或琥珀色。给 ConfirmDialog 加 `tone: 'default' | 'danger'`，destructive 操作切到红。

ToastProvider 当前的 `autoClose` 默认 false，意味着大多数 toast 永远不消失，需要用户手动点叉。这是一个隐性 bug。**改为默认 autoClose=true（4s），error 类型默认不自动关闭**（错误信息要让用户能看清）。

---

## 4. 交互流程重设计

### 4.1 创建任务

老流程：粘贴 → 点按钮 → 静默跳转。新流程：

1. **粘贴**：失焦 / 回车都触发校验。校验通过后，输入框右侧出现一个 chip 显示已识别的 BV 号。
2. **预检**：URL 通过后，立即在客户端发一个 `POST /v1/jobs/preview`（新接口）只拉元信息，不创建任务。在原地展示视频封面 / 标题 / 时长，让用户「确认是不是这个」再点开始。
3. **创建 + 跳转**：点开始后，立刻乐观跳转 `/jobs/:id`，同时弹一个非阻塞 toast「任务已创建」。
4. **后退兜底**：跳转使用 `pushState`，用户点浏览器返回回到首页时输入框内容保留。

预检步骤把「我点错链接」「URL 解析失败」之类的问题前置，避免用户先创建了任务再去删。

### 4.2 等待确认（TRANSCRIPT_READY）

这是产品的核心交互节点。改造点：

- 默认行为可配置：在 `/settings` 加一个开关「字幕就绪后自动开始总结」，老手可一键打开，跳过确认步骤；新手默认关闭以保留可控性。
- 没开自动时，UI 必须显眼地提示「等你确认」：让进度卡变橘 / 黄色调，且右上角主 CTA 文案从 `开始总结` 改为 `确认并总结`，并附带 secondary `重新转写`。

### 4.3 总结进行中

老流程：纯等待。新流程：

- 后端用 `stream=True` 调 LLM，按 token 推 `summary_chunk`。前端收到就 append 到当前 `summary` 后面，做打字机渲染。
- 同时把估算耗时展示出来：`已用 12s · 预计还需 30s`（基于字幕字数 × 模型平均速率简单线性估计即可）。
- 完成后 toast 自动消失，summary 面板上方滚动到视野中。

### 4.4 错误处理

当前所有失败都直接弹 error toast，文案是后端原始 message，对非技术用户不友好。建议加一个「错误码 → 中文文案 + 推荐操作」映射层：

| 场景 | 文案 | 操作 |
| --- | --- | --- |
| `LLM_API_KEY 未配置` | 还没有配置大模型 Key | 「查看后端 .env 配置」（折叠面板内嵌说明） |
| `B 站元信息接口返回失败` | 拿不到视频信息，可能是地区限制或需要登录 | 同上，提示填 `BILI_SESSDATA` |
| `yt-dlp ... No video formats found` | 下载音频失败，多半是 Cookie 失效 | 同上 |
| LLM HTTP 4xx / 5xx | 大模型接口异常 | 「换模型重试」（任务页内的选项面板） |

错误 toast 里点「查看后端配置」展开一个抽屉，里面用 `<code>` 列出当前缺失的 env 变量名 + 一句话说明（不暴露具体值），引导你去 `.env` 改完重启。

后端补一个 `error_code` 字段，前端按 code 渲染。

### 4.5 历史与多任务

- 同一 BV+CID 已经有总结时，创建新任务前提示「已有总结，要复用还是重新生成？」。复用直接跳到老的 jobId。
- **多版本相邻折叠**：同一 BV+CID 的多次任务在历史列表里显示为「一张主卡 + 折叠条」结构。主卡显示最新一次的状态与总结预览，下方一条 chevron「+2 个早期版本」点开展开早期记录。删除主卡时弹确认询问「只删这次还是删全部版本」。
- 历史页的「拖动重排 / 收藏」对个人长期使用很有用，但属于 v2。

---

## 5. 后端 / 链路优化

### 5.1 任务调度

`runner.py` 当前的并发模型是「不限并发的 asyncio.create_task」。问题：

- 启动时 recover 大量未完成任务会把 LLM / yt-dlp 全打满。
- 单个任务异常 stuck（比如 SenseVoice 死锁）没有超时。

改造：

- 引入**全局任务并发上限**（如 `MAX_CONCURRENT_JOBS=2`），用一个 `asyncio.Semaphore` 守护「下载 + 转写」这段重 IO/CPU。`summarize` 这段相对轻，单独再放一个 `Semaphore`。
- 每个阶段加 **wall-clock timeout**：fetch_meta 30s、download_audio 10min、transcribe 30min、summarize 5min。超时统一抛 `StageTimeoutError`，状态置 FAILED，error_code 标 `STAGE_TIMEOUT`。
- 启动恢复改成**串行恢复**（一次只重启一个，且只重启 PENDING / FETCHING_META / DOWNLOADING_AUDIO 这种「能从头跑」的状态；TRANSCRIBING、SUMMARIZING 这种中间态先置为 FAILED 等用户决定，避免重复消费资源）。

### 5.2 SSE 与状态同步

- SSE 当前只推「现在的状态」，断线 / 后接入的客户端拿不到历史事件。建议在 `subscribe` 时**先重放当前 Job snapshot**（已经做了一半），再推后续。
- 前端 `useJobStream` 加自动重连：断开后 1s / 2s / 5s 退避重连，重连成功后立刻 refresh 一次 `getJob` 拿全量。
- 终态（COMPLETED / FAILED / CANCELED）后服务端主动 close 流，前端不再重连。
- 增加 SSE 心跳（每 25s 发 `:keepalive`），防止 Cloudflare Tunnel / iOS Safari 90s 空闲断开。

### 5.3 LLM 流式与长视频

`modules/llm/client.py` 当前用 `client.chat.completions.create` 同步等待整段响应。改造：

- 改成 `stream=True`，按 delta 累计 markdown，每收到一段就 `event_bus.publish("summary_chunk", {"text": accumulated})`。
- JSON 解析改成「最终事件再 parse」，流式过程中不要尝试 parse（中间不是合法 JSON）。可考虑把 prompt 改成直接输出 Markdown，不再包一层 JSON 字段——可以减少模型 token、避免 JSON repair 的额外一轮调用。
- 字幕超长（> 30k tokens 估算）时做 chunk：用 `SUMMARY_PROMPT` 分段总结 → 用 `SUMMARY_MERGE_PROMPT` 合并。当前 `SUMMARY_MERGE_PROMPT` 已经有，但 pipeline 没用，把它接起来。
- 把 LLM 用量（input_tokens / output_tokens / cost_estimate）落库到 jobs 表，方便后续展示和限额。

### 5.4 数据库

- `connect()` 每次新建连接太重，且没启用 WAL。改为模块级 `Connection` 池 + `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`，SSE 长读不会阻塞写。
- jobs 表增加列：`error_code TEXT`、`stream_finished_at INTEGER`、`token_usage_json TEXT`、`content_hash TEXT`（基于 bvid+cid 做 dedup）。
- 把 `chapters_json`、`transcript_json` 体积大的字段单独抽出来到 `job_artifacts` 表，主表查询更轻。
- 实现 `AUDIO_RETENTION_DAYS` / `JOB_RETENTION_DAYS` 的清理任务：lifespan 内启一个 `asyncio.create_task(cleanup_loop())`，每 1h 跑一次。

### 5.5 字幕、音频与 ASR

- B 站元信息和字幕请求加重试（exponential backoff 3 次），并把 timeout 从 30s 调到 15s（更快失败更好）。
- 下音频用 yt-dlp Python API 直接调（而不是 subprocess + sys.executable -m yt_dlp），减少进程创建开销，方便捕获进度回调。把下载进度（已下/总大小）通过 SSE 推送，让 UI 显示百分比。
- SenseVoice 模型当前每次 `model = AutoModel(...)` 重新加载，几秒到十几秒的开销。改成模块级单例 + lazy load，第一次后驻留内存。配合 `ASR_DEVICE=auto`，根据机器有没有 GPU 自动选。
- 增加 faster-whisper 作为可选 ASR backend（很多人在 mac/win 上用 whisper.cpp 更香），通过 `ASR_MODEL` 切换。

### 5.6 安全与配置

- 把 `VITE_API_TOKEN` 这条路废掉。改用「前端首次访问时弹一个授权框，让用户输 token，存 localStorage」。这样部署到 Vercel 也不会把 token 打进 bundle。生产部署文档同步更新。
- API 接口加请求 ID（`X-Request-ID`），日志里打出来，方便用户截图反馈错误时定位。
- 增加 `/v1/config/runtime` 接口返回「LLM 是否配置 / 邮件是否配置 / Bilibili Cookie 是否配置」三个布尔，首页可以根据这个直接显示「未配置 Key，先去设置」引导，而不是等用户跑到一半看到红字。

---

## 6. 跨端体验

不做 PWA，也不做 iOS Shortcut（已确认）。所有跨端体验通过响应式 + 键盘快捷键 + Safari 兼容打磨实现，浏览器打开 URL 就是全部入口。

### 6.1 Windows / Mac 桌面浏览器

桌面优先做键盘流畅度和窗口宽度的 affordance：

- **键盘快捷键**：
  - `Cmd/Ctrl + V`（在首页焦点处自动）：从剪贴板粘贴 URL 并触发预检。
  - `Cmd/Ctrl + Enter`：提交 / 确认。
  - `Cmd/Ctrl + .`：取消当前任务。
  - `Cmd/Ctrl + K`：聚焦到搜索框（首页 / 历史页都生效）。
  - `?`：呼出快捷键速查浮层。
- **拖拽**：支持把 `.txt` / `.srt` / `.vtt` 字幕文件拖到 JobPage 字幕区，直接覆盖现字幕跳过 ASR，再点「重新总结」走 LLM。这条对长视频特别有用 —— 你可能希望先手动校对字幕再让 LLM 总结。
- **窗口宽度**：当前 `max-w-5xl` (~1024px) 在 27" 屏上显得局促；JobPage 改用 `max-w-7xl`，让左列状态卡和右列总结都有舒服宽度。
- **主题切换**：顶栏右上图标按钮，三档循环：跟随系统 → 亮 → 暗。状态写 `localStorage`。

### 6.2 iPhone Safari

不做 Shortcut，但作为日常打开 Safari 输 URL 的方式，需要把以下几条做对：

- **触感与尺寸**：所有按钮、列表项最小高度 ≥ 44px（当前 `min-h-10/11` 不达标的地方全局拉到 44px 起步）。
- **底部 sticky 操作栏**：JobPage 移动端的主操作（开始总结 / 取消 / 复制总结）做成 sticky bottom bar，距底 padding 用 `env(safe-area-inset-bottom)` 避开 home indicator。
- **SSE 稳定性**：iOS Safari 长连接 90s 空闲会断，需要后端心跳（见 §5.2）+ 前端断线自动重连。这对所有端都受益，对 iPhone 是刚需。
- **剪贴板 API**：`navigator.clipboard.readText()` 在 iOS 必须由 user gesture 触发，把「粘贴」按钮做成显式按钮，不要尝试自动读取。
- **字号与缩放**：`<meta name="viewport">` 已经设了 `initial-scale=1.0`，再补 `viewport-fit=cover`；全局字号用 rem，Safari 系统字号缩放才能生效。
- **音频预览**：JobPage 右上加一个小图标按钮「试听音频」，点开嵌一个 `<audio controls src="/v1/jobs/:id/audio">`，方便走路或通勤时边听边读字幕。WAV 在 iOS Safari 原生可播。

### 6.3 不做 PWA / iOS Shortcut 的取舍

省下来的工作量（约 2 天）挪到 §5 后端稳定化和 §3 视觉细节上。代价是：iPhone 用户每次要在 Safari 里打开 URL（少不了一次手势），无法离线打开历史壳。考虑到这是个 self-hosted 工具，URL 本来就只能在能访问后端的网络下打开，离线体验对你影响不大，这笔交易划算。

未来如果想加，PWA 是 1 个 manifest + 1 个 service worker 的事，随时能补上。

---

## 7. 功能增删建议

### 7.1 建议增加

1. **预检接口** `POST /v1/jobs/preview`：见 §4.1。
2. **dedup 提示与版本折叠**：见 §4.5。
3. **LLM 用量与成本**：见 §5.3。
4. **Token 前端授权**：浏览器首次访问弹一次输入框收 API token，存 `localStorage`；见 §5.6。
5. **导出为 PDF / 复制为富文本**：很多人想把总结直接贴到笔记软件。前端用 `marked` + `html2pdf` 即可，无需后端改动。
6. **基于章节的总结**：B 站官方 chapters 已经在元信息里取了但没用上。可以按 chapter 分段做总结，UI 上展示「分章节总结 / 全文总结」两个 tab。
7. **顶栏主题切换**：跟随系统 / 亮 / 暗三档，状态写 `localStorage`。

### 7.2 建议删除 / 弱化

1. **HomePage 上的「历史记录」按钮**：换成顶栏图标，首页空间留给主任务。
2. **glowPulse 动画 + 双层 pinkShadow**：见 §3.1。
3. **「更多」菜单里的「刷新」**：状态本来就实时推；按钮存在感不必要。改为 SSE 断连时的「重试连接」按钮。
4. **`bili-subtitle` 风格按钮的 `shadow-[0_10px_0_#d94f78,...]`**：太厚重，与新设计语言不匹配。
5. **summary 强制 JSON 包装**：见 §5.3。JSON 修复那一轮重试也可以省一次 LLM 调用。
6. **`segments_json` 列**：DB 里有这个字段但代码从不写入，是历史遗留。建议下一次 migration 删除（在确认无数据时）。

### 7.3 暂不做

- 视频内嵌播放：B 站 iframe 限制多，成本高；先用「跳转到 B 站 + 时间戳」替代。
- 多用户 / 团队空间：当前是个人工具，不引入用户体系。
- 翻译 / 多语言总结：可作 v2，先把单语流程做稳。

---

## 8. 实施步骤（按阶段拆分）

按「**最小可感知改动 → 视觉 → 流程 → 跨端 → 链路**」的顺序，分 5 个 phase，每个 phase 都能独立合并、独立交付，不会让项目长时间处于半成品状态。

### Phase 1 · 视觉减负与基础整治（1-2 天）

目标：先让现在的 UI 看起来「平衡、克制」，不动结构。

1. 删除 `tailwind.config.cjs` 中的 `pinkGlow`、`pinkGlowStrong`、`glowPulse`、`shadow-bili`、`shadow-biliHover`，统一为 `shadow-card` / `shadow-cardHover` 两档。
2. 重新定义颜色 token（§3.1 表格），把 `bg-pink` 用到的非主 CTA 位置（如 ConfirmDialog 警告图标、HistoryItem hover、subtitle source tag）换成 `bg-brand-soft` / `text-brand`。
3. `ToastProvider` 默认 autoClose=true（4s）、error 类型默认不自动关闭。
4. `formatDuration` 修复 `if (!seconds)` 把 0 当成无效值的问题，改为 `if (seconds == null || Number.isNaN(seconds))`。
5. `HomePage` 删掉 glowPulse 输入框、删掉 shadow_[0_10px_0...] 按钮，先用普通圆角按钮顶上。
6. `JobPage` 顶部 BV 号、标题、作者、时长重排成两行：第一行是 BV chip + 来源 chip + 视频源跳转链接，第二行是标题，第三行是作者 · 时长 · 创建时间。

**验收**：截图对比，首页和任务页的「视觉密度」明显下降；同一屏内最多一个粉色 Primary。

### Phase 2 · 信息架构与导航（2-3 天）

1. 引入 `wouter`，路由换成声明式（`<Route path="/jobs/:id">` 等）。
2. `AppShell` 增加顶栏：logo + breadcrumb + 历史 / 主题切换两个图标按钮。
3. 主题系统：`<ThemeProvider>` 在 `<html>` 上挂 `data-theme="light|dark|system"`，状态写 `localStorage`；CSS 用 `[data-theme="dark"]` 覆盖 §3.1 表里的颜色变量。
4. `JobPage` 拆成 `<JobHeader />`、`<JobProgress />`（新版动态步骤）、`<JobActions />`、`<JobSummary />`、`<JobTranscript />`、`<JobOptionsPanel />` 六个组件，重新按 §3.3 的桌面 / 移动布局拼装。
5. `HistoryPage` 加搜索、状态 chip、按日期分组、同 BV+CID 多版本相邻折叠（§4.5）。

**验收**：浏览器后退 / 转发可用；桌面端 JobPage 不需要滚动就能同时看到进度 + 总结 + 主操作；亮 / 暗 / 跟随系统三档切换无闪烁。

### Phase 3 · 交互流程与状态自解释（2-3 天）

1. 后端新增 `POST /v1/jobs/preview`，前端首页粘贴后展示视频卡片，再点开始。
2. `TRANSCRIPT_READY` 状态：进度卡橘色高亮 + 卡片化字幕预览 + 「确认并总结 / 重新转写 / 取消」三按钮。
3. 后端补 `error_code`，前端写 `errorMap.ts` 做友好文案 + 推荐操作（带跳转 `/settings`）。
4. 流式总结：LLM 用 `stream=True`、SSE 改造、前端打字机渲染（§5.3）。
5. `useJobStream` 加自动重连 + 心跳处理（§5.2）。

**验收**：从粘贴到看到第一行总结的时间，对短视频（< 5 分钟、有官方字幕）应该在 10-15 秒内开始流出 token；任何错误都能在 toast 里看到「下一步该做什么」按钮。

### Phase 4 · 桌面快捷键与移动端打磨（1-2 天）

1. 全局键盘快捷键 hook（`useShortcuts.ts`）：cmd/ctrl + v / enter / . / k；`?` 呼出速查浮层。
2. 字幕文件拖拽接管：JobPage 字幕区做 dropzone，支持 `.txt` / `.srt` / `.vtt`。
3. 移动端 sticky bottom action bar，处理 `env(safe-area-inset-bottom)`。
4. 全局触感目标 ≥ 44px、字号统一 rem、`viewport-fit=cover`。
5. JobPage 加可选音频试听 `<audio controls>`，按需懒挂载。
6. 主题切换的视觉细节调优：暗模式下卡片不再用阴影分层，改用 1px 内描边；高对比场景下 LLM 输出区域调到 `prose-invert`。

**验收**：键盘党桌面端整套流程不离手；iPhone Safari 上单手 sticky 按钮可达；亮 / 暗切换无 FOUC；同时跑 3 个任务时 SSE 不掉线。

### Phase 5 · 后端链路稳定与扩展（2-3 天）

1. SQLite 开 WAL + 连接池；新增 `error_code`、`token_usage_json`、`content_hash` 等列；jobs 拆 artifacts 表（视数据量决定，少则保留单表）。
2. 任务并发上限（Semaphore）、每阶段 timeout、recover 策略调整（§5.1）。
3. yt-dlp 改 Python API + 下载进度推 SSE。
4. SenseVoice 单例 + lazy load；接入 faster-whisper 可选后端。
5. 实现音频 / 任务的过期清理任务（lifespan 内启动）。
6. 把 `VITE_API_TOKEN` 改成「前端 localStorage 输入 token」（§5.6），更新部署文档。

**验收**：跑一个 1 小时长视频不再卡死；同时跑 3 个任务不会把机器打挂；连续运行 7 天后 `data/audio` 目录里看不到超过 7 天的文件。

---

## 9. 风险与回滚

| 改动 | 风险 | 缓解 |
| --- | --- | --- |
| LLM 流式 | 部分模型提供商不支持 stream 或 stream 字段不一致 | 在 settings 里给每个模型一个「禁用流式」开关，失败自动回退 |
| 删除 `glowPulse` / 厚阴影 | 用户已经习惯当前外观 | 把改动放到 Phase 1，先发主题选择项「经典 Bilibili 风」 / 「极简」，默认极简，让老用户能切回去 |
| 拆 jobs 表 | 已有数据迁移 | 写迁移脚本，全表导出 → 新表导入；先在 dev DB 跑通 |
| `VITE_API_TOKEN` 撤掉 | 老部署的浏览器直接 401 | 后端在过渡期同时支持 query string `?token=` 与新机制 |
| 启动恢复策略变更 | 之前 TRANSCRIBING 中的任务会被置 FAILED | 提供 `POST /v1/jobs/{id}/retry` 接口，UI 上有「重试」按钮 |

每个 phase 单独成 PR，CI 跑现有 `pytest`，前端补一些 React Testing Library 关键路径用例（HomePage 提交、JobPage 状态转换、HistoryPage 搜索）。

---

## 10. 已确认的设计决定

经过一轮对齐，下列方向已定，后续无需再讨论：

1. **主题色调**：中性灰白 + 小面积品牌色；品牌色选 **靛蓝 `#5B6DF0`**（理由见 §3.1）。
2. **暗色模式**：本轮包含，方案见 §3.1 表格 + §8 Phase 2 的 `<ThemeProvider>`。
3. **设置页**：不做。LLM / 邮件 / Cookie 仍在后端 `.env`；任务级偏好在「更多选项」；主题在顶栏按钮。
4. **路由库**：`wouter`。
5. **历史页同 BV 多次任务**：相邻折叠展示，主卡 + 「+N 个早期版本」chevron。
6. **PWA / iOS Shortcut**：均不做（理由见 §6.3）。
7. **Logo**：新设计一套，详见 §11。

---

## 11. Logo 设计

### 11.1 思路

名字 `biri-youyaku` 有两层语义可以借用：

- **biri**（ビリビリ）—— 电流劈啪的拟声词，对应「⚡ 闪电」。
- **youyaku**（要約）—— 摘要 / 终于的双关，对应「把长内容压缩成短结论」。

最简洁的视觉合并方式：**圆角方块 + 闪电**。圆角方块给现代 app icon 的亲切感（不冷不严肃），白色闪电在靛蓝底上传达「电、瞬间、能量」。这套组合在 16×16 favicon 到 512×512 大图都能保持识别度，不依赖文字。

我刻意没有用 `要約` 的汉字（文化偏窄、小尺寸糊掉）、没有用「Y」字母（无意义、和「要約」对应弱）、也没有用语音气泡（太通用）。

### 11.2 资产

落到 `web/public/` 下三个文件：

| 文件 | 用途 | 尺寸 |
| --- | --- | --- |
| `logo-mark.svg` | 单独的 mark，方块形态 | 任意，源文件 256×256 viewBox |
| `logo-full.svg` | mark + 「biri-youyaku」字标横排，用于顶栏 / 文档 | 任意，源文件 720×160 viewBox |
| `favicon.svg` | 浏览器 tab 图标（SVG favicon，现代浏览器全支持） | 任意，源文件 64×64 viewBox |

`web/index.html` 替换为：

```html
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="apple-touch-icon" href="/logo-mark.svg" />
<meta name="theme-color" content="#5B6DF0" />
```

### 11.3 使用规范

- **顶栏品牌区**：用 `logo-full.svg`，高度 24px，左侧距边 16px；点击回首页。
- **空状态 / 启动屏**：用 `logo-mark.svg`，宽度 64px，居中；下方一行文案。
- **favicon**：用 `favicon.svg`；为兼容老浏览器再导出一张 `favicon.ico`（32×32）作为 fallback。
- **暗模式**：mark 的方块底色保持 `#5B6DF0`（不要改成 `#9099FF`，会让 logo 在不同页面感觉不一致），闪电仍是 `#FFFFFF`。字标的文字色跟随页面 `fg`（亮模式 `#18191c`、暗模式 `#e8e9ee`），中间的分隔线（`-`）始终 brand 色。
- **最小尺寸**：mark 不小于 20px，full 字标不小于 96px 宽。
- **禁用变体**：不要给 mark 加阴影 / 渐变 / 描边 / 旋转 / 倾斜；不要把闪电单独抠出来用。

### 11.4 后续可扩展

如果以后想丰富品牌物料，这套 mark 可以延展：

- **加载动画**：闪电做 0.6s 的「从上到下扫过」高光，用于「总结生成中」的占位卡。
- **状态色变体**：进行中 `#5B6DF0`、成功 `#16a34a`、失败 `#dc2626`、等待确认 `#d97706` —— 在错误页 / 邮件签名等场景使用。
- **横排小图标**：把闪电单独抠出来做「⚡ 已就绪」「⚡ 总结完成」等通知图标。

---

## 附录 A：API 变更清单

新增：
- `POST /v1/jobs/preview` — 入参 `{url}`，出参 `{ok, meta: VideoMeta, dedup_job_id?: string}`。
- `POST /v1/jobs/{id}/retry` — 从最近失败的阶段重跑。
- `GET /v1/config/runtime` — 返回 `{llm_configured, email_configured, bilibili_cookie_configured}`。
- `GET /v1/usage?range=7d` — LLM 用量统计。

变更：
- `Job` 序列化增加 `error_code`、`token_usage`、`stage_timings`、`stream_finished_at`。
- `POST /v1/jobs` 与 `POST /v1/jobs/{id}/resume` 不再接受 `llm_api_key` in body；改用请求头 `X-LLM-API-Key`，避免落库与日志泄漏。

废弃：
- `GET /v1/jobs/{id}` 中的 `transcript` 字段在长字幕场景下太大，提供 `?include=summary,meta` 风格的 sparse fieldset；老接口保留向后兼容一个版本。

---

## 附录 B：前端组件目录建议

```
web/src/
  app/
    router.tsx
    shell/AppShell.tsx
    shell/TopBar.tsx
    theme/ThemeProvider.tsx
  pages/
    HomePage.tsx            // §3.2
    JobPage.tsx             // §3.3 容器
    HistoryPage.tsx         // §3.4
    SettingsPage.tsx        // §7.1.1
  features/
    job/
      JobHeader.tsx
      JobProgress.tsx
      JobActions.tsx
      JobSummary.tsx
      JobTranscript.tsx
      JobOptionsPanel.tsx
      useJobStream.ts       // 含心跳 / 重连
    history/
      HistoryFilters.tsx
      HistoryGroup.tsx
      HistoryItem.tsx
    home/
      UrlComposer.tsx       // 输入 + 粘贴 + 校验 + 预检
      RecentJobsStrip.tsx
  ui/
    Button.tsx               // primary / secondary / ghost / danger
    Card.tsx
    Toast.tsx                // §3.5 行为修正
    ConfirmDialog.tsx
    Chip.tsx
    KeyboardHint.tsx
  lib/
    api.ts
    sse.ts
    format.ts
    errorMap.ts             // §4.4
    storage.ts              // localStorage 包装，含设置持久化
    pwa.ts                  // 安装提示 / Service Worker 注册
```

按此拆分后，组件职责清晰，单测好写，未来加新的 feature 不会再让 JobPage 变成 800 行。
