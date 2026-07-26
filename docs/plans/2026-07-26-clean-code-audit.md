# 2026-07-26 Clean Code 审计与渐进改进

## 背景

在不改变产品功能和线上部署的前提下，对服务端、前端、脚本和测试进行全面审计。工作以可复现证据为准：先建立基线、识别确定性问题与可测量瓶颈，再按低风险批次实施必要的修复、性能优化和模块解耦。

## 目标

- 识别并修复确定性的代码缺陷。
- 测量关键路径性能，并仅实施有测量依据的优化。
- 在不改变行为的前提下，适度降低低风险模块间耦合。
- 补足与本次变更直接相关的测试和文档，并由独立 QA 验证。

## 范围与排除项

### 覆盖范围

- 服务端实现、路由、领域逻辑、配置与数据访问边界。
- 前端页面、组件、请求状态与构建配置。
- 维护/开发脚本及其调用约定。
- 自动化测试、测试辅助代码与现有覆盖缺口。

### 明确排除

- 线上部署、域名、Tunnel、运行环境或其他基础设施变更。
- 产品功能、接口语义或交互设计变化。
- 没有证据支持的大规模重构、格式化或依赖升级。
- 未经明确授权的 commit 或 push。

## 执行步骤

1. [x] 建立基线：记录当前 Git 状态、可用验证命令、测试结果、构建结果和关键路径的初始性能数据。
2. [x] 四路只读审计：分别审查服务端、前端、脚本、测试，记录问题证据、复现条件、风险和候选改进。
3. [x] 汇总并分级：将发现按 P0–P3 分类，区分确定性 bug、可测量性能问题、低风险解耦机会和仅供后续跟踪的建议。
4. [x] Batch 1 — 确定性 bug：为已复现的 P0/P1 缺陷补回归测试并实施最小修复。
5. [x] Batch 2 — 可测量性能：在相同测量方法下验证瓶颈，实施有明确收益的最小优化并比较前后数据。
6. [x] Batch 3 — 低风险解耦：仅处理行为保持不变、边界清晰且有测试保护的耦合点。
7. [x] Batch 4 — 测试与文档：补齐本次变更的测试、必要的开发文档和维护说明。
8. [x] 独立 QA：运行适用的测试、类型检查、lint、构建和性能复测；将失败项按新问题或既有问题分别记录。
9. [x] 最终 review：检查变更范围、逻辑正确性、回归风险、性能结论和文档完整性；在下方追加审查结论与根因。

## 成功标准

- 每个已修复缺陷均有可复现的故障证据或回归测试，并通过修复后验证。
- 性能改动具有同方法、同场景的前后测量数据；无数据支撑的优化不合入。
- 解耦改动不改变对外行为，且由现有或新增测试覆盖。
- 适用的项目验证命令通过；无法运行或既有失败项被明确隔离说明。
- 改动仅限于本计划范围，不包含部署、产品功能或未经授权的 Git 发布操作。

## 风险与边界

- 审计可能发现依赖上游服务、运行数据或外部环境的非确定性问题；此类问题只记录证据，不将猜测性改动混入批次。
- 性能数据容易受缓存、网络和机器负载影响；需记录测量命令、样本和环境，并避免单次偶然结果驱动设计。
- 模块解耦可能扩大回归面；仅在边界、行为和测试均清晰时实施，其他候选项保留为建议。
- 不覆盖其他代理或用户已有改动；每次批次前后检查工作树并将无关差异排除在本次范围外。
- 不在代码、日志、测试输出或文档中泄露 Cookie、令牌或其他敏感凭据。

## 预期受影响文件

待四路审计、问题分级和各批次范围确认后补充。仅列入与已证实问题、已测量瓶颈或已确认低风险解耦直接相关的文件。

## 实施备注

待实施后追加，保留上述原始计划不改写；记录实际变更、测量结果、验证结果和任何偏离及其理由。

## 审查 / 问题与根因

待最终 review 后追加；记录审查发现、根因、修复或不处理的裁决，以及遗留风险。

## 基线与审计结果（2026-07-26）

### 已完成基线

- 服务端测试在清除代理环境后通过：`144 passed`。
- Ruff 检查通过。
- Web 构建通过。
- 保持默认代理环境时，LLM 相关测试因 `socksio` 失败；该项记录为环境依赖问题，不作为本轮代码缺陷。
- 当前审计未发现 P0。

### 已审计关键文件

