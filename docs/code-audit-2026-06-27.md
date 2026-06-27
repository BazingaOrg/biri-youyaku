# biri-youyaku 代码审查与优化报告

日期：2026-06-27

## 0. 本轮修复状态

已在 2026-06-27 按本报告的高优先级项完成修复：

- 已修复 `resume` / `retry` 的 `llm_base_url` SSRF 校验绕过，并补充回归测试。
- 已同步本地 ollama README 示例，明确本地需清空 `LLM_BASE_URL_ALLOWED_HOSTS`。
- 已收紧邮件 readiness：启用邮件时 `EMAIL_WEBHOOK_URL` / `EMAIL_WEBHOOK_TOKEN` / `EMAIL_DEFAULT_RECIPIENT` 三项都必须配置，后端 runtime、启动 WARN、创建任务早失败和文档口径已一致。
- 已同步 Node 版本：CI 改为 Node 22，和 `.nvmrc` / README 一致。
- 已清理前端 `RuntimeConfig.api_token_required` 历史字段。
- 已把后端 `JobOptionsPayload.task_type` 收窄为 `summary` / `audio`。
- 已在 `CONFIG.md` 补充长视频实际 LLM 并发说明。

仍保留为独立后续任务：

- Vite / esbuild 依赖链升级：这是跨大版本迁移，建议单独做 `chore(web): upgrade vite toolchain`。
- `summary_delta` 流式协议优化：只有长摘要流式性能成为真实痛点时再改协议。

## 1. 审查步骤

1. 读取项目约束：`AGENTS.md`、`README.md`、`CONFIG.md`、`.env.example`、CI workflow。
2. 跑项目级静态信号：`audit_signals.py --root .`。
3. 重点阅读核心路径：
   - 后端任务流：`server/biri_youyaku/jobs/runner.py`
   - 后端持久化：`server/biri_youyaku/jobs/repo.py`、`server/biri_youyaku/db.py`
   - 后端 API：`server/biri_youyaku/routes/jobs.py`、`server/biri_youyaku/routes/config.py`
   - LLM / SSE：`server/biri_youyaku/modules/llm/client.py`、`server/biri_youyaku/events.py`
   - 前端状态流：`web/src/hooks/useJobStream.ts`、`web/src/pages/Workspace.tsx`、`web/src/lib/api.ts`
4. 核对 README 是否简洁、是否与当前实现一致。
5. 跑验证命令：
   - `cd server && uv run ruff check .`
   - `cd server && LLM_API_KEY=dummy-for-tests uv run pytest -q`
   - `cd web && npm run build`
   - `cd web && npm audit --omit=dev --audit-level=moderate`
   - `cd web && npm outdated --long`

## 2. 总体结论

项目整体质量较好，核心流程不是原型代码：任务状态、SSE、SQLite lite 投影、后台清理、LLM client 复用、长视频分段总结、前端流式渲染节流都已经有明确设计。

建议评分：

| 维度 | 分数 | 结论 |
| --- | ---: | --- |
| 架构 | 8.0 / 10 | 单用户本地服务的边界清晰，后端模块划分合理；`runner.py` 仍承担较多编排职责。 |
| 代码质量 | 8.0 / 10 | 注释解释了关键权衡，测试覆盖不错；少量 API contract 和默认值存在漂移。 |
| 工程化 | 7.5 / 10 | CI、lint、pytest、build 都齐；前端依赖栈偏旧，Node 版本文档/CI 不一致。 |
| 性能与风险 | 7.0 / 10 | 已有关键性能优化；仍有一个 SSRF 校验绕过点和几个长文本/依赖风险。 |

总体：7.6 / 10。

## 3. 验证结果

通过：

- `uv run ruff check .`：通过。
- `LLM_API_KEY=dummy-for-tests uv run pytest -q`：77 passed。
- `npm run build`：通过，产物最大 gzip 约 105 KB。

告警：

- `npm audit --omit=dev --audit-level=moderate`：3 个告警，集中在 `vite <=6.4.2` / `esbuild <=0.24.2` 开发服务器依赖链。修复建议会跨到 `vite@8.1.0`，需要按迁移任务处理。
- `npm outdated --long`：Vite、plugin-react、TypeScript、react-markdown、lucide-react 等存在大版本落后。

## 4. 必须优先处理

本节保留原始发现用于审计追溯；标注“已修复”的条目已经在本轮完成。

