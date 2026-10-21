# 笔哩 · 搜索与阅读重构 v2

日期：2026-10-21。基线 `b7b19a8`。本目录是设计提案和独立原型，没有改动业务代码。示例数据全部虚构。

- `index.html`：评审入口，左侧切场景，桌面和手机并排，可切深浅色
- `prototype.html`：可交互原型（单文件）
- `logo.html`：图标方案（4 个，全部左右对称）

## 1. 结论（相对 v1 的调整）

| v1（GPT 方案） | v2 |
| --- | --- |
| 蓝灰后台风格，丢掉樱红和兔子 | 保留和纸米底 + 樱红强调色；新图标从「笔」出发重画 |
| 三个一级入口：资料库 / 新建笔记 / 任务 | 一个输入框：粘贴链接 = 生成笔记，输入文字 = 搜索。顶栏只有「笔记」「任务」 |
| 任务是常驻一级页 | 进行中 / 失败的任务以条带出现在列表上方，顶栏徽标提示；任务列表保留但不抢主位 |
| 范围下拉 4 项 + 排序下拉 | 分段按钮「全部 / 笔记 / 字幕」，带命中数；有关键词按相关度，无关键词按时间，不给排序开关 |
| 卡片里套卡片再套色块 | 列表和结果都是平铺行 + 分隔线；命中片段用左侧「来源列」区分笔记 / 字幕 |
| 按钮各写各的 className | 一个 Button 组件：primary / secondary / ghost × md / sm，宽度跟随文字，一个区域最多一个 primary |

### 页面与路由

```text
/                       笔记列表（?up= ?tag= 筛选）
/search?q=&scope=       搜索结果，scope ∈ all | notes | subs
/doc/:id?tab=&at=&from= 阅读页；from 决定返回目标（搜索 / UP / 标签 / 任务）
/jobs/:id               任务详情（旧外链继续可用）
/tasks                  任务列表
/trash                  最近删除
/history → /            旧路由重定向
/knowledge?q= → /search?q=
/up/:mid                在线投稿，沿用现有页面
```

返回链接写明返回到哪里（「搜索「注意力」」「慢学实验室 的笔记」），不再根据 `history.length` 判断。查询条件放在 URL 里；滚动位置和已加载的页数按 URL 存进 sessionStorage。

### 删除与恢复

| 场景 | 设计 |
| --- | --- |
| 移除 | 阅读页「⋯ → 从笔记中移除」，弹窗说明会从列表和搜索里消失、30 天内可以恢复、任务记录和 B 站视频不受影响。确认后回到来源页，提示条里可以「撤销」（5 秒） |
| 最近删除 | `/trash`，入口在笔记列表底部，有内容时才出现（「最近删除 · 2 篇」）。每条显示移除日期和剩余天数，3 天内标黄；操作是「恢复」（次要按钮）和「永久删除」（幽灵按钮） |
| 永久删除 | 只出现在「最近删除」和已移除笔记的「⋯」里。弹窗要求输入 BV 号，和后端 `purge` 的 `confirm_title` 校验一致 |
| 打开已移除的笔记 | 仍然可以阅读，顶部提示剩余天数并给出「恢复」按钮 |
| 粘贴已移除视频的链接 | 识别面板写明「这个视频的笔记在最近删除里」，主操作是「恢复笔记」。点「重新生成」也会自动恢复，因为登记时的 upsert 会清掉 `deleted_at` |

不做批量清空：后端没有批量接口，30 天到期会自动清除，单条永久删除已经够用。

## 2. 后端数据结构（从代码读出）

你 Mac mini 上的数据库由同一份 `server/biri_youyaku/db.py` 建表和迁移。启动时 `init_db()` 会用 `ALTER TABLE ADD COLUMN` 补齐缺失的列，所以旧库的表结构和代码一致，只是早期的行会有空列。

```text
jobs                         一次处理；tags_json / duration / mid 只在这里
  └─ knowledge_job_links     job → document（删除历史只解除关联，document 保留）
knowledge_documents          一个视频分 P，唯一键 (provider, bvid, cid)
  ├─ knowledge_summary_revisions  笔记版本，is_active 标记当前版本
  ├─ knowledge_content_revisions  字幕版本
  ├─ knowledge_artifacts          内容寻址的文件（sha256），不可变
  ├─ knowledge_rag_chunks (+fts)  笔记分块：heading_path, chunk_ord
  └─ knowledge_transcript_chunks (+fts)  字幕窗口：start_sec, end_sec
```

