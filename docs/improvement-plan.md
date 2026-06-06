# biri-youyaku 改进计划（单人版）

> 范围：UI/交互优化、公网部署的访问控制、Prompt 重写。
> 前提：**只有你自己用**。任何「per-user 限流 / Turnstile / BYOK / 配额」之类的设计都不需要——只要确保陌生人进不来即可。
> 写作日期：2026-06-06。审计基准：当前 `main` 分支代码。
> 优先级：P0=立刻、P1=近期、P2=有空再做。

---

## TL;DR

1. **门锁**：Cloudflare Access 套 tunnel 域名，allow list 只放你自己邮箱。除此之外**所有反滥用代码都不用写**——没有第二个用户存在。
2. **Prompt 重写**：当前总结被 300-600 字硬上限和「过滤口水话」组合压得太狠，丢失原话和细节。新增「原文金句」「提到的具体内容」两个不限量章节。
3. **UI 摘掉两块浪费**：后端 `/v1/jobs/preview`（带去重和时长预检）和 `/v1/config/runtime`（运行时能力探测）已经实现但前端零调用；接上即可。

---

## A. UI / 交互改进

### A1. IdleView 直接 POST，没用 preview（P0）

**现状**：`Workspace.tsx:submitNew` 拿到 URL 后立刻 `createJob(url, {task_type:'summary', email_enabled:true})`。`api.ts` 里有 `previewJob` 函数但没人调用。

**问题**：
- 超过 `MAX_VIDEO_DURATION_SECONDS` 的视频要等 `FETCHING_META` 跑完才在 toast 里吐错。
- 后端 `preview_job` 会返回 `dedup_job_id`（同 `bvid+cid` 最近一条），完全没暴露给用户。重复粘贴只会建一条新任务白烧 token。
- 你按「开始」前看不到标题、时长、字幕来源——粘错（B 站「分享」有时是合集主页 URL）只能取消重来。

**建议**：IdleView 改成两步：

1. 调 `previewJob(url)`，渲染一个轻量确认卡（标题 / UP / 时长 / 字幕来源）。
2. 卡片底部按钮：「开始总结」、「这条以前看过 →」（仅当返回 `dedup_job_id`）、「换一条」。

可以加个「下次不再确认」localStorage 选项让你自己常用模式跳过。

### A2. `email_enabled: true` 硬写死（P0）

**现状**：`submitNew` 里写死 `email_enabled:true`。后端 `EMAIL_ENABLED=false`（你公网部署用不用邮件再说）时会直接 400。

**建议**：启动时调 `getRuntimeConfig()` 读 `email_configured`，没配就不传 `email_enabled`。preview 确认卡里给个「✉️ 发到邮箱」复选框，默认跟随 `email_configured`。

### A3. 没有用户可调的选项面板（P1）

**现状**：`JobOptions` 后端支持 `summary_language` / `force_asr` / `llm_model` / `prompt_template`，前端一个都不让选。

**建议**：preview 确认卡下挂一个折叠的「高级选项」：

| 控件 | 字段 | 备注 |
| --- | --- | --- |
| 总结语言 | `summary_language` | 4-5 个预设 |
| Prompt 预设 | `prompt_template` | 「会议纪要 / 学习笔记 / 短视频亮点」 |
| 强制语音转写 | `force_asr` | 官方字幕烂时用 |
| 模型 | `llm_model` | 调 `/v1/llm/models` 拉列表 |

折叠态首屏隐藏。

### A4. HistoryDrawer 缺基本能力（P1）

**现状**：写死 `listJobs({limit:30})`，没搜索、没分页、没批删。

**建议**：
- 顶部加搜索框（标题 / UP 前端模糊匹配）。
- 滑到底自动加载（用 `next_cursor`）。
- 顶部加「清空已完成」按钮，调 `deleteAllJobs()`。

### A5. Done 视图没暴露 token usage / 阶段耗时（P2）

