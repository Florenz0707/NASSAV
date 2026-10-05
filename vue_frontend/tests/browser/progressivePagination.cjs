const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage(),
      errors = []
    let submitted = 0,
      version = 1,
      state = 'running',
      total = 31
    const items = Array.from({ length: 46 }, (_, i) => ({
      avid: 'EXT-' + i,
      source_title: 'Result ' + i,
      source: 'jable',
    }))
    const snapshot = (p = 1, size = 15) => ({
      task_id: 'same-job',
      token: 'demo',
      state,
      version,
      pages_completed: 2,
      result: {
        data: {
          external_results: items.slice((p - 1) * size, Math.min(p * size, total)),
          external_meta: { partial: state !== 'succeeded', fetch_pages: 5 },
        },
        pagination: { page: p, page_size: size, total, pages: Math.ceil(total / size) },
      },
    })
    page.on('pageerror', (e) => errors.push(e.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', (route) => {
      const request = route.request(),
        url = new URL(request.url()),
        path = url.pathname
      let data = [],
        pagination
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      if (path.endsWith('/setting')) data = { color_mode: 'dark' }
      if (path.endsWith('/actors')) data = [{ id: 1, name: 'Demo actor', resource_count: 0 }]
      if (path.endsWith('/source/search-capabilities'))
        data = [
          { source: 'jable', label: 'Jable', actor: true, genre: true, orderings: ['-views'] },
        ]
      if (path.endsWith('/resources')) pagination = { page: 1, page_size: 18, total: 0, pages: 1 }
      if (path.endsWith('/search/jobs')) {
        submitted++
        data = snapshot()
      }
      if (path.endsWith('/search/jobs/same-job'))
        data = snapshot(
          Number(url.searchParams.get('page') || 1),
          Number(url.searchParams.get('page_size') || 15)
        )
      if (path.endsWith('/search/jobs/same-job/cancel')) {
        state = 'cancelled'
        version++
        data = snapshot()
      }
      return route.fulfill({ json: { code: 200, data, pagination } })
    })
    await page.goto((process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178') + '/actors/1')
    await page.getByRole('button', { name: '外部搜索', exact: true }).click()
    await page.getByRole('button', { name: '开始搜索', exact: true }).click()
    await page.getByText('Result 0', { exact: true }).waitFor()
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.getByText('Result 15', { exact: true }).waitFor()
    assert.equal(await page.locator('.external-search-card').count(), 15)
    total = 46
    version++
    await page.waitForTimeout(1800)
    assert.equal(await page.getByText('Result 15', { exact: true }).isVisible(), true)
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.getByText('Result 30', { exact: true }).waitFor()
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.getByText('Result 45', { exact: true }).waitFor()
    assert.equal(await page.locator('.external-search-card').count(), 1)
    assert.equal(submitted, 1)
    await page.getByRole('button', { name: '取消搜索', exact: true }).click()
    await page.getByText('搜索已取消，已获取的结果仍可查看。', { exact: true }).waitFor()
    await page.getByRole('button', { name: '上一页', exact: true }).click()
    await page.getByText('Result 30', { exact: true }).waitFor()
    assert.equal(submitted, 1)
    assert.deepEqual(errors, [])
    console.log(
      'PASS: browse growing partial pages without restarting; 15 items per page, last item and cancellation browsing'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