**旧数据会自动进库。** `app.py:116` 启动时、`jobs/cleanup.py:457` 每次定时清理时，都会调用 `reconcile_once(limit=50)`，把已完成但还没入库的 summary 任务分批登记，再补建全文索引（`app.py:125`）。以下几类会入不了库：

| 原因（`knowledge_reconcile.reason`） | 处理 |
| --- | --- |
| `summary_file_missing` | summary 文件已不在磁盘上（推测是 `6cb0103` 修复之前被清理掉的），内容已经没了。列表里显示标题，阅读页提示「笔记文件已丢失，可重新生成」 |
| `missing_bvid_or_cid` | 很早的任务没存 cid。列表照常显示，走旧的 job 阅读接口，标「旧版 · 仅支持标题搜索」 |
| `KNOWLEDGE_REGISTER_ENABLED=false` | 整个笔记库退化为基于 jobs 的列表，搜索只查元信息 |

上线前在 Mac mini 上跑一次这条只读 SQL，就知道各类各有多少条：

```sql
SELECT status, COALESCE(reason, ''), COUNT(*) FROM knowledge_reconcile GROUP BY 1, 2;
```

### 需要扩展的地方

1. `knowledge_documents` 加 `tags_json`、`duration`、`tldr` 三列，启动迁移里从仍然存在的 jobs 回填，以后在登记时写入。原因：删除历史之后，标签和时长就只能从 document 上拿。
2. `knowledge_job_links(document_id)` 加索引。目前只有 `job_id` 主键，从 document 反查任务要全表扫。
3. `knowledge_rag_chunks` 加一个可空的 `start_sec` 列（配合第 3 节的 prompt 改动）。这是可以重建的索引表，加列后跑一次 reindex 即可，不需要迁移旧数据。
4. 新接口放在新的 `library` 模块里，不扩大 `/v1/jobs?query=` 的语义，因为批量删除也复用它（`jobs/repo.py:817`）：
   - `GET /v1/library?cursor=&up=&tag=`：列表 = 有效的 documents ∪ 已完成但没有关联 document 的 jobs，按时间倒序，游标分页。
   - `GET /v1/library/search?q=&scope=&cursor=`：按 document 聚合。元信息用 LIKE（几百上千条足够快）；两张全文索引表各执行一条 SQL，用 `GROUP BY document_id` 算命中数，用 `ROW_NUMBER() OVER (PARTITION BY document_id)` 取每篇前 2 条，避免 N+1 查询。排序分层：BV 号精确命中 > 标题命中 > 笔记命中数 > 字幕命中数。哪个索引查询失败，就在 `partial` 字段里标出来，不再吞成空列表（`knowledge/search.py:115`）。
   - `GET /v1/library/documents/:id/content`：返回当前生效的笔记 markdown、字幕片段，以及每个分块的 `chunk_ord`、`heading_path`、`start_sec`。artifact 按内容寻址，可以直接把 `content_hash` 当 ETag，命中缓存就返回 304。
   - `GET /v1/library/trash`：已软删除的 documents，带 `deleted_at` 和到期时间（`deleted_at + KNOWLEDGE_SOFT_DELETE_DAYS`）。移除、恢复、永久删除直接用现有的 `/v1/knowledge/documents/:id/soft-delete`、`/restore`、`/purge`。
5. **修复永久删除后笔记「复活」的问题。** `purge_permanent` 只删除了 `knowledge_job_links`，关联的 job 还是 COMPLETED，summary 文件也还在。`list_reconcilable_completed_jobs` 里的 `r.status = 'registered' AND l.job_id IS NULL` 条件会选中这些 job，下一次 `reconcile_once` 就会把笔记重新登记回来。30 天到期的自动清除也走同一个函数，所以同样会复活。修法：永久删除时，把关联 job 的 `knowledge_reconcile` 状态改成新的 `purged`（并加进上面那条 SQL 的排除列表），同时删除这些 job 的 summary 文件。补一条测试：purge 之后执行一次 reconcile，document 不会再出现。

## 3. 总结 prompt 的优化

看过 `modules/llm/prompts.py` 和 `modules/asr/formatter.py`，新的阅读页和搜索需要这几处改动：

