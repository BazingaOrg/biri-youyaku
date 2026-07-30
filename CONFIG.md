# 配置参考 / Configuration reference

[中文](#配置参考) | [English](#configuration)

`server/.env` 的所有可调项，默认值见 `server/biri_youyaku/config.py`。
对应模板：`server/.env.example`（**开关与常用项一律显式写出**，与代码默认一致；拷贝后按需改）。

---

## 配置参考

| 类别 | 变量 | 默认 | 说明 |
| --- | --- | --- | --- |
| 应用 | `APP_LOG_LEVEL` | `INFO` | uvicorn / 应用日志级别 |
| 应用 | `APP_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 多个用逗号分隔 |
| 鉴权 | `API_TOKEN` | 空 | 空 = 不校验 Bearer Token（仅本地） |
| B 站 | `BILI_SESSDATA` | 空 | 浏览器登录后从 cookie 复制；多数视频只配这一个就够 |
| B 站 | `BILI_BUVID3` | 空 | 部分接口（高画质字幕、私享视频）需要 |
| B 站 | `BILI_BILI_JCT` | 空 | CSRF token，少数接口需要 |
| ASR | `ASR_MODEL` | `sensevoice` | `sensevoice` / `sensevoice-mlx` / `parakeet-mlx` / `faster-whisper` / `auto` |
| ASR | `ASR_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| ASR | `ASR_LANGUAGE_DEFAULT` | `auto` | |
| ASR | `SENSEVOICE_MODEL_DIR` | 空 | 自动下载 / 指定本地路径 |
| LLM | `LLM_API_KEY` | 空 | **必填** |
| LLM | `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容接口（默认 DeepSeek） |
| LLM | `LLM_MODEL` | `deepseek-v4-flash` | DeepSeek 最新基础款 |
| LLM | `LLM_THINKING_ENABLED` | `false` | 仅 deepseek-v4-* 有效；开启质量略升，但流式变慢且 token 增加 |
| LLM | `LLM_TIMEOUT_SECONDS` | `300` | 单请求超时 |
| LLM | `LLM_MAX_RETRIES` | `2` | SDK 层重试 |
| LLM | `LLM_TEMPERATURE` | 空 | 留空走代码默认 |
| LLM | `LLM_CHUNK_TOKEN_THRESHOLD` | `30000` | 长字幕分段阈值 |
| LLM | `LLM_SEGMENT_CONCURRENCY` | `3` | 段级总结并发数；长视频实际 LLM 并发约为 `MAX_CONCURRENT_SUMMARIES * LLM_SEGMENT_CONCURRENCY` |
| LLM | `LLM_BASE_URL_ALLOWED_HOSTS` | 内置常见供应商列表 | SSRF 白名单；空 = 不限制（仅本地） |
| LLM | `OPENROUTER_MANAGEMENT_API_KEY` | 空 | OpenRouter 管理 Key，用于读取账户 credits；普通推理 Key 只看自身限额 |
| LLM | `USAGE_FINGERPRINT_SECRET` | 空 | 稳定指纹密钥（不存原始 Key）；空则从本实例已有密钥安全派生 |
| 总结 | `SUMMARY_LANGUAGE` | `中文简体` | 输出语言 |
| 周报 | `WEEKLY_SUMMARY_TIMEZONE` | `Asia/Shanghai` | 周报周界与「本周」划分所用时区 |
| 邮件 | `EMAIL_ENABLED` | `false` | |
| 邮件 | `EMAIL_WEBHOOK_URL` | 空 | 收 webhook 的 URL（如 Cloudflare Worker） |
| 邮件 | `EMAIL_WEBHOOK_TOKEN` | 空 | 启用邮件时必填；后端 → Worker 的鉴权 token，与 Worker 端 `BIRI_YOUYAKU_TOKEN` 一致 |
| 邮件 | `EMAIL_DEFAULT_RECIPIENT` | 空 | **唯一**收件人；后端永远只发到这里（无 per-job 收件人，防滥发） |
| 邮件 | `EMAIL_SUBJECT_TEMPLATE` | `[Biri-Youyaku] {{title}}` | 支持 `{{title}}` / `{{author}}` |
| 存储 | `AUDIO_STORAGE_DIR / SUMMARY_STORAGE_DIR / DISTILL_STORAGE_DIR / KNOWLEDGE_STORAGE_DIR / DB_PATH` | `data/...` | `KNOWLEDGE_STORAGE_DIR` 存 knowledge artifacts；`KNOWLEDGE_REGISTER_ENABLED` 默认 true，关则跳过登记/回填 |
| 知识库 | `KNOWLEDGE_REGISTER_ENABLED` | `true` | 关闭后 register/reconcile 空操作（回滚开关）；已落盘 artifact 不删 |
| 知识库 | `KNOWLEDGE_SEARCH_ENABLED` | `true` | 基于总结的 FTS 检索；需 register 开启才对外暴露 |
| 知识库 | `KNOWLEDGE_CHAT_ENABLED` | `false` | 基于总结的知识问答（默认关；开启后 query+片段会发往已配置 LLM） |
| 知识库 | `KNOWLEDGE_TRANSCRIPT_INDEX_ENABLED` | `true` | 原始字幕 FTS 索引层；检索时可叠加总结层 |
| 知识库 | `KNOWLEDGE_SOFT_DELETE_DAYS` | `30` | 软删除文档超过该天数后由 cleanup 自动永久清理 |
| 知识库 | `KNOWLEDGE_BACKUP_DIR` | `data/backups` | 本地一致性备份目录（`sqlite` backup + knowledge + summaries + manifest） |
| 清理 | `AUDIO_RETENTION_DAYS` | `7` | 自动清 audio 文件并清空 path；job 行保留 |
| 清理 | `JOB_RETENTION_DAYS` | `180` | 仅自动删除 FAILED/CANCELED 且无 summary 的 job；COMPLETED 永久保留至用户手动删除 |
| 清理 | `ORPHAN_FILE_RETENTION_DAYS` | `3` | DB 不引用的孤儿文件多久后清 |
| 清理 | `STALE_RUNNING_FAIL_HOURS` | `4` | 非终态任务多久无心跳就置 FAILED |
| 清理 | `CLEANUP_INTERVAL_SECONDS` | `3600` | 清理循环周期 |
| 清理 | `WAL_CHECKPOINT_INTERVAL_HOURS` | `24` | WAL 截断周期 |
| 清理 | `DB_VACUUM_INTERVAL_DAYS` | `30` | VACUUM 周期 |
| 并发 | `MAX_CONCURRENT_JOBS` | `2` | `_io_semaphore` 上限：同时跑的「下载音频 + 转写」任务数 |
| 并发 | `MAX_CONCURRENT_SUMMARIES` | `2` | `_summary_semaphore` 上限：同时跑的 LLM 总结任务数 |
| 并发 | `DISTILL_TRANSCRIPT_CONCURRENCY` | `3` | 蒸馏 `_do_prepare_transcripts` 阶段并发获取/转写视频的上限 |
| 防滥用 | `MAX_VIDEO_DURATION_SECONDS` | `14400` | 视频时长上限（默认 4 小时）；超长直接拒 |
| 防滥用 | `MAX_INFLIGHT_JOBS` | `20` | 同时在飞任务上限；超出返回 503 |

### 运维提示（macOS 常驻 / 备份）

- **macOS LaunchAgent 常驻 API**（本机 MLX ASR、无需常开终端）：见 [`docs/runbooks/macos-service.md`](docs/runbooks/macos-service.md)，脚本 `scripts/mac-service.sh`。
- **知识库备份**仍建议定期做（换机、误删、盘故障）；相对 `data/*` 路径便于备份与迁移。CLI / API 见下文 English 节 *Knowledge backup & restore*，或中文环境直接：

```bash
cd server && uv run python scripts/knowledge_backup.py
```

---

## Configuration

All tunable settings live in `server/.env`; defaults are in
`server/biri_youyaku/config.py`. Template: `server/.env.example`
(booleans and common keys are written out explicitly; edit after copy).

| Group | Variable | Default | Notes |
| --- | --- | --- | --- |
| App | `APP_LOG_LEVEL` | `INFO` | uvicorn / app log level |
| App | `APP_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | comma-separated |
| Auth | `API_TOKEN` | empty | empty = no Bearer Token check (local only) |
| Bilibili | `BILI_SESSDATA` | empty | copy from browser cookies after login; most videos only need this one |
| Bilibili | `BILI_BUVID3` | empty | required by some endpoints (HQ subs, members-only videos) |
| Bilibili | `BILI_BILI_JCT` | empty | CSRF token, required by a few endpoints |
| ASR | `ASR_MODEL` | `sensevoice` | `sensevoice` / `sensevoice-mlx` / `parakeet-mlx` / `faster-whisper` / `auto` |
| ASR | `ASR_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| ASR | `ASR_LANGUAGE_DEFAULT` | `auto` | |
| ASR | `SENSEVOICE_MODEL_DIR` | empty | auto-download / local path |
| LLM | `LLM_API_KEY` | empty | **required** |
| LLM | `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI-compatible (default DeepSeek) |
| LLM | `LLM_MODEL` | `deepseek-v4-flash` | DeepSeek latest base model |
| LLM | `LLM_THINKING_ENABLED` | `false` | DeepSeek-v4 only; slightly higher quality but slower stream and more tokens |
| LLM | `LLM_TIMEOUT_SECONDS` | `300` | per-request timeout |
| LLM | `LLM_MAX_RETRIES` | `2` | SDK-level retry |
| LLM | `LLM_TEMPERATURE` | empty | empty = code default |
| LLM | `LLM_CHUNK_TOKEN_THRESHOLD` | `30000` | long-transcript split threshold |
| LLM | `LLM_SEGMENT_CONCURRENCY` | `3` | per-segment summarize concurrency; long-video LLM concurrency is roughly `MAX_CONCURRENT_SUMMARIES * LLM_SEGMENT_CONCURRENCY` |
| LLM | `LLM_BASE_URL_ALLOWED_HOSTS` | built-in providers | SSRF allowlist; empty = no limit (local only) |
| LLM | `OPENROUTER_MANAGEMENT_API_KEY` | empty | OpenRouter management key for account credits; normal inference keys only show their own limit |
| LLM | `USAGE_FINGERPRINT_SECRET` | empty | stable fingerprint secret (never stores raw keys); empty → derived from this instance's secrets |
| Summary | `SUMMARY_LANGUAGE` | `中文简体` | output language |
| Weekly | `WEEKLY_SUMMARY_TIMEZONE` | `Asia/Shanghai` | timezone used for weekly boundaries / "this week" |
| Email | `EMAIL_ENABLED` | `false` | |
| Email | `EMAIL_WEBHOOK_URL` | empty | the webhook receiver URL (e.g. a Cloudflare Worker) |
| Email | `EMAIL_WEBHOOK_TOKEN` | empty | required when email is enabled; auth token from backend → worker; must match the worker's `BIRI_YOUYAKU_TOKEN` |
| Email | `EMAIL_DEFAULT_RECIPIENT` | empty | the **only** recipient; backend always sends here (no per-job recipient, anti-abuse) |
| Email | `EMAIL_SUBJECT_TEMPLATE` | `[Biri-Youyaku] {{title}}` | `{{title}}` / `{{author}}` allowed |
| Storage | `AUDIO_STORAGE_DIR / SUMMARY_STORAGE_DIR / DISTILL_STORAGE_DIR / KNOWLEDGE_STORAGE_DIR / DB_PATH` | `data/...` | `KNOWLEDGE_STORAGE_DIR` holds knowledge artifacts; `KNOWLEDGE_REGISTER_ENABLED` defaults true (disable to skip register/reconcile) |
| Knowledge | `KNOWLEDGE_REGISTER_ENABLED` | `true` | when false, register/reconcile no-op (rollback switch); existing artifacts kept |
| Knowledge | `KNOWLEDGE_SEARCH_ENABLED` | `true` | FTS search over active summaries; exposed only when register is on |
| Knowledge | `KNOWLEDGE_CHAT_ENABLED` | `false` | opt-in knowledge Q&A over summaries (default off; when on, query+chunks go to configured LLM) |
| Knowledge | `KNOWLEDGE_TRANSCRIPT_INDEX_ENABLED` | `true` | raw transcript FTS layer; layered retrieve uses it when present |
| Knowledge | `KNOWLEDGE_SOFT_DELETE_DAYS` | `30` | soft-deleted docs older than this are permanently purged by cleanup |
| Knowledge | `KNOWLEDGE_BACKUP_DIR` | `data/backups` | local consistent backups (sqlite backup API + knowledge + summaries + hash manifest) |
| Cleanup | `AUDIO_RETENTION_DAYS` | `7` | auto: delete audio file(s) and clear path; job row kept |
| Cleanup | `JOB_RETENTION_DAYS` | `180` | auto-delete only FAILED/CANCELED jobs with no summary; COMPLETED kept until explicit user delete |
| Cleanup | `ORPHAN_FILE_RETENTION_DAYS` | `3` | how long DB-unreferenced files linger |
| Cleanup | `STALE_RUNNING_FAIL_HOURS` | `4` | non-terminal job auto-FAILED after N hours of silence |
| Cleanup | `CLEANUP_INTERVAL_SECONDS` | `3600` | cleanup loop period |
| Cleanup | `WAL_CHECKPOINT_INTERVAL_HOURS` | `24` | WAL checkpoint period |
| Cleanup | `DB_VACUUM_INTERVAL_DAYS` | `30` | VACUUM period |
| Concurrency | `MAX_CONCURRENT_JOBS` | `2` | `_io_semaphore` cap: concurrent "download audio + transcribe" jobs |
| Concurrency | `MAX_CONCURRENT_SUMMARIES` | `2` | `_summary_semaphore` cap: concurrent LLM summarize jobs |
| Concurrency | `DISTILL_TRANSCRIPT_CONCURRENCY` | `3` | Fan-out cap for `_do_prepare_transcripts` obtaining/transcribing videos concurrently for a distill run |
| Abuse | `MAX_VIDEO_DURATION_SECONDS` | `14400` | video length cap (default 4h); too long → reject |
| Abuse | `MAX_INFLIGHT_JOBS` | `20` | total in-flight jobs; overflow → 503 |

### Knowledge backup & restore (local, portable)

Recommended on any long-running host (Mac Mini LaunchAgent, Linux, etc.). Create a consistent snapshot (prefer while writers are idle):

```bash
# API (Bearer if API_TOKEN set)
curl -X POST http://127.0.0.1:17821/v1/knowledge/backup \
  -H 'Content-Type: application/json' -d '{"dry_run": false}'

# or CLI from server/
uv run python scripts/knowledge_backup.py
uv run python scripts/knowledge_backup.py --dry-run
```

Each backup under `KNOWLEDGE_BACKUP_DIR/<timestamp>/` contains:

- `biri_youyaku.db` — via SQLite backup API (WAL-safe)
- `knowledge/` — knowledge artifacts tree
- `summaries/` — legacy summary files
- `manifest.json` — relative paths + SHA-256 + restore hint

**Restore** (stop the server/LaunchAgent first; path rewrite helpers remain for machine moves — see also `docs/runbooks/macos-service.md`):

```bash
# Stop the server first, then from server/:
#   bash scripts/mac-service.sh stop   # from repo root
uv run python scripts/knowledge_restore.py --from data/backups/<timestamp>
uv run python scripts/knowledge_restore.py --from data/backups/<timestamp> --dry-run
uv run python scripts/knowledge_restore.py --from data/backups/<timestamp> --force  # ignore hash mismatch
uv run python scripts/knowledge_restore.py --from data/backups/<timestamp> --replace-trees  # wipe dest knowledge/summaries first
```

Restore verifies `manifest.json` hashes, then copies `biri_youyaku.db`, `knowledge/`, and `summaries/` to settings paths (or `--dest-*` overrides). After replacing the main DB it **deletes** destination `*.db-wal` / `*.db-shm` so a leftover WAL cannot attach to the restored file. Default tree restore **merges** into existing dirs; `--replace-trees` rmtree then copy. It does **not** reindex FTS; after restart run `POST /v1/knowledge/reindex` if search is empty.

**Path rewrite (absolute → relative under storage roots, for machine move):**

```bash
uv run python scripts/knowledge_rewrite_paths.py --dry-run
uv run python scripts/knowledge_rewrite_paths.py
```

Artifact `storage_path` and job `summary_path` are stored relative when under the configured roots; readers resolve via knowledge/summary helpers (legacy absolute paths still work).

Soft-deleted documents are excluded from search/status “visible” counts; after `KNOWLEDGE_SOFT_DELETE_DAYS` (default 30) cleanup permanently purges them.
