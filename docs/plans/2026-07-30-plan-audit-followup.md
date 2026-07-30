# 2026-07-30 Plan Audit Follow-up

> 本文件是本轮工作的 source of truth。开始时的工作区基线：`docs/plans/2026-07-30-knowledge-eval-gates.md` 已有用户修改（`git status --short` 为 ` M`）；该文件只作为基线记录，绝不修改、覆盖或纳入本轮改动。

## 目标与边界

修复已确认的两个前端可访问性/状态文案问题，并使仓库文档与已经发生的实现、验证和提交事实一致；完成定向自动化与浏览器验收。

本轮明确不做：trusted proxy、`to_thread` 进程化、真实账单导入、production holdout、OCR/上传、Docker 部署。

## 执行计划

1. [x] **Batch 0 — 基线（fast-worker）**
   - 记录 Git 工作区、相关前端实现、现有测试与文档现状；不触碰用户已有的 `2026-07-30-knowledge-eval-gates.md` 修改。
   - 受影响文件：仅检查相关文件与本计划。
   - 验证边界：记录可复现的静态/测试基线；不把浏览器或真实账户验收表述为已完成。

2. [x] **Batch 1 — 确定性前端修复与最小回归（fast-worker）**
   - 删除 `DistillButton` 对抓取历史动态的错误承诺，使其准确描述 video-only 投稿处理。
   - 为 `WeekNavigator` 补齐 `prefers-reduced-motion` 行为。
   - 新增或调整仅覆盖上述行为的最小回归测试。
   - 预期受影响文件：`web/src/` 下的 `DistillButton`、`WeekNavigator` 及其相邻测试文件（以实际仓库路径为准）。
   - 风险：文案调整不得误导用户为已支持抓取历史；动画修改可能影响正常动效；保持现有交互与非 reduced-motion 路径不变。
   - 成功标准：文案准确限定 video-only 投稿处理；reduced-motion 下不播放不必要动画；新增定向测试稳定通过。

3. [x] **Batch 2 — 文档与历史事实对齐（fast-worker）**
   - 同步 README 的 balance-only 表述。
   - 将 `enhancement-plan` 标明为 archived/superseded。
   - 将动画的真实提交号更新为 `9381050`。
   - 消除历史费用复合 checkbox 与浏览器验证记录之间的矛盾。
   - 移除或替换 server `Dockerfile` 相关说明中已取消的 cloud-cutover 语境。
   - 预期受影响文件：`README.md`、enhancement plan、历史费用/验证记录、server `Dockerfile` 或其紧邻文档说明（以实际仓库路径为准）。
   - 风险：历史记录必须保留事实与时间边界，不将未执行的生产、账单或浏览器验收写成已完成。
   - 成功标准：所有上述声明相互一致；无新增部署、账单导入或生产 holdout 承诺。

4. [x] **Batch 2.5 — Knowledge search correctness bugs（fast-worker；qa-runner 验证）**
   - 这是用户“发现 bug 可顺手修”授权下、经 deep-reasoner 复核后追加的 isolated batch；仅修复下列已确认的 knowledge search 正确性问题。
   - `reconcile` 固定取 latest 200 后再过滤，导致旧 pending 条目永久饿死。
   - summary/transcript index 固定取 latest 100 后再过滤，导致旧的缺 chunk 条目永久饿死。
   - `missing_bvid_or_cid` 达到 retry 上限后，即使 metadata 后续补齐也无法恢复处理。
   - 当 `retrieve` 的 `limit <= 6` 时，summary 结果会挤掉 transcript 结果。
   - 受影响文件：knowledge reconcile/index/retrieve 实现与其最小相邻测试文件（以实际仓库路径为准）。
   - 实现边界：SQL/扫描必须先选择可处理或缺失候选再施加限额，并保留实际处理预算；metadata 合法后仅对 `missing_bvid_or_cid` 原因安全恢复；若有 transcript hit，至少保留一个槽位且总数不超过 `limit`。
   - 明确不做 Chat 实际引用协议；该协议仅登记为 `knowledge_chat_enabled` 之前的 Gate。
   - 成功标准：分别新增并通过覆盖 >200、>100、retry 恢复和 `limit=6` 的回归测试；qa-runner 独立验证定向测试与边界。

5. [x] **Batch 3 — 浏览器验收与确定性 UI 修补（qa-runner / fast-worker）**
   - 在桌面、移动、键盘操作与 reduced-motion 条件下验收受影响 UI。
   - qa-runner 负责验收；仅在发现可稳定复现且与本轮范围直接相关的 UI bug 时，交由 fast-worker 修复并复测；其余发现记录而不扩展范围。
   - 受影响文件：仅限 Batch 1 组件/测试或确认的直接 UI bug 文件。
   - 验证边界：浏览器验收覆盖视觉、交互和键盘路径；不替代真实用户、真实账单或生产环境验收。
   - 成功标准：四种验收条件均通过，或将无法完成的条件与证据明确记录。

6. [x] **Batch 4 — 定向验证与最终审查（qa-runner）**
   - 运行受影响前端/服务端的定向测试与 Web build，并进行最终 diff、文档一致性及回归风险审查。
   - 验证边界：qa-runner 报告实际执行命令及 pass/fail；未运行的全量或生产验证明确排除。
   - 成功标准：定向测试和 Web build 通过，`git diff --check` 无输出，且审查未发现本轮引入的阻断问题。