- 服务端入口、配置与安全边界：`server/biri_youyaku/app.py`、`config.py`、`logging.py`、`llm_url.py`、`db.py`、`routes/config.py`、`routes/distill.py`、`routes/jobs.py`、`routes/up.py`。
- 作业、生命周期与事件：`jobs/runner.py`、`jobs/pipeline.py`、`jobs/cleanup.py`、`jobs/repo.py`、`jobs/model.py`、`events.py`。
- LLM、ASR 与蒸馏存储：`modules/llm/client.py`、`modules/llm/distill.py`、`modules/asr/__init__.py`、`modules/asr/whisper.py`、`modules/storage/distill.py`、`distill/repo.py`、`distill/orchestrator.py`。
- 前端请求与页面状态：`web/src/lib/api.ts`、`web/src/lib/runtimeConfig.ts`、`web/src/pages/up/UpList.tsx`、`web/src/pages/HistoryPage.tsx`、`web/src/pages/UpPage.tsx`、`web/src/hooks/useJob.ts`、`web/src/hooks/useJobStream.ts`。
- 对应回归/行为测试：`server/tests/test_llm_client.py`、`test_runner_pause.py`、`test_runner_await_completion.py`、`test_cleanup.py`、`test_events.py`、`test_config_and_audio_routes.py`、`test_job_options.py`、`test_distill_repo.py`、`test_asr_backend.py`。

### 已确认批次范围

以下为审计后的实际执行顺序；保留原执行步骤作为初始计划记录。

1. **Batch 1 — correctness/security（P1）**：SSRF 的 canonical URL 校验、API key 日志泄露、SQLite maintenance 共享连接、`video_limit`/配置边界、前端 `UpList`/`History` 竞态，以及 API 错误解析。
2. **Batch 2 — lifecycle/events（P1）**：runner/distill 的 shutdown 与 recovery 语义、cleanup 对 terminal 状态的反转，以及 SSE subscriber 阻塞。
3. **Batch 3 — measured performance**：LLM stream batching、ASR loader single-flight、原子化 distill 写入。Stats endpoint 仅在完成测量且确认瓶颈后决定是否处理。
4. **Batch 4 — moderate decoupling**：只评估 LLM gateway、media model 和 runtime public hooks；仅在前述批次通过后决定，避免架构重写。

### 延后项与高风险边界

- `to_thread` 的真正终止需要进程化设计；本轮不做表面“可取消”修复。
- trusted proxy 同时涉及部署网络拓扑；不在本轮业务代码中盲改。
- a11y 为 P2，可在前端批次中以低风险方式纳入。

## Implementation notes（2026-07-26）

- 完成防 SSRF 的 canonical URL 校验、日志脱敏、输入/配置约束、SQLite 独立 maintenance 连接及 distill 原子写。
- 前端修复请求竞态、API 错误解析，并统一 Dialog/Toast 反馈。
- jobs/distill 增加 CAS 与生命周期语义：停止接单、bounded drain、owner 复用及邮件投递未知状态处理；SSE 改为非阻塞。
- LLM 真实流式输出在 100ms 或 256 字符触发 flush；ASR loader 使用 single-flight；deferred client close 以 generation 与 completion shield 保护。
- 解耦仅公开 runtime hooks 与 `_cache` helper；未引入 LLM gateway 或 media model 重构。

## Deviations

- 原计划的“可测量性能”未扩展为 stats endpoint 改造：未形成可重复的真实基线，因此只保留已验证的流式与 single-flight 改进。
- 中等解耦限于低风险边界；LLM gateway 与 media model 继续延期，避免扩大回归面。

## Review issues and root causes

- 焦点被 Dialog 抢占：关闭/切换流程未保护焦点所有权；已修复。
- `confirmDisabled` 残留：异步确认状态未在所有退出路径复位；已修复。
- job status 残留：终态与清理路径的状态写入不完整；已修复。
- 取消 `to_thread` 的假恢复：取消无法终止底层线程；已改为诚实的生命周期处理并延期真正终止。
- distill 取消、重复执行与 owner 冲突：缺少 CAS、终态和 owner 复用约束；已修复。
- completion Future 取消传播：共享 completion 未被 shield；已修复。

## Validation

- 清除代理环境后服务端测试：`195 passed in 0.69s`。
- Ruff 通过；web build 通过（`1812 modules`）；`git diff --check` 通过。
- 当前代理环境下 LLM 因缺少 `socksio` 失败，归为环境依赖，非本轮代码回归。

## Deferred risks

- [ ] `to_thread` 的真正终止（需进程化或等价的可中断执行设计）。
- [ ] trusted proxy（依赖实际部署网络拓扑）。
- [ ] stats endpoint 的真实性能基线。
- [ ] LLM SOCKS 依赖的运行环境补齐。
