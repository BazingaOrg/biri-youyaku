# 2026-07-30 上云前置与 Cutover 分步实施

> 数据与唯一 writer 现状：家用 **Mac Mini**。开发机只改代码；阿里云为 cutover 后唯一 writer。

## 目标

1. 本机加固：路径可迁移、backup/restore 可执行、单 writer 与 ASR/拓扑写死。
2. Mini：生产 backup + restore 演练。
3. 阿里云：空栈 + Tunnel；再迁数据 cutover。
4. 完整 D（OSS outbox / Mini 只读）后置。

## 阶段与顺序

| 阶段 | 地点 | 内容 | 出口 |
| --- | --- | --- | --- |
| **S1 本机加固** | 开发机 | 路径相对化；restore 脚本；runbook；env/ASR 说明 | 测试绿；空 Docker 可冒烟 |
| **S2 Mini 验收** | Mac Mini（远程） | 部署 S1；生产 backup；restore 演练；路径 rewrite | 可信 backup + 可恢复 |
| **S3 云就绪** | 阿里云（可与 S2 并行） | ECS+数据盘；空 compose；Tunnel/Access；OSS bucket | healthz 通 |
| **S4 Cutover** | Mini + 云 | drain → 金样本 backup → 迁 ECS → 停 Mini 写 | 单 writer 在 ECS |
| **S5 增强** | 云 | 定时冷备 OSS；可选 outbox/Mini 只读 | 非当天 |

## S1 执行项（本批编码）

1. [x] knowledge `storage_path`：入库相对 `KNOWLEDGE_STORAGE_DIR`；读取/删除时 resolve；兼容旧绝对路径。
2. [x] jobs `summary_path`：入库相对 `SUMMARY_STORAGE_DIR`；`read_summary`/cleanup 时 resolve。
3. [x] 一次性 path rewrite 辅助（CLI 或 backup 模块函数，供 Mini 迁移用）。
4. [x] `knowledge_restore`：校验 manifest + 停写前提下恢复到目标 data 布局。
5. [x] 文档：CONFIG restore、`docs/runbooks/cutover.md`、`.env.example` ASR/云端提示、Dockerfile 注释对齐。
6. [x] 测试：相对路径 round-trip、绝对路径兼容、restore dry-run/verify。

## 锁定默认（S1）

- 拓扑默认文档：**Vercel 前端 + Tunnel 后端**（与 DEPLOY.md 一致）；ECS 同源为备选。
- 云端 ASR 默认：**不装** funasr（镜像 slim）；无字幕策略在 runbook 标明。
- 单 writer：任意时刻 Mini 与 ECS 不可双开写库。

## 非目标（S1）

- OSS outbox、Mac receive-only、CF Access 自动化 IaC、向量库、打开 chat 默认。

## 实施备注

### S1 本机加固（2026-07-30）

**实际变更**

- `knowledge/artifacts.py`：`to_stored_path` / `resolve_stored_path` / `rewrite_artifact_paths_in_db`。
- `register.py`：artifact `storage_path` 入库相对路径；`register` 读 job summary 经 summary resolve。
- `index.py` / `lifecycle.py`：打开/删除 artifact 前 `resolve_stored_path`。
- `modules/storage/summary.py`：同上 pattern + `rewrite_summary_paths_in_db`。
- `jobs/repo.py`：`set_summary_path` 存相对；`read_summary` / `all_summary_paths` resolve；cleanup 删除 resolve。
- `knowledge/backup.py`：`verify_backup` + `restore_backup`（dry_run / force；不自动 reindex）。
- CLI：`scripts/knowledge_restore.py`、`scripts/knowledge_rewrite_paths.py`；backup 脚本 docstring 指向 restore。
- 文档：`CONFIG.md` restore、`docs/runbooks/cutover.md`、`.env.example`、`Dockerfile` 注释。
- 测试：`tests/test_knowledge_paths.py`（相对入库、索引、legacy 绝对、rewrite、backup restore）。

**偏差**

- 无向量库 / OSS outbox / 前端拓扑代码改动（仅 runbook 文档）。
