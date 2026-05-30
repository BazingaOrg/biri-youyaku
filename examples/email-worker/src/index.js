// biri-youyaku email worker：把后端发来的 markdown 摘要转发到 Resend。
// 部署见同目录 README.md。

const cors = (origin) => ({
  'Access-Control-Allow-Origin': origin || '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
})

function json(status, body, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {'Content-Type': 'application/json', ...extra},
  })
}

function mdToHtml(md) {
  // 极简 markdown → HTML（标题、加粗、链接、列表、换行）。够邮件可读。
  return md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2">$1</a>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/^(?!<)/gm, '<p>')
    .replace(/$/gm, '</p>')
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '*'
    if (request.method === 'OPTIONS') {
      return new Response(null, {status: 204, headers: cors(origin)})
    }
    if (request.method !== 'POST') {
      return json(405, {error: 'Method Not Allowed'}, cors(origin))
    }

    // 鉴权：与后端 EMAIL_WEBHOOK_TOKEN 一致才放行
    const auth = request.headers.get('Authorization') || ''
    const expected = `Bearer ${env.BIRI_YOUYAKU_TOKEN || ''}`
    if (!env.BIRI_YOUYAKU_TOKEN || auth !== expected) {
      return json(401, {error: 'Unauthorized'}, cors(origin))
    }

    let payload
    try {
      payload = await request.json()
    } catch {
      return json(400, {error: 'Invalid JSON body'}, cors(origin))
    }

    const {to, subject, markdown, videoMeta} = payload || {}
    if (!to || !subject || !markdown) {
      return json(400, {error: 'Missing required fields: to, subject, markdown'}, cors(origin))
    }

    const html = `
<!doctype html>
<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;line-height:1.6;color:#1a1a1a;max-width:680px;margin:0 auto;padding:24px;">
  ${videoMeta?.url ? `<p style="color:#666;font-size:13px;">📺 <a href="${videoMeta.url}" style="color:#5B6DF0;">${videoMeta.title || '原视频'}</a> · ${videoMeta.author || ''}</p>` : ''}
  ${mdToHtml(markdown)}
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
  <p style="color:#999;font-size:12px;">由 biri-youyaku 生成</p>
</body></html>`.trim()

    const resendResp = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: env.RESEND_FROM,
        to: [to],
        subject,
        html,
        text: markdown,
      }),
    })

    if (!resendResp.ok) {
      const text = await resendResp.text()
      return json(502, {error: `Resend returned ${resendResp.status}: ${text.slice(0, 500)}`}, cors(origin))
    }
    return json(200, {ok: true}, cors(origin))
  },
}
