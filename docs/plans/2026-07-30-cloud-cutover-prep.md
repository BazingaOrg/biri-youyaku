# 2026-07-30 本机耐久与运维（原「上云 cutover」计划）

> **状态（2026-07-30 修订）：阿里云 ECS cutover 路线已取消。**  
> 生产仍在常开 **Mac Mini**；高频 ASR 依赖本机 MLX，不用 Docker/Linux 镜像当日常 writer。  
> 本文保留 **S1 路径可迁移 + backup/restore** 的价值说明，并记录后续 **macOS LaunchAgent 常驻**。

## 当前部署结论

| 决策 | 选择 | 原因 |
| --- | --- | --- |
| Writer | Mac Mini 本机 `uv` + uvicorn | 高频 MLX ASR；家中机器常开 |
| 常驻方式 | **launchd LaunchAgent**（`scripts/mac-service.sh`） | 不占终端窗口；开机可拉起 |
| Docker / OrbStack | 不作为 ASR 生产 | 容器无 MLX；默认镜像无 ASR |
| 阿里云 ECS | **不做** | 无「家机会关」痛点；2G 不适配高频 ASR |
| 路径相对化 + backup | **保留** | 重装/换盘/误删恢复，与是否上云无关 |

## 已完成

### S1 本机加固（保留）

1. [x] knowledge / summary 路径相对存储根；读写 resolve；兼容旧绝对路径  
2. [x] `knowledge_rewrite_paths.py`  
3. [x] `knowledge_restore.py` + manifest 校验  
4. [x] 测试与 CONFIG 备份说明  

### S2 Mini 验收（保留结论）

1. [x] 生产 backup 校验通过（例：474 文件 hash 一致）  
2. [x] 路径已全部 relative（rewrite dry-run 无需实写）  

### S3–S5 阿里云

- [ ] ~~ECS / Tunnel cutover / OSS outbox~~ → **取消**，不实施。

### S6 macOS 常驻（本批）

1. [x] `scripts/mac-service.sh` + plist 模板  
2. [x] `docs/runbooks/macos-service.md`  
3. [x] README 指引；原 cutover runbook 收敛  

## 日常运维（Mini）

```bash
# 安装并启动（一次）
bash scripts/mac-service.sh install

# 改完后端代码
bash scripts/mac-service.sh restart

# 要跑 dev.sh 热重载时
bash scripts/mac-service.sh stop
bash scripts/dev.sh
# 结束后
bash scripts/mac-service.sh start

# 备份（空闲时）
cd server && uv run python scripts/knowledge_backup.py
```

详见 `docs/runbooks/macos-service.md`。

## 非目标

- OSS outbox、Mac receive-only 镜像、CF Access IaC、向量库、默认打开 knowledge chat。  
- 为「上云」单独维护的第二套生产拓扑。

## 实施备注

### 2026-07-30 — 取消云 cutover，改为 Mini LaunchAgent

- 不删除 S1 的相对路径与 backup/restore 代码与 CLI。  
- 删除/改写以 ECS 为主线的操作预期；`docs/runbooks/cutover.md` 改为简短「已取消」指针。  
- 新增 macOS 服务脚本与 runbook。  
