# biri-youyaku 增强方案（5 项评估 + step by step）

> 结论先行：1/2/3 都值得做且不大；4 可做但**因供应商而异**，只对少数厂商可行；
> 5 可做且数据现成（前端纯算即可），建议先做「热力图 + 周对比」，手绘风作为可选皮肤。
> 推荐落地顺序：① 滚动条 → ③ 筛选交互 → ② 文案（三个纯打磨、快）→ ⑤ 统计页 → ④ 余额（卡片塞进统计页顶部）。

---

## ① 统一滚动条样式（P0 · 小）

**评估**：目前零自定义滚动条，用系统默认，和暖纸+墨蓝的主题不搭；多个内滚容器
（字幕原文、脑图、笔记 TOC、历史长列表）观感不一致。值得统一。

**形式**：全局 CSS（`web/src/styles.css`），用主题色变量画细圆角滚动条，跟随明暗模式。

**步骤**
1. 在 `styles.css` 加全局规则：
   - WebKit：`::-webkit-scrollbar{width/height:8px}`、`::-webkit-scrollbar-thumb{圆角 + bg 用 --color-line，hover 加深}`、`track 透明`。
   - Firefox：`* { scrollbar-width: thin; scrollbar-color: var(--color-line) transparent }`。
   - 暗色模式下 thumb 用更亮一档（已有 `--color-*` 变量，直接复用）。
2. 移动端可保持系统默认（细滚动条在触屏意义不大）——用 `@media (pointer:fine)` 限定。

**工作量**：~15 行 CSS。零风险。

---

## ② 横向滚动筛选交互（P1 · 小）—— item 3

**评估**：`HistoryPage` 的作者行、标签行用 `overflow-x-auto` 横向滚动。问题：
没有可见滚动条→不可发现、看不全、触控板/鼠标横滚都别扭；标签多时尤其差。

**形式（推荐 A，备选 B）**
- **A. 收起为「可展开的换行区」**：默认 `flex-wrap` 只显示约 1.5 行（`max-h` + 渐隐），
  底部一个「展开全部 / 收起」。优点：能一眼看全、不依赖横滚、改动小。
- **B. 收进「筛选」弹层**：作者/标签各做一个带搜索框的下拉 popover，按钮显示当前选中。
  优点：再多也不挤版面；缺点：多一层点击、要写 popover。

> 个人维护、作者/标签量级中等 → 选 **A**。两行筛选（作者 + 标签）统一成一个
> 「换行 + 展开」组件，复用同一套 chip 样式。

**步骤（方案 A）**
1. 抽一个 `<ChipFilter label items selected onSelect />` 组件：`flex flex-wrap`，
   外层 `max-h-[4.5rem] overflow-hidden`（折叠态）+ 底部渐隐；展开后 `max-h-none`。
2. 右侧/下方「展开全部（N）/ 收起」按钮，`useState(expanded)`。
3. `HistoryPage` 的作者行、标签行都换成它；去掉 `-mx-4 overflow-x-auto`。
4. UpPage 的排序/筛选保持（那几个少，不需要）。

**工作量**：1 个小组件 + 接 2 处。

---

## ③ 文案统一排查（P1 · 中）

**评估**：扫了一遍 UI 文案，存在几类不一致，值得统一成一套「简洁、口语、标点统一」的风格：
- **术语**：「总结 / 摘要」混用（README 用"摘要"，UI 多用"总结"）；「投稿 / 稿件 / 视频」混用；「UP 主 / 作者」混用。
- **标点**：中文引号「」与英文 ' '、省略号 `…` vs `...` 不统一。
- **Toast 语气**：「已开始 / 已复制 / 已删除」简洁；但「这条之前总结过，已为你打开」「这条之前总结过，已复用」两处措辞不一致。
- **错误文案**：有的「请重试」、有的「请稍后再试」、有的「换个链接试试」。

**形式**：定一份「文案规范」（术语表 + 标点规则），然后逐文件改。不引入 i18n 框架（过度）。

**步骤**
1. 定规范（建议）：统一用**「总结」**（动词/名词都用它，README 的"摘要"也改"总结"以一致）；
   统一**「UP 主」「投稿」**；引号统一中文「」；省略号统一 `…`；
   动作完成 toast 用「已 X」；可重试错误统一「请稍后重试」。
2. 集中盘点：`grep` 出所有面向用户的字符串（toast / label / placeholder / 错误），列差异 → 批量改。
3. 重点文件：`Workspace.tsx`、`pages/workspace/*`、`HistoryPage.tsx`、`UpPage.tsx`、
   `errorMap.ts`、`ToastProvider` 调用点、`steps.tsx`。
4. README/CONFIG 里的术语跟着统一一遍。

**工作量**：盘点 + 改，半天内。无逻辑风险（纯字符串）。

---

## ④ 展示 API Key 余额（P2 · 中）—— item 4

**评估**：余额查询**没有通用标准**，必须按供应商各写各的。已知支持「用 API Key 直接 GET 余额」的：

| 供应商 | 端点（**实现前请对最新官方文档核对**） | 返回（大意） | 币种 |
| --- | --- | --- | --- |
| **DeepSeek**（默认，最该做） | `GET https://api.deepseek.com/user/balance` | `balance_infos[].total_balance` | CNY |
| Moonshot / Kimi | `GET https://api.moonshot.cn/v1/users/me/balance` | `data.available_balance` | CNY |
| SiliconFlow | `GET https://api.siliconflow.cn/v1/user/info` | `data.balance` | CNY |
| OpenRouter | `GET https://openrouter.ai/api/v1/credits` | `total_credits - total_usage` | USD |
| OpenAI / Anthropic / Gemini / 智谱 | ❌ 无「Key 直查余额」的公开端点 | — | — |
| ollama / 本地 | N/A（免费） | — | — |

