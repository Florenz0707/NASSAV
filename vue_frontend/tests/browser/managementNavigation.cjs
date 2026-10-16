const assert = require('node:assert/strict')
const { chromium } = require('playwright')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage()
    const errors = []
    let admin = true
    page.on('pageerror', (error) => errors.push(error.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      let data = []
      if (path.endsWith('/auth/session'))
        data = {
          authenticated: true,
          username: 'nav-audit',
          cache_identity: admin ? 'admin' : 'ordinary',
          capabilities: { app_admin: admin, shared_library: true },
        }
      if (path.endsWith('/setting')) data = { color_mode: 'dark' }
      await route.fulfill({
        json: { code: 200, data, pagination: { page: 1, pages: 1, total: 0 } },
      })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4196'
    for (const width of [1440, 1024, 768, 390]) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto(origin + '/personal/general')
      await page.getByRole('heading', { name: '个人中心', exact: true }).waitFor()
      assert.equal(
        await page.getByRole('navigation', { name: '个人中心功能' }).getByText('管理中心').count(),
        0
      )
      if (width < 768) await page.getByRole('button', { name: '菜单', exact: true }).click()
      const link = page
        .getByRole('link', { name: '管理中心', exact: true })
        .filter({ visible: true })
      await link.waitFor()
      assert.equal(
        await link.evaluate((node) => node === node.parentElement.lastElementChild),
        true
      )
      const box = await link.boundingBox()
      assert.ok(
        box.x >= 0 && box.x + box.width <= width + 1,
        `management link overflows at ${width}`
      )
      await link.focus()
      await page.keyboard.press('Enter')
      await page.getByRole('heading', { name: '管理中心', exact: true }).waitFor()
      if (width < 768) {
        assert.equal(
          await page
            .getByRole('button', { name: '菜单', exact: true })
            .getAttribute('aria-expanded'),
          'false'
        )
        await page.getByRole('button', { name: '菜单', exact: true }).click()
      }
      assert.match(
        await page
          .getByRole('link', { name: '管理中心', exact: true })
          .filter({ visible: true })
          .getAttribute('class'),
        /active/
      )
    }
    admin = false
    await page.goto(origin + '/personal/general')
    await page.getByRole('heading', { name: '个人中心', exact: true }).waitFor()
    await page.getByRole('button', { name: '菜单', exact: true }).click()
    assert.equal(await page.getByRole('link', { name: '管理中心', exact: true }).count(), 0)
    assert.deepEqual(errors, [])
    console.log(
      'PASS: admin-only management link is last, accessible, active and visible on desktop/mobile; personal duplicate removed'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