1. **给模型时间戳。** `transcript_to_text` 目前把时间全部丢掉了，所以笔记里的每一节都没法对应到视频的某个时间。改成大约每 30 秒插一个 `[02:15]` 标记（不必每行都插，输入 token 大约多 5%）。同时要求每节标题以开始时间开头：`## 02:15 问题背景`。这样可以做到：
   - 目录点击后能跳到对应的字幕，或者「在 B 站从 02:15 播放」；
   - 搜索命中笔记时，结果里能显示时间。

   长视频分段总结时，传入各段的绝对时间，合并 prompt 要保留这些时间。
2. **结构拍平。** 去掉外层的 `## 笔记`，每一节直接用 `##`。这样分块的 `heading_path` 就是「问题背景」，而不是「笔记 > 问题背景」，目录和搜索结果的来源标签也更干净。
3. **TL;DR 单独存。** 第一行固定写成 `> 一句话`，登记时提取到 `documents.tldr`。列表行和搜索结果可以在标题下多显示一行摘要，这是让列表「一眼看懂」最划算的改动。
4. **术语要能搜到。** 专有名词第一次出现时写成「原文（中文）」，比如「注意力机制（Attention）」，中英文关键词都能搜中。
5. **去掉重复的 prompt。** JSON 版和 Markdown 版的规则一字不差地重复了两遍，合并 prompt 也一样。改成共享的规则片段，再分别加上输出格式部分。如果 JSON 版只剩修复兜底的用途，可以考虑删掉。
6. **兼容旧笔记。** 解析时两种格式都接受：旧格式（`## 笔记` + `###`、没有时间）照常显示，只是不提供跳转；不批量重写旧数据。用户点「重新生成」时，这一篇才升级到新格式。

改完之后，拿 10–20 个真实视频对比新旧两版：时间准不准、节数是否合理、token 增加了多少。

## 4. 性能与 clean code

**前端**
- 新建 `Button`、`Chip`、`Segmented` 三个基础组件，把散落在各页面的长 className 收进去。
- 新建 `useUrlState`，统一读写查询参数。`KnowledgePage` 的查询状态目前存在组件 state 里，离开页面就丢了，这个问题随之解决。
- `HistoryPage.tsx`（547 行）和 `KnowledgePage.tsx` 合并成 `LibraryPage`，下面拆出 `LibraryList`、`SearchResults`、`ResultGroup`。旧的两个页面整体删除，不保留兼容层。
- 搜索只在按 Enter 时提交，不需要防抖。新请求用 `AbortController` 取消旧请求，避免慢请求的结果覆盖新结果。
- 阅读页继续用 `LazyMarkdown` 懒加载。正文按 `content_hash` 缓存；切换笔记 / 字幕标签不重新请求。
- 列表按游标分页，几百条的量不需要虚拟滚动。搜索结果不加入场动画。

**后端**
- 搜索每个索引表只执行一条 SQL，见 2.4。
- 新索引和回填都放进 `init_db` 的幂等迁移里，按批执行，不阻塞启动。
- 新接口独立成 `library/` 模块（router + repo），jobs 和 knowledge 的现有契约都不改。
- 测试：搜索的分层排序、部分失败、未入库 job 的合并、旧格式笔记的解析，各写一组用例。

## 5. 名称与图标

**笔哩**（bǐlī，英文 Bili Notes）。「笔」说明用途，「哩」接上旧名的读音，而且不用「哔」字，离 B 站商标远一点。商标和重名还没有查。

日文没有自然的对应：「哩」在日文里是英里（マイル）的意思；「ビリ」单独使用是「最后一名」。日文场景建议写「ビリノート」或直接用 Bili Notes。

图标定稿为 **B 书里探头**：一只兔子从摊开的笔记本后面探出头，两只爪子扒着书页，意思是笔记里住着一只帮你看视频的兔子。左右对称。`logo.html` 里另外 3 个方向（墨滴兔、吐笔记的小电视、书签兔）保留作对照。