**现状**：`Job.token_usage` 和 `stage_timings` 都在 payload 里，UI 没用。

**建议**：Done 视图底部加一行「⏱ 字幕 12.3s · 总结 8.1s · ¥0.03」。维护一张 `model → unit_price` 映射估算成本——你自己烧的钱看着才有感觉。

### A6. 流式总结期间无法换 prompt/模型重试（P2）

**现状**：SUMMARIZING 阶段只能 cancel 整个任务。

**建议**：cancel 按钮旁边加 ChevronDown 菜单：「换 prompt 重试 / 换模型重试 / 取消」。逻辑上是 cancel + retry with overrides，后端已经支持。

### A7. 暗色模式没人工开关（P2）

**现状**：`tailwind.config.cjs` 用 `darkMode: 'media'` 跟随系统。

**建议**：右上角加月亮/太阳/auto 三态切换，写 localStorage。

### A8. 缺键盘快捷键（P2）

**建议**：`Cmd/Ctrl+K` 焦点回 URL 输入框；`g h` 打开历史。

### A9. 错误信息卡的可访问性（P2）

- 「复制」按钮 aria-label 改成「复制错误详情」。
- StepCarousel 底部点指示器加 `aria-current="step"` 和 `aria-label="第 N 步：xxx"`。

### A10. IdleView 空状态太空（P2）

**建议**：URL 输入框下方加最近 3 条历史的快捷卡片。

---

## B. 公网部署：访问控制（**只需要做这一件事**）

### B1. Cloudflare Access：白名单 = 你一个人（P0）

**现状**：`web/src/lib/api.ts:96` `const API_TOKEN = (import.meta.env.VITE_API_TOKEN ?? '').trim()`。`DEPLOY.md` 已经写了「token 打进 bundle，所有人能在 devtools 看到」。

**问题**：现在是「弱口令」级别防爬虫。任何路过 Vercel 域名的人都能抓到 token 直接打你后端。

**方案**：CF Zero Trust → Access → Applications → Add application。

```
Application type: Self-hosted
Application domain: your-api-domain.example.com
Policy name: only-me
Action: Allow
Include rule: Emails → 你的邮箱
Session duration: 24h（或更长，你自己用没必要短）
```

后端改动：
- `.env` 里 `API_TOKEN` 留空。
- `auth.py:require_token` 改成：若 `CF_ACCESS_TEAM_DOMAIN` 配置了，校验 `Cf-Access-Jwt-Assertion` header（用 CF 的 JWKS 验签，过期 / aud 不对 → 401）；否则走原有 `API_TOKEN` 逻辑。
- 前端 `VITE_API_TOKEN` 留空，浏览器走 CF SSO 后 cookie 自动带。

`.env` 新增（**唯二两个配置项**）：
```env
CF_ACCESS_TEAM_DOMAIN=your-team.cloudflareaccess.com
CF_ACCESS_AUD=<Access application audience tag>
```

**这就完了**。

### 为什么其他反滥用机制都不需要

| 之前考虑的 | 单人场景下的判断 |
| --- | --- |
| per-identity 在飞数 | 你不会自己 DoS 自己 |
| per-identity 日任务数 | 同上 |
| Turnstile | 没有匿名访问者 |
| SSE 限流 | 你不会同时开 50 个 SSE |
| 出口流量预算 | 视频时长上限 `MAX_VIDEO_DURATION_SECONDS=9000`（2.5h）已经够防你手抖 |
| 邮件日上限 | 同上 |
| BYOK | 没有第二人，全是你的 key |

`MAX_INFLIGHT_JOBS=20`、`MAX_VIDEO_DURATION_SECONDS=9000`、`LLM_BASE_URL_ALLOWED_HOSTS` 这些**已有**的全局阈值留着即可——单人场景下它们的作用从「防陌生人」降级为「防你自己手滑」，比如不小心循环创建任务、不小心粘了一个 10 小时的直播录像。