### 4.1 `resume` / `retry` 可绕过 LLM base_url SSRF 校验（已修复）

状态：已在 `routes/jobs.py` 中统一 options 解析和 `llm_base_url` 校验，并新增 `resume` / `retry` 回归测试。

原始位置：

- `server/biri_youyaku/routes/jobs.py:154-155`：创建任务时会调用 `_validate_llm_base_url(options.llm_base_url)`。
- `server/biri_youyaku/routes/jobs.py:277-290`：`resume` 更新 options 时没有校验 `llm_base_url`。
- `server/biri_youyaku/routes/jobs.py:304-306`：`retry` 更新 options 时没有校验 `llm_base_url`。
- `server/biri_youyaku/routes/config.py:16-43`：已有 SSRF 防护函数。

影响：

如果服务部署在公网且攻击者拿到 API token，`POST /v1/jobs` 不能直接传内网 URL，但可以对已有 `TRANSCRIPT_READY` / `FAILED` 任务走 `resume` / `retry`，把 `llm_base_url` 改成内网、元数据服务或未授权 host。下一次总结会使用该 base URL。

建议：

在所有会接受 `llm_base_url` override 的入口统一调用 `_validate_llm_base_url`。最好抽一个 helper：

```python
def _options_from_payload(payload_options: JobOptionsPayload, *, validate_base_url: bool = True) -> tuple[JobOptions, dict, str | None]:
    option_overrides = payload_options.model_dump(exclude_unset=True)
    llm_api_key = option_overrides.pop("llm_api_key", None)
    options = JobOptions.from_overrides(option_overrides, settings)
    if validate_base_url:
        _validate_llm_base_url(options.llm_base_url)
    return options, option_overrides, llm_api_key
```

同时补测试：

- `resume` 传 `llm_base_url=http://127.0.0.1:1/v1` 应返回 400。
- `retry` 传未白名单 host 应返回 400。

### 4.2 README 的本地 ollama 配置按当前默认值会失败（已修复）

状态：README / README.en 的 ollama 示例已补充 `LLM_BASE_URL_ALLOWED_HOSTS=`，并明确仅限本地。

原始位置：

- `README.md:91-93`：ollama 示例只设置 `LLM_BASE_URL=http://localhost:11434/v1`。
- `server/biri_youyaku/config.py:60-70`：默认 `LLM_BASE_URL_ALLOWED_HOSTS` 是内置供应商列表，非空。
- `server/biri_youyaku/routes/config.py:36-43`：白名单非空时，`localhost` 不在列表会被拒绝。

影响：

README 说“完全本地：ollama”可用，但用户照抄配置创建任务时会被 `llm_base_url` 白名单拒绝。

建议二选一：

1. 文档修复：ollama 示例补一行 `LLM_BASE_URL_ALLOWED_HOSTS=`，并说明“仅本地开发这样配置，公网不要放开”。
2. 代码策略修复：当 `API_TOKEN` 为空且 host 是 `localhost` / `127.0.0.1` 时允许本地 LLM；公网仍按白名单拒绝。

考虑安全边界，推荐先做文档修复，代码策略另开议题。

### 4.3 邮件配置 readiness 判断与实际发送条件不一致（已修复）

状态：runtime capability、启动 WARN、创建任务早失败、README、CONFIG、`.env.example` 已统一为三项必填：`EMAIL_WEBHOOK_URL` / `EMAIL_WEBHOOK_TOKEN` / `EMAIL_DEFAULT_RECIPIENT`。

原始位置：

- `server/biri_youyaku/routes/config.py:70`：`email_configured` 只检查 `EMAIL_ENABLED` 和 `EMAIL_WEBHOOK_URL`。
- `server/biri_youyaku/modules/email/webhook.py:33-35`：实际发送还要求 `EMAIL_DEFAULT_RECIPIENT`。
- `examples/email-worker/src/index.js:45-49`：模板 Worker 还要求 `BIRI_YOUYAKU_TOKEN`，对应后端 `EMAIL_WEBHOOK_TOKEN`。
- `README.md:177-184`：文档写“任一必填值为空会 WARN / 拒绝”。

影响：

当前前端在 `runtime.email_configured` 为 true 时会自动给新任务传 `email_enabled=true`。如果只配置了 webhook URL 但没配置默认收件人，前端会启用邮件，后端创建任务再 400 拒绝。若使用仓库自带 Worker 且没配 token，任务可创建但邮件阶段会 401。

