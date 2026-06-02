# 安全策略

## 报告漏洞

请**不要**在公开 issue 中提交安全漏洞。请走 GitHub Security Advisories 私有渠道：

仓库页 → **Security** 选项卡 → **Report a vulnerability**

会尽量在一周内回复。

## 范围

属于安全范畴的问题（按优先级降序）：

- 服务端任意命令执行 / 路径穿越 / SSRF
- 鉴权绕过、Bearer Token 泄漏
- 任意文件读写、上传字幕/音频带来的解析层 RCE
- 任意用户的 SQLite 数据被未授权访问
- 通过任务参数注入恶意 prompt 导致后端凭据外泄

下列**不属于**本仓库安全范畴：

- `VITE_API_TOKEN` 出现在前端 bundle —— 这是预期行为（README 已说明），公网部署请叠 Vercel Protection / Cloudflare Access。
- LLM 输出可能含幻觉、错误或不当内容 —— 模型本身的问题，请上游反馈。
- 本地部署因 `API_TOKEN` 留空而无鉴权 —— 默认仅适合本机，公网部署务必配上。

## 第三方依赖

发现依赖（FastAPI / Vite / yt-dlp / openai-python …）的 CVE，欢迎一并报上来，
但请先去对应上游确认。我这边只能跟随升级。
