// Run with playwright-cli run-code --filename against an isolated build served at
// 127.0.0.1:42731 with VITE_API_BASE_URL=/mock-api and VITE_API_TOKEN empty.
async (page) => {
  const base = 'http://127.0.0.1:42731'
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (url.origin !== base) return route.abort()
    if (!url.pathname.startsWith('/mock-api/')) return route.continue()
    const rows = Array.from({length: 30}, (_, i) => i + 1)
    let data = {ok: true, items: [], jobs: [], total: 0}
    if (url.pathname.endsWith('/library/search')) {
      const offset = url.searchParams.has('cursor') ? 30 : 0
      data = {
        query: url.searchParams.get('q'), next_cursor: offset ? null : 'second',
        groups: rows.map(i => ({
          document_id: String(i + offset), title: 'sample ' + (i + offset),
          author: i === 1 ? '匿名作者' : '测试作者', mid: i === 1 ? null : 42,
        })),
      }
    } else if (url.pathname.endsWith('/videos')) {
      const n = Number(url.searchParams.get('page'))
      data = {
        author: '测试作者', page: n, has_more: n === 1, total: 60,
        videos: rows.map(i => {
          const id = String(i + (n - 1) * 30)
          return {title: [url.searchParams.get('keyword'), url.searchParams.get('order'), id].join(' '), bvid: 'BV' + id, document_id: id, status: 'COMPLETED', pubdate: 1, duration: 5}
        }),
      }
    } else if (url.pathname.endsWith('/content')) {
      data = {document: {id: '55', title: '测试笔记', mid: 42}, summary: {markdown: '测试正文'}}
    }
    await route.fulfill({json: data})
  })

  await page.setViewportSize({width: 390, height: 844})
  await page.goto(base)
  const query = `sample-${Date.now()}`
  const box = page.getByRole('searchbox')
  await box.fill(query)
  await box.press('Enter')
  await page.getByRole('button', {name: '查看更多结果'}).click()
  const result = page.getByRole('link', {name: 'sample 55', exact: true})
  await result.scrollIntoViewIfNeeded()
  const y = () => page.evaluate(() => window.scrollY)
  const searchY = await y()
  await result.click()
  await page.getByRole('link', {name: `搜索「${query}」`}).click()
  await result.waitFor()
  await page.waitForFunction(expected => Math.abs(scrollY - expected) <= 2, searchY)
  await result.click()
  await page.getByRole('link', {name: `搜索「${query}」`}).waitFor()
  await page.goBack()
  await result.waitFor()
  await page.waitForFunction(expected => Math.abs(scrollY - expected) <= 2, searchY)
  if (await page.getByRole('link', {name: '匿名作者'}).count()) throw Error('无 MID 的作者出现了链接')
  await page.getByRole('link', {name: '测试作者'}).first().click()
  await page.waitForURL('**/?up=42')
  await page.getByRole('link', {name: '浏览 TA 的全部投稿'}).click()

  const keyword = '学习 & C++'
  await page.getByPlaceholder('在该 UP 的投稿里搜标题').fill(keyword)
  await page.getByRole('button', {name: '最热'}).click()
  const read = page.getByRole('link', {name: '阅读笔记'})
  await page.getByText(keyword + ' click 30', {exact: true}).first().waitFor()
  await read.nth(29).scrollIntoViewIfNeeded()
  await read.nth(54).waitFor()
  await page.getByRole('button', {name: /^已总结/}).click()
  await read.nth(54).scrollIntoViewIfNeeded()
  const catalogY = await y()
  await read.nth(54).click()
  await page.getByRole('link', {name: '返回投稿列表'}).click()
  await read.nth(54).waitFor()
  await page.waitForFunction(expected => Math.abs(scrollY - expected) <= 2, catalogY)
  const restored = new URL(page.url()).searchParams
  if (restored.get('q') !== keyword || restored.get('filter') !== 'done' || restored.get('order') !== 'click') {
    throw Error('投稿筛选条件未恢复')
  }
  return {searchY, catalogY, catalogRows: await read.count()}
}
