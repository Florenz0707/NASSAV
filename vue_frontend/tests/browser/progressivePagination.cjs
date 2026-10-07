const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage(),
      errors = []
    let delayPage = true
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
    await page.route('**/nassav/api/**', async (route) => {
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
      if (
        path.endsWith('/search/jobs/same-job') &&
        url.searchParams.get('page') === '2' &&
        delayPage
      ) {
        delayPage = false
        data = structuredClone(data)
        data.result.data.external_results[0].source_title = 'Stale result'
        version++
        await new Promise((resolve) => setTimeout(resolve, 2200))
      }
      return route.fulfill({ json: { code: 200, data, pagination } })
    })
    await page.goto((process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178') + '/actors/1')
    await page.getByRole('button', { name: '外部搜索', exact: true }).click()
    const initial = page.getByRole('button', { name: '开始搜索', exact: true })
    await initial.waitFor()
    const center = await initial.evaluate((button) => {
      const area = button.parentElement.parentElement
      const box = area.getBoundingClientRect(),
        control = button.parentElement.getBoundingClientRect()
      return {
        center: control.top + control.height / 2,
        expected: box.top + box.height / 2,
        bottom: box.bottom,
        height: window.innerHeight,
      }
    })
    assert(Math.abs(center.center - center.expected) < 2)
    assert(center.bottom <= center.height)
    assert(center.bottom > center.height - 80)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(100)
    const mobileCenter = await initial.evaluate((button) => {
      const area = button.parentElement.parentElement.getBoundingClientRect(),
        control = button.parentElement.getBoundingClientRect()
      return {
        delta: Math.abs(control.top + control.height / 2 - (area.top + area.height / 2)),
        bottom: area.bottom,
        viewport: window.innerHeight,
      }
    })
    assert(mobileCenter.delta < 2)
    assert(mobileCenter.bottom <= mobileCenter.viewport)
    assert(mobileCenter.bottom > mobileCenter.viewport - 80)
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    await page.setViewportSize({ width: 1280, height: 720 })
    await initial.click()
    await page.getByText('Result 0', { exact: true }).waitFor()
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.getByText('Result 15', { exact: true }).waitFor()
    await page.waitForTimeout(1000)
    assert.equal(await page.getByText('Stale result', { exact: true }).count(), 0)
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
    assert.equal(await page.getByRole('button', { name: '刷新外部结果', exact: true }).count(), 0)
    const restart = page.getByRole('button', { name: '重新搜索', exact: true })
    const next = page.getByRole('button', { name: '下一页', exact: true })
    const placement = await restart.evaluate((button) => {
      const box = button.parentElement.getBoundingClientRect(),
        own = button.getBoundingClientRect()
      return {
        centered: Math.abs(own.left + own.width / 2 - (box.left + box.width / 2)),
        top: box.top,
      }
    })
    assert(placement.centered < 30)
    assert(placement.top > (await next.boundingBox()).y)
    await restart.click()
    await page.getByText('Result 0', { exact: true }).waitFor()
    assert.equal(submitted, 2)
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
