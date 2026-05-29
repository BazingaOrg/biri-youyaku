# biri-youyaku 前端瘦身改造 Plan

> 目标：把目前「首页 + 任务页 + 历史页 + 顶栏 + 高级选项 + 主题切换」的多层结构，收成一个**单页流式**的体验：粘贴链接 → 一键要約 → 原地展开进度 → 出结果。其它能力（音频、历史、重发邮件）作为「次要项」隐藏在角落或结果之后。

---

## 0. 设计基调（命名 × 风格）

项目名拆开看：

- `要約 / ようやく` —— 日语「摘要」，同音「终于」。
- `ビリビリ / biri` —— B 站的日语口语。

所以基调定为：**和风文艺、轻量克制、带一点点 B 站粉的暖意**。不做花哨装饰，留白要够，文字要短。

### 0.1 推荐主题色（Sakura-on-Washi）

| Token | Light | Dark | 说明 |
| --- | --- | --- | --- |
| `--color-bg` (canvas) | `#FBF7F2` 和纸米 | `#15131A` 墨夜 | 暖底，不用纯白 |
| `--color-bg-elevated` (panel) | `#FFFFFF` | `#1E1B23` | 卡片 |
| `--color-bg-sunken` (lift) | `#F2ECE4` | `#0F0D12` | 输入框 / 次级块 |
| `--color-fg` (ink) | `#2B2A33` 墨 | `#EDE7DB` 宣 | 主文字 |
| `--color-fg-muted` | `#8A8593` | `#9B95A4` | 次级文字 |
| `--color-border` | `#ECE3D6` | `#2A2630` | 描边 |
| `--color-brand` | `#E26A8D` 樱红 | `#F29CB4` 浅樱 | 按钮、点缀 |
| `--color-brand-soft` | `#FBE7EE` | `#3A1F2A` | 标签底 |
| `--color-success` | `#5B8C6A` 松绿 | `#8FBF9F` |  |
| `--color-warning` | `#C98A3F` 黄丹 | `#E2B074` |  |
| `--color-danger` | `#C0533F` 朱赤 | `#E08573` |  |

字体保持系统栈，但增加 `"Noto Serif JP", "Source Han Serif"` 作为标题可选，让「要約」二字有点书卷气；正文仍是 sans。

> 备选方案：如果你觉得樱粉太「甜」，可以把 brand 换成 `#C0533F` 朱赤（更近浮世绘的赤），或 `#5B6E8C` 墨青（更冷静）。先按樱红出，调起来很快。

### 0.2 文案风格

- 一句话以内能说清的，不写两句。
- 用「要約」「字幕」「邮箱」这种实词，不写「快速智能 AI 处理」这种空话。
- 可以有一两处小双关 / 谐音梗，但只放在首屏标题和空状态，不要全篇玩梗。

候选文案样张：

| 位置 | 旧文案 | 新文案 |
| --- | --- | --- |
| 输入框上方一行（无 logo，无品牌名） | 粘贴 B 站链接，要約一下 / 副标题两行 | **粘贴 B 站链接，要約成 Markdown，发到你邮箱** |
| 主按钮（空） | 解析视频 | 要約 |
| 主按钮（跑） | 解析中... | 正在要約… |
| 完成 toast | 总结已完成 | 要約完了。 |
| 空历史 | 暂无历史任务。粘贴一个链接开始。 | 还没有要約过的视频。 |
| 错误兜底 | 创建任务失败 | 没能开始，换个链接试试？ |

> 顶部不再出现 `biri-youyaku` / logo / 副标题分段。只有这**一行功能描述**，让首次来的人 3 秒看懂这是个什么东西。

描述行的几个候选，选一条就好：

1. 「粘贴 B 站链接，要約成 Markdown，发到你邮箱」 ← 最直白，**推荐**
2. 「B 站视频 → 字幕 → Markdown 要約 → 邮箱」 ← 流程感
3. 「一条 B 站链接，要約 + 邮件，一次搞定」 ← 节奏感
4. 「把 B 站视频要約成 Markdown，自动发邮箱」 ← 动词在前

