# biri-youyaku Email Worker（Cloudflare Worker + Resend）

把视频总结通过 [Resend](https://resend.com) 发到你邮箱的极小型 Worker。后端通过
`EMAIL_WEBHOOK_URL` POST 调用它；与 `BIRI_YOUYAKU_TOKEN` 鉴权后转发到 Resend API。

## 部署步骤

1. 装 [wrangler](https://developers.cloudflare.com/workers/wrangler/install-and-update/)：

   ```bash
   npm i -g wrangler
   wrangler login
   ```

2. 注册 Resend，验证一个发件域名，拿到 `RESEND_API_KEY`：
   <https://resend.com/api-keys>

3. 在本目录运行：

   ```bash
   wrangler deploy
   # 部署后给三个 secret：
   wrangler secret put BIRI_YOUYAKU_TOKEN   # 与后端 EMAIL_WEBHOOK_TOKEN 一致
   wrangler secret put RESEND_API_KEY       # Resend 控制台拿
   wrangler secret put RESEND_FROM          # 例如 "Biri-Youyaku <noreply@your-domain.com>"
   ```

4. 拷贝 Worker URL（形如 `https://biri-youyaku-mail.<account>.workers.dev`），写到后端 `.env`：

   ```env
   EMAIL_ENABLED=true
   EMAIL_WEBHOOK_URL=https://biri-youyaku-mail.<account>.workers.dev
   EMAIL_WEBHOOK_TOKEN=与 BIRI_YOUYAKU_TOKEN 一致的字符串
   EMAIL_DEFAULT_RECIPIENT=you@example.com
   ```

5. 起后端，跑一个总结，验证邮箱能收到。