### 可选小清理（P2，做不做都行）

- `app.py` 的 CORS `allow_methods=["*"], allow_headers=["*"]` 收成显式列表，纯洁癖。
- `DEPLOY.md` 里关于 `VITE_API_TOKEN` 的「弱口令」段落删掉，改成「上 CF Access」。
- `README.md` 部署章节同步。

---

## C. Prompt 重写（P0）

### 现状

`server/biri_youyaku/modules/llm/prompts.py` 5 个 prompt，主路径用 `SUMMARY_MARKDOWN_PROMPT`，长视频分段用 `SUMMARY_PROMPT` + `SUMMARY_MERGE_MARKDOWN_PROMPT`。

### 问题（逐条）

1. **硬字数上限**：`"总长度控制在 300-600 字"`。60-90 分钟的演讲被压到 600 字，模型只能扔细节保宏观。
2. **「过滤口水话/避免空话」组合拳**：模型实际执行时会把所有具体例子、原话、数据都当成「非高密度」一起丢掉。
3. **没有强制原文引用章节**：`核心内容` 要求「按视频逻辑顺序提炼 3-7 条，每条一句话」——这是要求**改写**而不是**引用**。原话完全消失。
4. **`值得关注的细节` 只「最多 3 条」**：模型本来能列 10 个数据/工具/案例，被这条压回 3。
5. **Merge prompt 把「去重、合并同类信息」放第一位**：分段总结里好不容易保住的原话和细节，到合并这一步又被压一次。

### 重写方案

把 prompt 从「写读后感」改成「**写带引用的笔记**」。中文版替换 `SUMMARY_MARKDOWN_PROMPT`：

```
你是视频字幕的「笔记整理员」，不是「摘要作者」。读者的目标是：不看视频就能掌握全部有用信息，包括 UP 主原话、举的例子、说的数据。

# 输入
- 标题：{{title}}
- 字幕来源：{{subtitle_source}}
- 字幕：
{{transcript}}

# 总原则
- 字幕里**说过**的话尽量保留；不是「值得保留才保留」，而是「除非是纯口水话否则就保留」。
- 宁可让笔记长，不要丢信息。长度跟视频长度走，**不设上限**。
- 输出是给读者的笔记，不是给视频做广告。**不**写「精彩」「值得一看」「让人深思」这类评价。

# 处理细节
1. 口头禅（「那个」「就是说」「对吧」「嗯」）可省。
2. 重复表达留一次。
3. 错字、ASR 误识可按上下文修正，**但不要替换原词**——书名、工具名、人名以 UP 主说的为准，ASR 拼错也尽量按上下文还原。
4. 字幕里没有的内容**不要补**。不确定就不写。

# 输出（直接 Markdown，不要 JSON 不要代码块）

## TL;DR
一句话（30 字内）：这个视频在讲什么。不要照抄标题。

## 核心要点
按视频时间顺序列 5-15 条要点，每条 1-3 句话。**短视频可以少，长视频不要少**。
每条要点应该回答「视频在这一段讲了什么具体内容」，不要泛泛写「介绍了 X 的优势」，要写「X 比 Y 快 3 倍，因为 Z」。

## 原文金句
从字幕里挑 5-15 句**值得直接引用**的话，用 `> ` 引用块按出场顺序列出。
判断标准：观点强烈、定义清晰、有具体数据、有反常识结论、或者有梗。
**不要**复述、不要改写——逐字引用（修正明显错字除外）。
如果视频实在没有值得引用的句子（纯流水账 vlog），写「（无突出原话）」。

## 提到的具体内容
逐项列出视频里出现的「专有名词」，**有就列，没有就省略对应小项**：
- **人物**：提到的人名（含简短背景，如「李飞飞（ImageNet 作者）」）
- **作品/工具**：书名、论文、软件、网站、产品、API
- **数据/数字**：百分比、价格、参数量、时间、距离等具体数字
- **案例**：UP 主举的具体例子（公司、事件、新闻）
- **链接/资源**：UP 主口播或字幕里提到的 URL、GitHub repo、邮箱

每项 1 行，**全部列出，不设上限**。

## 结论 / 行动建议
视频末尾的明确结论、推荐、号召或操作步骤。没有就省略本节。

## 字幕质量备注
仅当字幕明显残缺、ASR 噪声大、或某段听不清时写一句话说明；正常就省略本节。
```