建议：

- `email_configured` 至少改成 `EMAIL_ENABLED && EMAIL_WEBHOOK_URL && EMAIL_DEFAULT_RECIPIENT`。
- 如果默认 Worker 是推荐路径，启动 WARN 和创建任务早失败也应包含 `EMAIL_WEBHOOK_TOKEN`；如果 token 允许自定义 webhook 为空，则 README 要写清“使用自带 Worker 时必填”。

## 5. 性能优化建议

### 5.1 流式总结目前发送“累计全文”，长摘要会放大 CPU 和网络开销

位置：

- `server/biri_youyaku/modules/llm/client.py:186-198`：每个 delta 都 `content += delta`，然后 `on_chunk(content)`。
- `server/biri_youyaku/events.py:25-28`：`summary_chunk` 被合并，但语义仍是最新累计全文。
- `web/src/hooks/useJobStream.ts:145-149`：前端直接把 payload text 作为完整 summary。

影响：

短摘要问题不大；长视频合并阶段如果输出很长，后端会重复构造越来越长的字符串，SSE 也会重复传完整 Markdown。事件总线合并能防止慢消费者阻塞，但不能减少消费者正常跟上时的重复传输。

建议：

- 中期：新增 `summary_delta` 事件，前端累加 delta；终态仍用 status snapshot 带完整 summary 做纠偏。
- 保守过渡：服务端对累计全文做 50-100ms 节流，减少 SSE 帧数。
- 保持终态 `GET /jobs/{id}` 和 stream snapshot 返回完整 summary，避免断线恢复复杂化。

### 5.2 长视频并发实际是两层乘法，需要文档提示

位置：

- `server/biri_youyaku/config.py:34-35`：`LLM_SEGMENT_CONCURRENCY=3`。
- `server/biri_youyaku/config.py:78-79`：`MAX_CONCURRENT_SUMMARIES=2`。
- `server/biri_youyaku/modules/llm/client.py:273-307`：单个长视频内部并发分段总结。

影响：

默认情况下，两个长视频同时总结时，段级 LLM 请求可能达到 2 * 3 = 6 路，再加最终 merge。对限流严格的供应商会更容易 429。

建议：

在 `CONFIG.md` 给这两个配置加一句：“实际 LLM 并发约为 `MAX_CONCURRENT_SUMMARIES * LLM_SEGMENT_CONCURRENCY`”。必要时把默认 `LLM_SEGMENT_CONCURRENCY` 下调到 2。

### 5.3 `runner.py` 仍是主要复杂度热点

位置：

- `server/biri_youyaku/jobs/runner.py`：503 行，审计脚本标记为 file size hotspot。

现状：

当前文件已经比“散落 dict + 多段生命周期”更干净，注释也解释了历史包袱。但它同时负责任务注册、取消、恢复、阶段转移、并发槽位、错误归因和主流程编排。

建议：

不要为了行数立刻拆。等下一次改任务生命周期时，优先抽这三类纯 helper：

- options / LLM key 处理。
- stage transition / timing 处理。
- transcript acquisition（平台字幕 vs ASR）处理。

目标是降低回归风险，不是追求文件短。

## 6. Clean Code 建议

### 6.1 API payload 应使用更窄类型，减少隐式容错（部分修复）

状态：`task_type` 已收窄为 `Literal["summary", "audio"] | None`；其它自由文本字段仍保持现状。

位置：

- `server/biri_youyaku/routes/jobs.py:37-48`：`JobOptionsPayload` 中 `task_type`、`language`、`summary_language` 等都是宽泛 `str | None`。
- `web/src/lib/api.ts:13-23`：前端已经把 `task_type` 限定为 `'summary' | 'audio'`。

影响：

原先后端会接受任意 `task_type` 字符串；除 `"audio"` 外都会走总结路径。这对单用户工具不严重，但 API contract 不够清晰。

建议：

`task_type` 已处理。后续如继续收窄，可对 `llm_base_url` 用 Pydantic URL 或现有校验函数统一入口，让 422 更早于业务层。

### 6.2 RuntimeConfig 类型和后端响应有历史字段漂移（已修复）

状态：前端 `RuntimeConfig` 类型和 fallback 已删除 `api_token_required`。

原始位置：