---

## 1. 信息架构（IA）改造

### 1.1 现状

```
AppShell（顶栏：logo / 标题 / Home / History / Theme）
 ├── /            HomePage（输入 + 预览 + 高级选项 + 最近任务横滑）
 ├── /jobs/:id    JobPage（元信息 + 进度侧栏 + 总结 + 字幕 + 移动端 sticky bar）
 └── /history     HistoryPage
```

### 1.2 目标

```
单页 / 无顶栏
 ├── 中央：URL 输入框 + 「要約」按钮（其它什么都没有）
 ├── 提交后：输入框上滑 → 原地展开「进度时间线 + 当前步骤 + 产出」
 ├── 完成后：在产出下方追加「下载音频 / 重发邮件 / 复制 / 下载 Markdown」
 ├── 右下角浮动小钮：历史（点开是侧抽屉，不是新页面）
 └── 顶部不再有任何导航或品牌栏；logo 只放在页脚最小一行
```

不再有 `/history`、不再有 `/jobs/:id` 这种二级页。路由仅作为**深链入口**保留（粘贴一条 `/jobs/xxx` 进来仍能直达，但视觉上没有「跳页」感）。

### 1.3 三个阶段（同一个页面）

```
状态 A：idle（空）
┌─────────────────────────────┐
│                             │
│   粘贴 B 站链接，要約成      │   ← 一行功能描述（无 logo 无品牌名）
│   Markdown，发到你邮箱       │
│                             │
│  ┌───────────────────────┐  │
│  │ 粘贴 B 站链接…        │  │   ← 圆角大输入框，自动 focus
│  └───────────────────────┘  │
│        [   要約   ]          │   ← 一个主按钮
│                             │
│   昨天那条还没看完 →  ⌛    │   ← 仅当有「未完成任务」时出现，点击恢复
│                             │
└─────────────────────────────┘
                          [历史 3]  ← 右下浮动

状态 B：running（提交后） —— 单卡片 + 左右切步
┌─────────────────────────────┐
│  ←  把链接交给我             │   ← 顶部一行：返回 + 标题
│                             │
│  [封面 / 标题 / UP / 时长]   │
│                             │
│  ┌───────────────────────┐  │
│  │                       │  │
│  │     ✓ 取字幕           │  │   ← 一次只展示一步：图标 + 名称 +
│  │     1.2s · 官方字幕    │  │     时长 / 状态 / 该步的产物预览
│  │                       │  │
│  │  〔 字幕预览 3 行 〕   │  │
│  │                       │  │
│  └───────────────────────┘  │
│                             │
│   ‹  ● ● ◐ ○ ○  ›           │   ← 底部一行 dots（5 步），当前步高亮
│                             │     左右箭头 / 滑动 / 点 dot 都能切
│                             │     当前正在跑的步会自动定位为「当前」
└─────────────────────────────┘

状态 C：done
┌─────────────────────────────┐
│  ← / 新建                   │
│  [封面/标题/UP]              │
│  [Markdown 总结]            │
│                             │
│   下载音频  复制  下载 .md  重发邮件
└─────────────────────────────┘
```

#### 状态 B 的「单卡片 + 步骤分页」细则

5 个步骤固定：① 解析视频 → ② 取字幕（或下载音频 + ASR）→ ③ 要約 → ④ 发邮件 → ⑤ 完成。
每张卡片内容统一三段式：

