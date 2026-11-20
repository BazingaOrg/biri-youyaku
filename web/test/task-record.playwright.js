// Run with the same isolated build as navigation-roundtrip.playwright.js.
async (page) => {
  const base = 'http://127.0.0.1:42731'
  const jobs = [{id: 'job1', created_at: 1710000000000, read_id: 'doc1', status: 'COMPLETED', title: '已完成', chapters: [], transcript: [], options: {}, stage_timings: []}]
  let deletes = 0
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.origin !== base) return route.abort()
    if (!url.pathname.startsWith('/mock-api/')) return route.continue()
    let data = {ok: true, items: [], jobs: [], defaults: {}}
    if (url.pathname.endsWith('/jobs') && !url.searchParams.has('active_only')) data.jobs = jobs
    if (url.pathname.endsWith('/jobs/job1')) {
      if (route.request().method() === 'DELETE') { deletes++; jobs.length = 0 }
      else data.job = jobs[0]
    }
    if (url.pathname.endsWith('/content')) data = {document: {id: 'doc1', job_id: 'job1', title: '测试笔记'}, summary: {markdown: '正文'}, transcript: [{text: '字幕', start: 5, end: 8}]}
    await route.fulfill({json: data})
  })
  await page.goto(base)
  await page.locator('a[href="/tasks"]').first().click()
  const del = page.getByRole('button', {name: '删除', exact: true})
  await del.click()
  await page.getByRole('link', {name: '全部笔记', exact: true}).click()
  await page.getByRole('button', {name: '撤销', exact: true}).click()
  await page.locator('a[href="/tasks"]').first().click()
  await page.getByRole('link', {name: '阅读笔记'}).click()
  await page.getByRole('tab', {name: '字幕'}).click()
  const reader = page.url()
  await page.getByRole('button', {name: '更多操作'}).click()
  await page.getByRole('link', {name: '处理记录'}).click()
  await page.getByRole('link', {name: '返回笔记'}).click()
  await page.waitForURL(reader)
  await page.getByRole('tab', {name: '字幕', selected: true}).waitFor()
  await page.waitForTimeout(5100)
  if (deletes !== 0) throw Error('撤销后仍发送了删除请求')
  await page.locator('a[href="/tasks"]').first().click()
  await del.click()
  await page.getByRole('link', {name: '全部笔记', exact: true}).click()
  if (deletes !== 0) throw Error('离页提前提交删除')
  await page.waitForTimeout(5300)
  if (deletes !== 1) throw Error('到期应只删除一次')
  return {undoRequests: 0, expiredRequests: deletes, reader}
}