- `server/biri_youyaku/routes/config.py:63-72`：后端返回 `auth_mode`，不返回 `api_token_required`。
- `web/src/lib/api.ts:190-198`：前端类型仍要求 deprecated `api_token_required`。
- `web/src/lib/runtimeConfig.ts:9-16`：fallback 仍包含 `api_token_required`。

影响：

当前没有运行时 bug，因为代码使用 `auth_mode`。但类型声明不再准确，后续维护者容易误以为后端还提供旧字段。

建议：

删除前端 deprecated 字段，或后端恢复返回 `api_token_required` 作为兼容字段。更推荐删前端字段，保持公开 contract 简单。

### 6.3 `repo.py` 可以保留当前集中式，但读改写函数需谨慎扩展

位置：

- `server/biri_youyaku/jobs/repo.py:361-391`：`add_stage_timing` 和 `add_token_usage` 都是 read-modify-write。

现状：

当前运行在单进程、主要单事件循环内，风险可接受；测试也覆盖了 token usage 累加。

建议：

如果未来引入多 worker / 多进程，需把这类累加改成事务或独立表 append-only。现在无需立即重构。

## 7. README 与文档一致性

### 简洁度

README 主体是简洁的，符合项目约束：

- 快速开始、架构、LLM、可选 ASR、邮件、文档入口都在一屏到几屏内。
- 完整配置放在 `CONFIG.md`，公网部署放在 `DEPLOY.md`，没有把 README 扩成百科。
- API 只列常用入口，完整列表交给 FastAPI `/docs`，合理。

### 需要修正的一致性点

1. Node 版本不一致（已修复）：
   - `.nvmrc` 是 `22.14.0`。
   - `README.md:17` / `README.en.md:20` / `scripts/dev.sh:18` / `scripts/dev.ps1:12` 写 Node.js 22+。
   - `.github/workflows/ci.yml:56` 用 Node 20。
   - 处理：CI 已升到 Node 22，和 `.nvmrc` / README 一致。

2. 本地 ollama 示例缺少 `LLM_BASE_URL_ALLOWED_HOSTS=`，见 4.2（已修复）。

3. 邮件“配置完成”的定义不一致，见 4.3（已修复）。

4. `web/src/lib/api.ts:212-215` 注释提到已删 endpoint：`POST /v1/llm/models`、`GET /v1/usage` 等。作为源码注释可以，但如果 README 后续再扩 API 列表，应避免把这些历史 endpoint 带回文档。

## 8. 依赖与安全维护

### 前端

当前 `npm audit` 报告集中在 Vite 3 / esbuild 开发服务器链路：

- `esbuild <=0.24.2`：moderate。
- `vite <=6.4.2`：依赖 vulnerable esbuild。
- `@vitejs/plugin-react 2.x`：依赖 vulnerable vite。

建议：

1. 单独开一个 `chore(web): upgrade vite toolchain`。
2. 目标版本：Vite 最新大版本、`@vitejs/plugin-react` 对应大版本、TypeScript 至少升到当前稳定主线。
3. 验证：
   - `npm run build`
   - 本地 dev server 打开首页、历史页、UP 页、mindmap lazy chunk。
   - 如果升级 React 19，另开任务；不要和 Vite 升级混在一个 commit。

### 后端

`uv tree --depth 1` 显示核心依赖当前较新；`ruff` 被钉在 `<0.5` 是项目明确取舍。暂不建议为了“更新而更新”后端主依赖。

## 9. 建议执行顺序

1. [x] 修 SSRF 校验绕过：`resume` / `retry` 统一校验 `llm_base_url`，补测试。
2. [x] 修文档/配置漂移：ollama 示例、邮件 readiness、Node CI 版本。
3. [x] 清理 RuntimeConfig deprecated 字段。
4. [x] 给长视频并发配置补文档说明。
5. [ ] 单独升级 Vite 工具链，处理 `npm audit`。
6. [ ] 评估 `summary_delta`，只有在长摘要流式性能成为真实痛点时再改协议。

## 10. 暂不建议做的事

- 不建议引入 ORM：当前 SQLite 裸写法符合项目约束，且 repo 层已经集中。
- 不建议重写 SSE：当前 `sse-starlette` + coalesced event bus 的设计是对的。
- 不建议为了行数拆 `runner.py`：先修具体问题，等生命周期逻辑再次变动时顺手拆 helper。
- 不建议把 README 继续扩长：新增细节应进 `CONFIG.md` / `DEPLOY.md` / 专项 docs。
