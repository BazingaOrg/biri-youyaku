# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.1.0]

首个开源版本。

### 功能

- 粘贴 B 站视频链接 → 自动取官方字幕，没有则下载音频本地转写（ASR）→ OpenAI 兼容 LLM
  生成 Markdown 摘要，SSE 流式输出。
- 摘要多视图：Markdown 笔记（带目录）、思维导图（mind-elixir，可导出 SVG/PNG）、
  主题标签、字幕原文（时间戳点击跳回视频对应时刻）；可下载 Markdown / SRT 字幕。
- 重复视频按 BV 号去重：粘到已总结过的视频直接复用旧结果，不重复消耗 token。
- 按 UP 主浏览全部投稿：标记哪些已总结，未总结可一键补总结；支持最新/最热排序与标题搜索。
- 历史记录：搜索、按作者 / 标签筛选、删除（带撤销）。
- 可选邮件推送（仓库自带 Cloudflare Worker 模板）。
- 本地 ASR 后端可选：SenseVoice（跨平台 CPU）/ SenseVoice-MLX、Parakeet-MLX（Apple Silicon
  加速）/ faster-whisper。

### 技术

- 后端 FastAPI + SQLite（无 ORM），前端 Vite + React + Tailwind，流式走 SSE。
- 总结 / 邮件由服务端驱动：拿到字幕后自动续跑到完成，关掉浏览器也不影响；任务可重启恢复、
  可取消，邮件失败可重发。
- 数据全部落本地，无遥测；可选 `API_TOKEN` 鉴权；`llm_base_url` 走 SSRF 白名单。
- Docker / Compose 一键部署，`scripts/dev.sh` 本地一键起前后端。