### Merge prompt 的对应改动

把 `SUMMARY_MERGE_MARKDOWN_PROMPT` 里「去重、合并同类信息」改成：

```
合并规则：
- 「TL;DR」和「核心要点」可以合并、精简、去重。
- 「原文金句」「提到的具体内容」**不允许删减**。如果两段都引用了同一句，只保留一次；否则全部按出场顺序保留。
- 不要把多个分段的「具体内容」合并成抽象描述，要保留具体名字和数字。
```

### 落地步骤

1. 用上面的中文模板**完全替换** `SUMMARY_MARKDOWN_PROMPT`（主路径）和 `SUMMARY_PROMPT`（旧 JSON 路径，结构对齐即可）。
2. 用 merge 改动版替换 `SUMMARY_MERGE_MARKDOWN_PROMPT` 和 `SUMMARY_MERGE_PROMPT`。
3. 找 3 个长度不同的视频（5min 短解说、30min 教程、90min 访谈）回归测试，肉眼对比新旧输出。
4. 输出明显变长是预期的；如果你后续觉得「太啰嗦」，再加一行 `如果某节实在没有内容就省略整节，不要硬凑`，但**不要再加字数上限**。

### 隐性收益

新版强制「按时间顺序列要点」+「原文金句按出场顺序」，让你能用关键词在笔记里反查到原视频对应位置。配合 A5「显示 stage_timings / token usage」，整体体感会从「LLM 帮你写了篇读后感」升级到「视频的可搜索笔记」。

---

## D. 落地顺序建议

| 阶段 | 改动 | 估时 |
| --- | --- | --- |
| **Day 1** | C prompt 重写（5 个模板）+ 回归测试 3 个视频 | 2h |
| **Day 1** | B1 CF Access 套域名 + 后端 JWT 校验 | 4h |
| **Week 1** | A2 runtime config 接入 + A1 preview 二步式 | 2h + 4h |
| **Week 2** | A3 高级选项 + A4 历史搜索/分页/批删 | 4h + 4h |
| **有空再做** | A5 cost 透明 + A6 流式重试 + A7 暗色 + A8 快捷键 + A9 a11y + A10 历史快捷卡 | 视情况 |

排 prompt 在最前是因为：**前端改 10 个 UI 细节也比不上 prompt 改一次带来的体感升级**——单人场景下你每次跑出来的总结质量才是真正决定你愿不愿意持续用这个工具的因素。

---

## E. 你的使用成本（全部落地后）

- **一次性**：在 CF Zero Trust 建一个 Access application（10 分钟），把自己邮箱填进 allow list；改 `.env` 加两行 `CF_ACCESS_*`。**没了**。
- **日常**：访问前端 → 浏览器弹一次 SSO（已登录 Google 直接过，体验等同访问 Google 内部工具）→ 进入页面。SSO session 设 24h 以上基本无感。
- **本地 dev**：继续走 `localhost:5173 → localhost:17821`，`.env` 里 `API_TOKEN` 留空，**完全不需要 CF Access**——只有暴露在公网的 tunnel 域名才走 Access。

---

## F. 不在本计划范围

- 任何 per-user 配额 / Turnstile / BYOK / SSO 之外的账号体系 —— 单人场景下没意义。
- Postgres 迁移 / Redis 限流后端 —— SQLite + slowapi 内存计数完全够你一个人。
- 隐私/E2E 加密 —— 数据已经全本地，过度工程。