1. **状态行**：图标（○ 等待 / ◐ 进行中 / ✓ 完成 / ✕ 失败）+ 步骤名 + 耗时或进度（百分比 / SSE 实时数）。
2. **要点行**：一句话当前状态。例：「官方字幕可用」「ASR 中，已处理 03:42 / 12:18」「正在调用 `gpt-4o-mini`」。
3. **产物预览**（可空）：
   - 取字幕 → 前 3 行字幕。
   - ASR → 进度条 + 已转写片段计数。
   - 要約 → 已生成的开头 200 字（流式增量）。
   - 发邮件 → 收件人地址 + 「已送达」or「未配置邮箱，已跳过」。

切换规则：

- 默认锁定在「当前进行中的那一步」，新步骤一变化卡片自动滑过去（同向、220ms）。
- 用户主动切（点 dot / 左右箭头 / 触摸滑动）后，进入**手动锁定**态：不会被自动滑走；卡片右上角出现「↻ 跟随当前」小按钮，点一下回到自动模式。
- 未到达的步骤可以预览（卡片是占位态：「等待中…」），不阻断切换。
- 失败步骤的卡片用 `danger` 描边，要点行直接显示后端 `error_message` 的 friendly 版本，下方一个「重试」按钮。

> 实现上是一个受控的 carousel：5 张 div 横向铺排，外层 `overflow: hidden` + `transform: translateX(-N * 100%)`。不需要引第三方库；左右切手势用 pointerdown/move/up + 30% 阈值即可。

---

## 2. 默认配置策略（去掉「高级选项」）

- 前端**不再渲染** `OptionsForm`。
- 提交任务时只发 `{url, options: {task_type: 'summary', email_enabled: true}}`，其余全部走后端 `/v1/config/defaults`。
- `email_recipient` 不在前端表单里出现：
  - 后端 `EMAIL_DEFAULT_RECIPIENT` 已配置 → 直接发。
  - 没配置 → 后端跳过邮件，前端只在产出区显示一个「邮件未配置」的灰字 hint，不弹错。
- 「仅下载音频」按钮从首页移除，挪到**结果页**「下载音频」按钮里（任何 job 完成后都能下，逻辑已有）。
- 模型发现 `discoverLlmModels`、字幕上传 `replaceTranscript`、`force_asr` 重转写：保留 API，但**前端 UI 全部隐藏**。需要时通过 URL 参数或后续设置页恢复，本次不做。

---

## 3. 主题与暗黑

- 删除 `ThemeProvider` 的三态切换 UI（`Sun / Moon / Monitor` 那个按钮）。
- 保留 `prefers-color-scheme: dark` 媒体查询，CSS 变量按系统自动切；`html[data-theme]` 不再写入。
- `ThemeProvider` 文件可保留为空壳（避免改 main.tsx），但去掉状态、去掉 cycleTheme。

---

## 4. 状态恢复 —— 关掉页面再回来怎么办？

这是核心交互问题。规则：

### 4.1 提交即落库

用户点「要約」的那一刻：

1. 调 `POST /v1/jobs` 拿到 `job_id`（已有逻辑）。
2. 立刻 `localStorage.setItem('biri:active', JSON.stringify({jobId, url, createdAt}))`。
3. 同时 `history.replaceState(null, '', '/?j=<jobId>')`，URL 里也带一份，方便分享 / 收藏。

### 4.2 再次进入

页面加载时按优先级判断：

1. **URL 带 `?j=<id>`** → 直接拉 `getJob(id)`，进入对应状态（B 或 C）。
2. **localStorage 有 active**：
   - 拉 `getJob(activeId)`：
     - 仍在跑（`PENDING / FETCHING_META / DOWNLOADING_AUDIO / TRANSCRIBING / SUMMARIZING / EMAILING`）→ 直接进入状态 B，并续上 SSE。
     - 已 `TRANSCRIPT_READY`（等待确认）→ 因为我们去掉了二次确认，前端**自动**调 `resumeJob` 让它继续。
     - `COMPLETED / FAILED / CANCELED` → 进入状态 C，并把 localStorage 清掉。
