const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }),
      requests = [],
      errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', (route) => {
      const url = new URL(route.request().url()),
        path = url.pathname
      let data = [],
        pagination
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      if (path.endsWith('/setting')) data = { color_mode: 'light', enable_avatar: 'false' }
      if (path.endsWith('/actors') || path.endsWith('/resources')) {
        requests.push(url)
        data = Array.from({ length: 15 }, (_, i) => ({
          id: i + 1,
          name: 'Actor ' + i,
          avid: 'DEMO-' + i,
          source_title: 'Resource ' + i,
          resource_count: 1,
          downloaded: false,
        }))
        pagination = { total: 30, page: 1, page_size: 15, pages: 2 }
      }
      return route.fulfill({ json: { code: 200, data, pagination } })
    })
    for (const path of ['/resources/actors', '/resources']) {
      await page.setViewportSize({ width: 1440, height: 1000 })
      await page.goto((process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178') + path)
      await page.waitForFunction(
        () =>
          document.querySelector('.library-grid')?.children.length === 15 &&
          !document.querySelector('.skeleton-card')
      )
      assert.equal(requests.at(-1).searchParams.get('page_size'), '15')
      const boxes = await page.locator('.library-grid > *').evaluateAll((els) =>
        els.map((el) => {
          const r = el.getBoundingClientRect()
          return [Math.round(r.x), Math.round(r.y)]
        })
      )
      assert.equal(new Set(boxes.map(([x]) => x)).size, 5)
      assert.equal(new Set(boxes.map(([, y]) => y)).size, 3)
      await page.setViewportSize({ width: 390, height: 844 })
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        true
      )
    }
    assert.deepEqual(errors, [])
    console.log(
      'PASS: actors/resources request 15 items, desktop five columns by three rows, mobile no overflow'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
