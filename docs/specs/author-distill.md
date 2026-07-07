# 作者蒸馏语料（author-distill）

状态：已批准（2026-07-07）。跨会话执行以本 spec 为准，进度见 `docs/author-distill-status.md`。

## 目标与边界

一键为某 UP 主生成「蒸馏语料包」：抓取动态 + 补齐投稿转写 → 逐视频观点提取 +
动态批量清洗 → 组装为 `data/distill/<mid>/` 目录。**本项目到语料包为止**，
蒸馏 skill（SKILL.md 人物化）在项目外生成，不在范围内。

Not building：SKILL.md 生成、蒸馏链路的邮件通知、批评者视角补充搜索、
现有笔记总结行为的改动（除 prompts 的两行增益性原则）。

## 关键决策

1. **分层 map-reduce**：视频逐个提取（转写超上下文 + 可断点续跑）；动态按批
   （约 50 条/批）清洗、保留有观点动态的**原文**不改写；末端只组装不做有损压缩
   （压缩是项目外蒸馏阶段的职责）。
2. **复用转写、不复用笔记总结**：成本大头是 ASR 而非 LLM。已完成 job 的
   `transcript_json` 直接复用，观点提取用蒸馏专用 prompt 重跑一次；
   笔记式总结目标不同（操作步骤 vs 观点密度），不作语料。
3. **数据隔离**：新表 `distill_runs` + 独立目录 `data/distill/<mid>/`，
   不动现有 jobs 表结构与 summaries 存储。蒸馏建的 job 用
   `task_type="distill"`，主历史列表过滤、不产笔记、不发邮件。
4. **去无用信息靠 prompt 不靠规则**：提取 prompt 明确忽略广告口播/商单/
   抽奖/平台套话；需区分「插播恰饭」与「视频主题本身是评测」。
5. **从严默认**：视频上限默认 50（UI 可改）；动态默认近 2 年、上限 1000 条，
   串行翻页带间隔。防「一键跑两天 + 账号风控」。

## 接口与数据形态

- 动态抓取：`GET /x/polymer/web-dynamic/v1/feed/space`（WBI 签名 + cookie/
  buvid/w_webid 风控热身，复用 `wbi.py` 与 space.py 提取出的 `_guard.py`）。
  解析 `DYNAMIC_TYPE_AV/WORD/DRAW/FORWARD/ARTICLE` 为统一结构
  `{type, text, bvid?, ts}`。路由 `GET /v1/up/{mid}/dynamics`。
- 蒸馏 API：`POST /v1/up/{mid}/distill`（video_limit 默认 50）、状态查询、
  SSE 进度、结果读取。重启后按 manifest 断点续跑。
- 产物目录：
  ```
  data/distill/<mid>/
    manifest.json      # 作者信息、数量、时间范围、各步状态（断点续跑依据）
    videos/<bvid>.md   # 每视频观点提取（frontmatter：标题/日期/播放量）
    dynamics.md        # 清洗后动态，按时间线、带类型标注
    corpus.md          # 组装后的单文件语料包
  ```
- 提取输出固定四节：观点与立场（附支撑原话）/ 思维方式 / 价值倾向 /
  低观点密度标记（纯教程类降权用）。
- prompts 位置：`modules/llm/distill_prompts.py`（DISTILL_EXTRACT_PROMPT、
  DISTILL_EXTRACT_MERGE_PROMPT、DYNAMICS_CLEAN_PROMPT），与笔记 prompts 分离。

## 错误与降级

- 动态接口失败（-352/-799/-509 重试后仍失败）：不中断 run，manifest 标注
  `dynamics: unavailable`，继续纯视频语料。
- 单视频转写/提取失败：记入 manifest 的 failed 列表，继续其余视频。
- 未指明的边缘情况一律取更严格行为（限速、跳过而非重试风暴）。

## 分步与验证

| Step | 内容 | 验证 |
|---|---|---|
| 1 | 笔记 prompt 加两行原则（跳过插播恰饭；保留作者立场） | 真实视频对比 + pytest/ruff |
| 2 | `_guard.py` 提取 + `dynamic.py` + dynamics 路由 | 真实 mid 翻页/匿名/-352 恢复 + 回归 |
| 3 | distill 包 + distill_prompts + 迁移 + 路由 + 续跑 | 小体量作者端到端（含复用与重启续跑） |
| 4 | UpPage 蒸馏按钮/弹窗/SSE 进度/结果预览 | tsc + build + 浏览器端到端 |

每步独立可合并；回滚 = 还原两行 prompt / 删新增文件与新表。
