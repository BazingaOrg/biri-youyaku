# （已取消）阿里云 Cutover

> **2026-07-30：** 本仓库个人部署路径改为 **Mac Mini 本机常驻**（高频 MLX ASR + launchd）。  
> **不再实施** ECS / Tunnel cutover / OSS outbox 作为既定计划。

## 请改用

| 需求 | 文档 / 命令 |
| --- | --- |
| 后端不占终端、开机自启 | [`macos-service.md`](./macos-service.md)、`bash scripts/mac-service.sh install` |
| 本地备份与恢复 | `CONFIG.md`（Knowledge backup）、`server/scripts/knowledge_backup.py` / `knowledge_restore.py` |
| 可选公网暴露（仍跑在家里） | 根目录 [`DEPLOY.md`](../../DEPLOY.md)（Tunnel 指本机，**不是**迁阿里云） |

## 为何保留相对路径与 backup 代码

与是否上云无关：换盘、重装系统、误删后的校验恢复仍需要。不要当作「云专用」删除。

## 历史计划

分阶段记录见 [`docs/plans/2026-07-30-cloud-cutover-prep.md`](../plans/2026-07-30-cloud-cutover-prep.md)（已修订为取消 S3–S5）。