3. 都没有 → 状态 A，但若 `listJobs({limit:1})` 里最近一条仍在跑，把它作为「昨天那条还没看完 →」提示条出现在输入框下方一行（可点恢复，可右侧 × 忽略）。

### 4.3 同源标签同步

监听 `storage` 事件：A 标签提交、B 标签刚好打开 → B 标签自动跟上。不做复杂的 leader election，简单覆盖即可。

---

## 5. 历史任务 —— 角落而不是页面

- 删除 `/history` 路由和 `HistoryPage.tsx`。
- 新增 `HistoryDrawer` 组件：
  - 入口：右下角 56×56 的浮动圆钮，里面是「历史」图标 + 未完成数量小红点。
  - 点击从右侧滑出 360px 抽屉（移动端全宽）。
  - 列表项**精简到三行**：标题、UP + 时长、状态徽章 + 时间。
  - 操作只保留两个：「打开」「删除」。重发邮件 / 重试 / 取消都挪到打开后的结果页里。
  - 搜索、批量删除、复杂筛选**砍掉**。
- 列表数据：直接 `listJobs({limit: 30})`，不再分页；够用。

---

## 6. 动画与过渡

只用四种动效，统一时长 220ms（抽屉 320ms），曲线 `cubic-bezier(0.2, 0.8, 0.2, 1)`：

1. **状态 A → B**：输入框 `transform: translateY(-12vh) scale(0.92) + 透明度 1→0.6`，下方卡片 `opacity 0→1 + translateY 12px → 0`。
2. **步骤切换（carousel）**：卡片容器 `transform: translateX(-N * 100%)`，220ms；底部 dots 当前点从 `8×8 → 20×8` 的圆角矩形过渡。新一步抵达时若处于自动模式，先把当前点 ◐ 收为 ✓（120ms），再平移到下一张（220ms），两段串行不重叠。
3. **状态图标**：`○ → ◐ → ✓ / ✕` 用一个固定 18×18 的 SVG slot，里面三种 path crossfade（150ms），不用 framer-motion 也能写。
4. **抽屉**：右滑 320ms，背后 8px 模糊 + 黑色 30% 蒙层。

尊重 `prefers-reduced-motion`，命中时所有动效降级到 1ms（现有 CSS 已经处理）。

> 不需要 framer-motion。carousel 用 `transform + transition` + 三个状态变量（`currentStep`、`displayStep`、`manualLock`）就够。包体保持现状。

---

## 7. B 站链接兼容

`web/src/lib/url.ts` 现在只覆盖：

```
bilibili.com/video/(BV…|av…)
b23.tv/<slug>
bilibili.com/bangumi/play/
BV… / av…  纯 ID
```

需要补：

- `m.bilibili.com/video/…`（移动端 web）
- `b.23.tv/…`（你提到的另一种短链域名形式）
- `space.bilibili.com` 暂不接（不是单视频）
- 链接后可能带 `?p=2`、`?t=120`、`?spm_id_from=…`，正则**只匹配前缀**就够，参数交给后端。

新正则草案：

```ts
const BILI_PATTERNS: RegExp[] = [
  /^https?:\/\/(www\.|m\.)?bilibili\.com\/video\/(BV[0-9A-Za-z]{10}|av[0-9]+)/i,
  /^https?:\/\/b\.?23\.tv\/[A-Za-z0-9]+/i,
  /^https?:\/\/(www\.|m\.)?bilibili\.com\/bangumi\/play\//i,
  /^BV[0-9A-Za-z]{10}$/i,
  /^av[0-9]+$/i,
]
```

同时输入框 onPaste 时做一次 `trim + 取第一个 URL`，因为手机端复制经常带上「【标题】… https://b23.tv/xxx 复制开链接看」整段。处理逻辑：

```ts
const match = pasted.match(/https?:\/\/[^\s]+/)
setUrl(match ? match[0] : pasted.trim())
```

后端 `_parse_video_url` 也应同步识别 `b.23.tv`、`m.bilibili.com`，本次 plan 范围内一起改。

