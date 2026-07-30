# 2026-07-30 知识库评测 Gate（Phase F）

> 承接 `2026-07-29-personal-knowledge-base-rag.md` 中 B/C 书面降级后的 **holdout 评测基建**。  
> **不**默认打开 chat；**不**在本批做 dense / normalizer / 会话持久化（过 gate 后再开子计划）。

## 目标

1. 可重复的 **synthetic** 语料 + query 集（入库、FTS/分层检索可测）。  
2. 评测 runner：Recall@5、MRR@10、no-answer 行为、transcript 层 document 命中（可扩展）。  
3. pytest 锁定 synthetic 路径（空 corpus 不得虚报通过）。  
4. CLI 输出 JSON 报告；可选 private real corpus 目录（gitignore，本批只留接口）。  
5. 计划备注：当前 gate **未**宣称生产就绪；`KNOWLEDGE_CHAT_ENABLED` 仍默认 false。

## 非目标（本批）

- dense / sqlite-vec  
- normalizer A/B  
- conversation 表  
- reindex 分批（另项）  
- 调低数值门槛或污染 holdout  

## 执行项

1. [x] fixtures：`server/tests/fixtures/knowledge_eval/`  
2. [x] `biri_youyaku/knowledge/eval.py` 加载/灌库/指标  
3. [x] `scripts/knowledge_eval.py` CLI  
4. [x] `tests/test_knowledge_eval.py`  
5. [x] 主 RAG 计划与 CONFIG 指针  

## 成功标准

- `uv run pytest tests/test_knowledge_eval.py` 绿  
- CLI 对 synthetic 输出 metrics + `gates_met` bool  
- chat 默认配置不变  

## 实施备注

**2026-07-30 Phase F eval harness**

- Synthetic fixtures：8 docs、18 answerable + 5 no_answer queries；categories entity/topic/commands/numbers/no_answer；summary + transcript layers。
- `knowledge/eval.py`：`load_*`、`seed_eval_corpus`（真实 `try_register_job` + FTS）、`run_eval`（summary Recall@5 / MRR@10、no_answer empty rate、transcript doc Recall@5、per-split）、`evaluate_gates`、`run_synthetic_eval`。
- CLI 默认 **隔离 temp DB**，stdout JSON，`gates_met` → exit 0/1；`--fixtures` / `--split`。
- CI `manifest.json` thresholds 仅针对 synthetic 小语料，**不等于**主计划生产 holdout 门槛；`KNOWLEDGE_CHAT_ENABLED` 仍默认 false。
- 私有语料：同布局目录 + `--fixtures`（见 fixtures README）；不提交真实用户内容。

## Review issues / root causes

- 私有语料建议目录未实际加入 `.gitignore`，README 与仓库保护规则脱节。
- no-answer 仅查询 summary FTS，未复用生产 search 的分层 `retrieve()`，会漏掉 transcript-only evidence。
- transcript Recall 将分层返回的 summary 与 transcript 混合去重，summary 命中可错误满足 transcript 指标。
- gate 对缺失/拼错 threshold 及 seed 注册失败均未 fail-closed，可能产生假绿。

## 修复实施记录

- `.gitignore` 精确忽略 `server/tests/fixtures/knowledge_eval_private/`。
- no-answer 改用生产 search 相同的 `retrieve(..., mode="search")`；transcript 指标仅计 `source_level == "transcript"` evidence。
- gate 要求全部既定指标阈值存在且为 0–1 的有限非 bool 数值；未知或非法阈值以结构化 failure 拒绝通过。
- runner 将空 corpus 与 seed 注册不完整合入 gate failure，并新增相关回归测试。
- 偏差：无。
