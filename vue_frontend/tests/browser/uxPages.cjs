const { chromium } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const errors = []
    page.on('pageerror', (err) => errors.push(err.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    let pending,
      requests = 0
    await page.route('**/nassav/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/resources')) {
        requests++
        pending = route
        return
      }
      let data = {}
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      if (path.endsWith('/setting')) data = { color_mode: 'dark' }
      return route.fulfill({ json: { code: 200, data } })
    })
    await page.goto((process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178') + '/resources')
    await page.locator('.page-load').waitFor()
    assert.equal(await page.locator('.page-skeleton').count(), 0)
    assert.equal(await page.getByText('暂无资源', { exact: true }).count(), 0)
    await page.locator('.page-skeleton').first().waitFor()
    assert.equal(
      await page
        .locator('.skeleton')
        .first()
        .evaluate((el) => getComputedStyle(el).animationDuration),
      '3.2s'
    )
    const animationStart = await page
      .locator('.skeleton')
      .first()
      .evaluate((el) => el.getAnimations()[0].startTime)
    await page.waitForTimeout(250)
    assert.equal(
      await page
        .locator('.skeleton')
        .first()
        .evaluate((el) => el.getAnimations()[0].startTime),
      animationStart
    )
    await pending.fulfill({ json: { code: 500, message: '资源列表暂时不可用' } })
    await page.getByRole('alert').filter({ hasText: '资源列表暂时不可用' }).waitFor()
    assert.equal(await page.getByText('暂无资源', { exact: true }).count(), 0)
    await page.getByRole('button', { name: '重试', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('.page-load'))
    assert.equal(requests, 2)
    await pending.fulfill({
      json: {
        code: 200,
        data: [{ avid: 'UX-001', source_title: 'UX 验收资源', file_exists: false }],
        pagination: { page: 1, pages: 1, page_size: 15, total: 1 },
      },
    })
    await page.getByText('UX 验收资源', { exact: true }).waitFor()
    await page.locator('.floating-refresh-btn').click()
    await page.locator('.page-load').waitFor()
    assert.equal(await page.getByText('UX 验收资源', { exact: true }).isVisible(), true)
    await pending.fulfill({
      json: { code: 200, data: [], pagination: { page: 1, pages: 1, page_size: 15, total: 0 } },
    })
    await page.getByText('暂无资源', { exact: true }).waitFor()
    await page.goto(
      (process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178') + '/recommendations'
    )
    await page.getByRole('heading', { name: '推荐发现' }).waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    const actions = await page.locator('.header-actions .ui-button').evaluateAll((buttons) =>
      buttons.map((button) => {
        const text = button.querySelector('.ui-button__content')
        return {
          width: button.getBoundingClientRect().width,
          height: text.getBoundingClientRect().height,
          line: Number.parseFloat(getComputedStyle(text).lineHeight),
        }
      })
    )
    assert.equal(actions.length, 5)
    assert.ok(
      actions.every((action) => action.width > 120 && action.height <= action.line * 1.2),
      'mobile actions must keep complete single-line labels'
    )
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    assert.deepEqual(errors, [])
    console.log(
      'PASS: delayed stable skeleton, failure vs empty, retry and preserved content during refresh'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