---

## 8. 文件级改动清单

> 后续真正动手时按这个顺序提 PR，每条都是独立可合并粒度。

| # | 动作 | 文件 |
| --- | --- | --- |
| 1 | 新主题变量、字体栈 | `web/src/styles.css`, `web/tailwind.config.cjs` |
| 2 | URL 正则补 `m.bilibili.com` / `b.23.tv`，加 paste 抽取 | `web/src/lib/url.ts`, `web/src/components/UrlInput.tsx` |
| 3 | 后端 URL 解析对齐 | `server/biri_youyaku/...`（待定位） |
| 4 | 拆掉 AppShell 顶栏与三态主题 | `web/src/components/AppShell.tsx`, `web/src/components/ThemeProvider.tsx`, `web/src/App.tsx` |
| 5 | 单页改造：把 HomePage / JobPage 合并到 `pages/Workspace.tsx`，按状态 A/B/C 渲染 | 新文件 + 删 `HomePage.tsx`、`JobPage.tsx` |
| 6 | 删除高级选项、邮件勾选、确认按钮、字幕编辑入口 | 删 `OptionsForm.tsx`，删 `TranscriptView.tsx` 入口（组件可暂留以防回滚） |
| 7 | 新 `JobProgress`：紧凑时间线版 | 改写 `web/src/components/JobProgress.tsx` |
| 8 | `HistoryDrawer` + 浮动入口；删 `/history` 路由 | 新文件 + 删 `HistoryPage.tsx` |
| 9 | localStorage + `?j=` 状态恢复 | `Workspace.tsx`, 新 `hooks/useActiveJob.ts` |
| 10 | 动画过渡（CSS / framer-motion 二选一） | 同上 |
| 11 | 文案替换（H1、按钮、toast、空状态） | 全局搜 |
| 12 | 清理 `useShortcuts` 里已经不存在的快捷键（Cmd+. 取消等） | `hooks/useShortcuts.ts`, `App.tsx`（快捷键弹窗） |

---

## 9. 取舍记录（明确「不做」）

- ❌ 任务页字幕逐句编辑（`TranscriptView` 入口）—— 低频，先收。
- ❌ 高级选项面板 —— 走默认。
- ❌ `/history` 独立页 —— 抽屉就够。
- ❌ 主题三态按钮 —— 跟系统。
- ❌ 「仅下载音频」首页按钮 —— 完成后再下。
- ❌ 「强制 ASR / 重新转写」按钮 —— 隐藏，下次再说。
- ❌ 模型选择 / API key 输入 —— 走 `.env`，前端零交互。
- ❌ 快捷键说明弹窗（`?` 打开那个）—— 砍掉，留两个核心（Cmd+V、Cmd+Enter），不再提示。

---

## 10. 实施顺序（建议三轮 commit）

**Round 1 · 视觉与文案**（不动逻辑，UI 改完先看效果）
- step 1（主题）、step 11（文案）、step 4（去顶栏）

**Round 2 · 单页流**（核心交互）
- step 5（Workspace）、step 6（删选项/邮件勾选）、step 7（进度时间线）、step 10（动画）

**Round 3 · 状态与边角**
- step 9（恢复）、step 8（历史抽屉）、step 2 + 3（URL 兼容）、step 12（清理快捷键）

每轮跑一遍：粘贴一个新链接 / 中途刷新 / 关掉再回来 / 直接打开 `/?j=<id>` / 历史抽屉里点恢复，五条路径都过。

---

## 11. 已确认

1. 主题色：**樱红 `#E26A8D`**（Sakura-on-Washi，按第 0.1 节配色落地）。
2. 输入框上方描述：**「一条 B 站链接，要約 + 邮件，一次搞定」**。
3. 邮箱：**永远跟后端默认走，前端零交互**。
4. 要約产物：**流式增量**展示（接 SSE token 事件）。
