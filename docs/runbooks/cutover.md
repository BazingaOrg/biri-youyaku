# Cutover runbook — Mini → 阿里云

> 单一 writer 规则：**任意时刻** Mac Mini 与阿里云 ECS 不可同时写同一库。开发机只改代码、不写生产数据。

## 角色

| 角色 | 机器 | 职责 |
| --- | --- | --- |
| **dev** | 开发机 | 编码、测试、出镜像/文档；不挂生产 `data/` |
| **Mac Mini** | 家用生产（cutover 前） | 当前唯一 writer；S2 备份与 restore 演练 |
| **Aliyun ECS** | 云生产（cutover 后） | 唯一 writer；空栈就绪后再迁数据 |

## 单 writer 规则

1. 同一时刻只允许一台机器对 `DB_PATH` / knowledge / summaries 写入。
2. Cutover 窗口：Mini **先停写** → 金样本 backup → 迁到 ECS → 在 ECS 启服务 → Mini 保持停写（或只读，完整 D 后再做）。
3. 禁止「两边都开着试一下」；回滚时同样：ECS 停写 → 从金样本 restore 回 Mini → 只启 Mini。

## 默认拓扑与 ASR

- **拓扑默认**：Vercel 前端 + Cloudflare Tunnel 打到后端（与 `DEPLOY.md` 一致）。ECS 同源反代为备选。
- **云端 ASR 默认**：**不装** funasr（镜像 slim，无 `--extra asr`）。无官方字幕的视频在云端默认无法本地 ASR；需 ASR 时另开带 `--extra asr` 的镜像并配置模型路径（Linux 用 `ASR_MODEL=sensevoice`，不要拷贝 Mac 绝对路径的 `SENSEVOICE_MODEL_DIR`）。
- **知识库 chat**：默认 `KNOWLEDGE_CHAT_ENABLED=false`（保持）。

## S2 — Mini 验收清单

1. 部署含 S1 的代码（相对路径 + restore CLI）。
2. 生产 backup（writer 空闲时）：
   ```bash
   cd server
   uv run python scripts/knowledge_backup.py
   ```
3. Restore **演练**（到临时目录，勿覆盖生产）：
   ```bash
   uv run python scripts/knowledge_restore.py --from data/backups/<ts> --dry-run
   uv run python scripts/knowledge_restore.py --from data/backups/<ts> \
     --dest-db /tmp/restore-drill/biri.db \
     --dest-knowledge /tmp/restore-drill/knowledge \
     --dest-summaries /tmp/restore-drill/summaries
   ```
4. Path rewrite dry-run / 实写（迁移前把绝对路径改成相对）：
   ```bash
   uv run python scripts/knowledge_rewrite_paths.py --dry-run
   uv run python scripts/knowledge_rewrite_paths.py
   ```
5. 确认 backup 目录可离线拷贝到安全处（U 盘 / OSS 手工上传均可）。

## S3 — 云端空栈 + Tunnel

1. ECS + 数据盘；挂载点写进 compose / `.env` 的相对 `data/*` 路径。
2. 空 compose 起 slim 镜像（**无** `--extra asr`）。
3. 配置 Tunnel / Access；`healthz` 通。
4. 预建 OSS bucket（冷备用，S5）；**不要**在空栈阶段双写生产库。
5. `.env`：相对 `data/*`；`ASR_MODEL=sensevoice` 若以后开 ASR；**不要**从 Mini 复制 Mac 绝对 `SENSEVOICE_MODEL_DIR`；`KNOWLEDGE_CHAT_ENABLED=false`。

## S4 — Cutover 步骤

1. **Drain**：Mini 停止接新任务；等 in-flight 结束。
2. **金样本 backup**：
   ```bash
   uv run python scripts/knowledge_backup.py
   ```
   记录 `data/backups/<timestamp>/`。
3. **Path rewrite**（若库内仍有绝对路径）：
   ```bash
   uv run python scripts/knowledge_rewrite_paths.py
   ```
   再打一份 backup（可选但推荐）。
4. **停 Mini 写进程**（systemd/compose stop）。
5. **迁数据到 ECS**（rsync/scp backup 目录或整 `data/`）。
6. **ECS restore**（或直接解压到 `data/` 布局）：
   ```bash
   uv run python scripts/knowledge_restore.py --from data/backups/<timestamp>
   ```
7. **启 ECS**；健康检查；抽样 search / 打开一条历史总结。
8. FTS 空则 `POST /v1/knowledge/reindex`。
9. Tunnel / DNS 切到 ECS；**Mini 保持停写**。

## 回滚

1. ECS stop（停写）。
2. 从金样本 backup restore 回 Mini 的 `data/`（或保留 cutover 前 Mini 未覆盖的副本）。
3. 只启 Mini；Tunnel 指回 Mini。
4. 记录失败原因后再择机重试 cutover。

## 相关命令速查

| 动作 | 命令（`server/`） |
| --- | --- |
| Backup | `uv run python scripts/knowledge_backup.py` |
| Backup dry-run | `uv run python scripts/knowledge_backup.py --dry-run` |
| Restore | `uv run python scripts/knowledge_restore.py --from data/backups/<ts>` |
| Restore dry-run | `… --dry-run` |
| Rewrite paths | `uv run python scripts/knowledge_rewrite_paths.py` |
