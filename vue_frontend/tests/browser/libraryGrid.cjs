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
      if (path.endsWith('/actors') || path.endsWith('/genres') || path.endsWith('/resources')) {
        requests.push(url)
        const size = Number(url.searchParams.get('page_size'))
        data = Array.from({ length: size }, (_, i) => ({
          id: i + 1,
          name: 'Actor ' + i,
          avid: 'DEMO-' + i,
          source_title: 'Resource ' + i,
          resource_count: 1,
          downloaded: false,
        }))
        pagination = { total: size * 2, page: 1, page_size: size, pages: 2 }
      }
      return route.fulfill({ json: { code: 200, data, pagination } })
    })
    for (const [path, columns, size] of [
      ['/resources/actors', 5, 15],
      ['/resources/genres', 5, 15],
      ['/resources', 3, 15],
    ]) {
      await page.setViewportSize({ width: 1440, height: 1000 })
      await page.goto((process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178') + path)
      await page.waitForFunction(
        (count) =>
          document.querySelector('.library-grid')?.children.length === count &&
          !document.querySelector('.skeleton-card'),
        size
      )
      assert.equal(requests.at(-1).searchParams.get('page_size'), String(size))
      const boxes = await page.locator('.library-grid > *').evaluateAll((els) =>
        els.map((el) => {
          const r = el.getBoundingClientRect()
          return [Math.round(r.x), Math.round(r.y)]
        })
      )
      assert.equal(new Set(boxes.map(([x]) => x)).size, columns)
      assert.equal(new Set(boxes.map(([, y]) => y)).size, Math.ceil(size / columns))
      if (path === '/resources') {
        const badge = page.getByText('DEMO-0', { exact: true })
        for (const theme of ['dark', 'light']) {
          await page.evaluate((mode) => {
            document.body.classList.remove('dark-mode', 'light-mode')
            document.body.classList.add(mode + '-mode')
          }, theme)
          assert.equal(
            await badge.evaluate((element) => {
              const probe = document.createElement('span')
              probe.style.color = 'var(--accent-primary-text)'
              element.append(probe)
              const matches = getComputedStyle(element).color === getComputedStyle(probe).color
              probe.remove()
              return matches
            }),
            true
          )
        }
      }
      await page.setViewportSize({ width: 390, height: 844 })
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        true
      )
    }
    assert.deepEqual(errors, [])
    console.log(
      'PASS: actors/genres use five columns, resources use three columns, page sizes preserved, mobile no overflow'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