## 委派与验证责任

- fast-worker：执行 Batch 0–2 的范围内检查、实现与文档更新；仅在 Batch 3 发现确定性直接 UI bug 时修复并配合复测；不得还原或覆盖其他协作者修改。
- fast-worker：执行 Batch 2.5 的 isolated knowledge correctness 修复与最小回归测试；不得实现 Chat 实际引用协议。
- qa-runner：验证 Batch 2.5 的定向测试与边界，执行 Batch 3 浏览器验收，以及 Batch 4 的测试/build/变更审查，输出命令、结果与未覆盖边界。
- orchestrator：按 batch 汇总结果，确认范围未扩张，并在验证通过后交付；不提交、推送或部署，除非用户另行明确授权。

## 实施备注

- **Batch 0 baseline（2026-07-30）**：`HEAD` 与 `origin/main` 均为 `36aa6a8`；现有用户修改为 `docs/plans/2026-07-30-knowledge-eval-gates.md`；本计划文件为 untracked；未运行测试。
- **Batch 1 implementation（2026-07-30）**：将蒸馏确认文案收窄为该 UP 的投稿视频与可用字幕处理、转写补齐和语料包生成，不再承诺抓取历史动态；`WeekNavigator` 复用 `scroll.ts` 的 reduced-motion 滚动行为，正常为 `smooth`、系统要求减弱动态时为 `auto`。仓库原本没有前端测试栈，故以 Node 内置测试新增两个源码回归断言，分别覆盖文案范围及 shared helper 的 `smooth`/`auto` 两分支接入，避免为两个断言引入测试依赖；未修改 `2026-07-30-knowledge-eval-gates.md`。`npm ci && npm test` 通过（2/2），`npm run build` 通过；本批文件的 diff 检查通过。全工作区 diff 检查仍会报告用户既有 `knowledge-eval-gates.md` 的 trailing whitespace，未修改该文件。
- **Batch 2 implementation（2026-07-30）**：将中英文 README 与架构图收窄为当前历史页展示 API 余额与周报，不对 Token/费用数据能力作删除性表述；将旧 `enhancement-plan` 标为 archived/superseded 并指向 README 与当前历史/用量计划；动画计划提交号更正为 `9381050`，并记录本轮 `WeekNavigator` reduced-motion 回归修复。历史费用计划原始步骤和勾选保持不改，末尾补充 OpenRouter `usage.cost` 已完成、DeepSeek/其他官方账单导入和浏览器/真实账号验收未完成的边界；更新 Docker 注释与知识库 fixture 的 `--extra dev` pytest 命令。未修改 `2026-07-30-knowledge-eval-gates.md`。
- **Batch 2.5 implementation（2026-07-30）**：`reconcile` SQL 先筛选真实候选再 `LIMIT 50`；summary/transcript index 先筛选缺 chunk 候选、使用 latest revision，再 `LIMIT 100`；metadata repair 仅对 `missing_bvid_or_cid` 在 metadata 合法后安全恢复；`retrieve` 有 transcript hit 时至少保留一个槽位，且结果总数不超过 `limit`。worker 验证：registry + transcript 定向测试 26 passed、retrieval 单独测试 13 passed、Ruff 通过；最终 QA 仍会复跑。
- **Batch 3 browser acceptance（2026-07-30）**：按计划允许 blocked 有证据，已完成当前可执行验收。安全进程环境传入 token，未写入 `.env`；5173/history 无加载错误；空态、筛选展开、键盘焦点和 API 200 通过。BLOCKED：无数据，无法验证周导航、长标题与 `DistillButton`；Browser 无 viewport/reduced-motion emulation，无法验证移动与真实 scroll 行为。源码回归测试已覆盖接入，但不替代浏览器验收。最初 401 根因是 Vite 未获得 API token，不是产品 bug；3000 为 tsuzuri，未触碰；临时进程已停止。
- **Batch 4 QA（2026-07-30）**：独立 QA 实际结果：Web `npm test` 2/2 与 `npm run build` 均 PASS；server registry + transcript 26 passed；已修改 Python 文件 Ruff PASS；本轮定向 diff check PASS。无 `.env`、secret 或 lockfile 意外修改，文档关键词一致。全工作区 `git diff --check` 唯一失败为用户基线 `docs/plans/2026-07-30-knowledge-eval-gates.md:32` trailing whitespace，按边界未修改；因此成功标准按“本轮文件无问题，既有用户改动例外”完成。

## Review issues / root causes

- Chat citations 当前为 retrieval hits 而非实际引用；在 `knowledge_chat_enabled` 前必须改名或实现结构化引用。当前默认关闭，故本轮不做。
- 浏览器移动、reduced-motion、真实数据下的长标题、`WeekNavigator` 与 `DistillButton` 仍未验收。
- `retrieve(limit=0)` 的既有实现因 `limit or 10` 采用默认 10；本轮未改变，API 正常调用具有 `>= 1` 限制。若未来开放低层调用，需明确其语义。
- 无阻断 review 问题。