> 都用同一个 `Authorization: Bearer <key>`，但路径/字段各不同。**OpenAI/Claude/Gemini 查不了**——
> 这些**直接隐藏**余额卡（`supported:false` 时前端什么都不渲染，不占位、不报错）。

**形式**：后端做一个「余额探针」注册表（按 `LLM_BASE_URL` 的 host 匹配供应商→调对应端点→
归一成 `{supported, balance, currency}`）。**放后端**而非前端：key 在服务端、避免 CORS、避免把
余额接口结构暴露给浏览器。新增 `GET /v1/llm/balance`（这次是**真接 UI** 的，不像之前删掉的那些）。

**什么时候刷新**（重要）：余额变化慢、查询要打外网，**不要每次进页面/轮询**。建议：
- 进「统计页」时取一次，**服务端缓存 5 分钟**；
- 一个「↻ 刷新」按钮强制重取；
- **每次任务完成后标记缓存失效**（余额刚减少，下次打开是新值）——可选增强。

**步骤**
1. `modules/llm/balance.py`：`async def fetch_balance(base_url, api_key) -> Balance | None`，
   内部按 host 路由到各 provider 的解析函数；未知供应商返回 `None`。
2. 缓存：`@ttl_lru(maxsize=1, ttl_seconds=300)`（按 key 前缀做 cache key，别把整 key 进日志）。
3. 路由 `GET /v1/llm/balance`（`Depends(require_token)`）→ `{supported: bool, balance?, currency?, provider?}`。
4. 前端 `getLlmBalance()` + 在统计页顶部一个小卡：「DeepSeek 余额 ¥12.34 · ↻」；
   `supported:false` → **整卡隐藏**（不显示「不支持」字样，零占位）。

**工作量**：后端探针 + 1 路由 + 前端 1 卡。DeepSeek 先行，其余按需加。

---

## ⑤ 统计页 / 统计板块（P2 · 中大）—— item 5

**评估**：数据**全部现成**——`GET /v1/jobs` 列表已含 `created_at / completed_at / status /
token_usage / duration / tags / author`。所以统计可**纯前端**算（拉全量 jobs，单用户量级 OK），
无需新后端端点。

**形式（建议组合）**
- **GitHub 风热力图**：按天统计「完成的总结数」，最近 ~26 周，7×N 方格、深浅分级。纯 SVG，无依赖。
- **周对比卡**：本周 vs 上周——总结数 / 总 tokens / 估算花费（复用 `estimateCostCny` 价格表）/ 视频总时长 / Top 标签。
- **柱状图**：最近 8–12 周每周总结数（或 tokens）。纯 SVG 即可。
- **手绘风（可选皮肤）**：用 `rough.js`（轻）或 `roughViz` 给柱状图/折线加手绘质感，类似 star-history 那种。
  代价：多一个依赖（rough.js ~9KB）。建议**先上规整 SVG 版**，手绘作为开关或后续皮肤。
- **以周维度的总结**：周对比卡即是；可再加「本周关键词」（聚合本周 tags 出现次数 Top N）。
- **样式适配项目（重点）**：所有图表用项目色板（`--color-brand / brandSoft / line / panel / ink / muted`）、
  圆角卡（`rounded-3xl bg-panel shadow-card`）；热力图深浅用 brand 的不透明度阶梯；跟随明暗模式
  （复用现有 CSS 变量，不写死颜色）；和 DoneView / 历史页同一套视觉语言；base 版纯 SVG、不引重型图表库。

**放哪**：新路由 `/stats`，从首页/历史页加入口；余额卡（④）也放这页顶部。

**步骤**
1. `lib/stats.ts`：输入 jobs[]，输出 `{ heatmap: {date,count}[], weekly: {...}, byWeek: {week,count,tokens}[], topTags }`。复用 `format.ts` 的成本/时长。
2. `components/Heatmap.tsx`（SVG 方格 + 月份标 + hover tooltip）、`components/WeekBars.tsx`（SVG 柱）。
3. `pages/StatsPage.tsx`：进页拉全量 jobs（复用 HistoryPage 的分页 loop）→ 算 → 渲染热力图 + 周对比卡 + 柱状图 +（顶部）余额卡。
4. `App.tsx` 加 `/stats` 路由 + 首页/历史页入口按钮。
5. （可选）`rough.js` 手绘皮肤开关。

**工作量**：stats 计算 + 2 个 SVG 组件 + 1 页 + 路由。中等；纯前端、零后端改动（除非 ④ 的余额）。

---

## 总览与建议

| # | 事项 | 可行 | 形式 | 量 |
| --- | --- | --- | --- | --- |
| 1 | 滚动条统一 | ✅ | 全局 CSS | 小 |
| 2 | 文案统一 | ✅ | 文案规范 + 逐文件改 | 中 |
| 3 | 筛选交互 | ✅ | 换行+展开组件（备选 popover） | 小 |
| 4 | 余额展示 | ⚠️ 按供应商 | 后端探针 + `/v1/llm/balance` + 统计页卡片 | 中（DeepSeek 先行） |
| 5 | 统计页 | ✅ | 纯前端：热力图 + 周对比 + 柱状（手绘可选） | 中大 |

**建议落地顺序**：① 滚动条 → ③ 筛选 → ② 文案（这三个是纯打磨、快）→ ⑤ 统计页（搭好 `/stats`）→ ④ 余额（卡片塞进统计页顶部）。
