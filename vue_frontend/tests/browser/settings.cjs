const { chromium } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const browser = await chromium.launch({
    executablePath: process.env.NASSAV_CHROMIUM_PATH,
    headless: true,
  })
  try {
    const page = await browser.newPage(),
      errors = [],
      saved = []
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/nassav/api/**', (route) => {
      const request = route.request(),
        path = new URL(request.url()).pathname
      let data = []
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      if (path.endsWith('/setting')) {
        data = { color_mode: 'dark', enable_avatar: 'true', display_title: 'source_title' }
        if (request.method() === 'PUT') saved.push(request.postDataJSON())
      }
      return route.fulfill({ json: { code: 200, data } })
    })
    await page.goto(`${process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'}/settings`)
    await page.getByRole('button', { name: '浅色', exact: true }).click()
    await page.locator('body.light-mode').waitFor()
    const avatar = page.getByRole('switch', { name: '显示女优头像' })
    await avatar.click()
    assert.equal(await avatar.getAttribute('aria-checked'), 'false')
    assert.equal(saved.length, 0)
    await page.getByRole('button', { name: '保存设置', exact: true }).click()
    await page.waitForFunction(
      () =>
        document.body.textContent.includes('设置已保存') ||
        document.body.textContent.includes('保存成功')
    )
    assert.equal(saved.length, 1)
    assert.equal(saved[0].color_mode, 'light')
    assert.equal(saved[0].enable_avatar, 'false')
    await page.setViewportSize({ width: 390, height: 844 })
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    await page.screenshot({ path: '/tmp/nassav-f6-settings-mobile.png', fullPage: true })
    assert.deepEqual(errors, [])
    console.log(
      'PASS: settings emit updates, manual save only, accessible avatar switch and mobile layout'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