- 两个版本：48px 以上用完整版；32px 及以下（favicon、顶栏、字标）用简化版，去掉爪子和书页横线，眼睛放大、描边加粗。原型顶栏用的是简化版。
- 动画：「一缩一探」用作加载状态；眨眼用作空闲状态。
- 落地时要替换 `web/public/` 下的 `icon.svg`、`favicon.ico`、`apple-touch-icon.png`、`icon-192/512.png`、`maskable-icon*.png` 和 `maskable-icon.svg`。maskable 版要整体缩小到中心 80% 的安全区以内，否则书的下角会被裁掉。
- 改名只改用户能看到的文字：`web/index.html` 的 title、`site.webmanifest` 的 name / short_name、`IdleView.tsx` 的标题。仓库名、Python 包名 `biri_youyaku`、环境变量都不改，改了只有迁移成本，没有收益。

## 6. 实施计划

按依赖关系分 5 步。第 1、2 步互不依赖，可以同时做；每一步单独合并、单独上线。

| 步骤 | 内容 | 依赖 | 完成标准 |
| --- | --- | --- | --- |
| 1. 基础 | `Button` / `Chip` / `Segmented`、`useUrlState`；改名和新图标资源 | 无 | 现有页面都换成新组件，界面没有变化；构建和类型检查通过 |
| 2. 后端 `library` 模块 | 迁移（documents 加三列并回填、`knowledge_job_links(document_id)` 索引）；列表、搜索、正文三个接口；测试 | 无 | 第 4 节列的测试全部通过；在 Mac mini 库的副本上跑一遍迁移，耗时和回填结果符合预期 |
| 3. 前端页面 | `LibraryPage`（列表 + 搜索）、阅读页（查找条、目录、按来源返回）、任务条带、旧路由重定向；删除 `HistoryPage` / `KnowledgePage` | 1、2 | 原型里的各个场景都能用真实数据复现；320px 宽度下没有横向溢出 |
| 4. 总结 prompt | 时间戳、结构拍平、TL;DR、术语写法、合并重复规则；两种格式都能解析；加 `rag_chunks.start_sec` 后 reindex | 后端部分不依赖其他步骤；跳转到时间的界面依赖 3 | 10–20 个视频新旧对比通过；旧笔记显示不变 |
| 5. 删除与恢复 | 修复永久删除后的复活问题（2.5）；`/v1/library/trash`；阅读页的移除、`/trash` 页面、撤销提示条 | 3（复活问题的修复不依赖其他步骤，可以提前做） | 原型里「删除与恢复」的 5 个场景都能复现；永久删除后执行 reconcile，笔记不会重新出现 |

## 7. 还没定下来的事

1. **旧数据还没实测。** 上线前在 Mac mini 上跑第 2 节那条只读 SQL，确认入不了库的旧任务有多少条，再决定要不要做「旧版记录」的兼容显示。
2. **prompt 改动要先评估再上线。** 主要看时间准不准、token 增加多少。
3. **商标和重名还没查。**
4. **不在这次范围内：** 在线 UP 投稿页、设置页沿用现有设计；兔子的表情套图（空状态、出错、加载）等第 3 步做到时再画。

## 8. 验证状态

- `node --check`：`prototype.html`、`logo.html`、`index.html` 的脚本都能通过。
- 在浏览器里实际打开看过：
  - 桌面首页、深色首页、搜索结果；
  - 从搜索进入笔记：命中定位和 ‹ › 跳转正常（2/3）；
  - 手机端从搜索进入字幕：06:18 行高亮，吸顶查找条 2/2；
  - 桌面阅读页：右侧目录和命中标记显示正常；
  - 任务失败页；
  - 删除与恢复：移除 → 撤销、恢复、输入 BV 号后才能永久删除，深色模式下的弹窗；
  - 图标页 4 个新方案，16–96px 都看过；定稿 B 的简化版在 16px、32px 和字标里都清楚。
- 320px 宽度：16 个路由，加上新增的最近删除、已移除笔记、粘贴已移除视频的链接，逐个检查都满足 `scrollWidth = 320`，没有元素溢出。
- 实看中发现并已修复：
  - `hidden` 属性被 `.btn` 的 `display` 覆盖；
  - 窄屏下输入框被按钮挤窄，改成在识别面板里显示「生成笔记」；
  - 失败原因文案前后矛盾，恢复动作改为「重试 / 忽略」；
  - 阅读页查找条加了吸顶，跳转时不再被顶栏遮住；
  - 图标 B 的爪子看起来像眼镜，C 的耳朵像插头，都已重画。
- 没有验证：真实数据和后端接口。原型的数据都是写死的。
