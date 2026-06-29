# 配置参考 / Configuration reference

[中文](#配置参考) | [English](#configuration)

`server/.env` 的所有可调项，默认值见 `server/biri_youyaku/config.py`。
对应模板：`server/.env.example`。

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
| 总结 | `SUMMARY_LANGUAGE` | `中文简体` | 输出语言 |
| 邮件 | `EMAIL_ENABLED` | `false` | |
| 邮件 | `EMAIL_WEBHOOK_URL` | 空 | 收 webhook 的 URL（如 Cloudflare Worker） |
| 邮件 | `EMAIL_WEBHOOK_TOKEN` | 空 | 启用邮件时必填；后端 → Worker 的鉴权 token，与 Worker 端 `BIRI_YOUYAKU_TOKEN` 一致 |
| 邮件 | `EMAIL_DEFAULT_RECIPIENT` | 空 | **唯一**收件人；后端永远只发到这里（无 per-job 收件人，防滥发） |
| 邮件 | `EMAIL_SUBJECT_TEMPLATE` | `[Biri-Youyaku] {{title}}` | 支持 `{{title}}` / `{{author}}` |
| 存储 | `AUDIO_STORAGE_DIR / SUMMARY_STORAGE_DIR / DB_PATH` | `data/...` | |
| 清理 | `AUDIO_RETENTION_DAYS` | `7` | |
| 清理 | `JOB_RETENTION_DAYS` | `180` | |
| 清理 | `ORPHAN_FILE_RETENTION_DAYS` | `3` | DB 不引用的孤儿文件多久后清 |
| 清理 | `STALE_RUNNING_FAIL_HOURS` | `4` | 非终态任务多久无心跳就置 FAILED |
| 清理 | `CLEANUP_INTERVAL_SECONDS` | `3600` | 清理循环周期 |
| 清理 | `WAL_CHECKPOINT_INTERVAL_HOURS` | `24` | WAL 截断周期 |
| 清理 | `DB_VACUUM_INTERVAL_DAYS` | `30` | VACUUM 周期 |
| 并发 | `MAX_CONCURRENT_JOBS` | `2` | `_io_semaphore` 上限：同时跑的「下载音频 + 转写」任务数 |
| 并发 | `MAX_CONCURRENT_SUMMARIES` | `2` | `_summary_semaphore` 上限：同时跑的 LLM 总结任务数 |
| 防滥用 | `MAX_VIDEO_DURATION_SECONDS` | `9000` | 视频时长上限；超长直接拒 |
| 防滥用 | `MAX_INFLIGHT_JOBS` | `20` | 同时在飞任务上限；超出返回 503 |

---

## Configuration

All tunable settings live in `server/.env`; defaults are in
`server/biri_youyaku/config.py`. Template: `server/.env.example`.

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
| Summary | `SUMMARY_LANGUAGE` | `中文简体` | output language |
| Email | `EMAIL_ENABLED` | `false` | |
| Email | `EMAIL_WEBHOOK_URL` | empty | the webhook receiver URL (e.g. a Cloudflare Worker) |
| Email | `EMAIL_WEBHOOK_TOKEN` | empty | required when email is enabled; auth token from backend → worker; must match the worker's `BIRI_YOUYAKU_TOKEN` |
| Email | `EMAIL_DEFAULT_RECIPIENT` | empty | the **only** recipient; backend always sends here (no per-job recipient, anti-abuse) |
| Email | `EMAIL_SUBJECT_TEMPLATE` | `[Biri-Youyaku] {{title}}` | `{{title}}` / `{{author}}` allowed |
| Storage | `AUDIO_STORAGE_DIR / SUMMARY_STORAGE_DIR / DB_PATH` | `data/...` | |
| Cleanup | `AUDIO_RETENTION_DAYS` | `7` | |
| Cleanup | `JOB_RETENTION_DAYS` | `180` | |
| Cleanup | `ORPHAN_FILE_RETENTION_DAYS` | `3` | how long DB-unreferenced files linger |
| Cleanup | `STALE_RUNNING_FAIL_HOURS` | `4` | non-terminal job auto-FAILED after N hours of silence |
| Cleanup | `CLEANUP_INTERVAL_SECONDS` | `3600` | cleanup loop period |
| Cleanup | `WAL_CHECKPOINT_INTERVAL_HOURS` | `24` | WAL checkpoint period |
| Cleanup | `DB_VACUUM_INTERVAL_DAYS` | `30` | VACUUM period |
| Concurrency | `MAX_CONCURRENT_JOBS` | `2` | `_io_semaphore` cap: concurrent "download audio + transcribe" jobs |
| Concurrency | `MAX_CONCURRENT_SUMMARIES` | `2` | `_summary_semaphore` cap: concurrent LLM summarize jobs |
| Abuse | `MAX_VIDEO_DURATION_SECONDS` | `9000` | video length cap; too long → reject |
| Abuse | `MAX_INFLIGHT_JOBS` | `20` | total in-flight jobs; overflow → 503 |
