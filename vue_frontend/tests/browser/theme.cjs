const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    for (const theme of ['dark', 'light']) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
      const errors = []
      await page.routeWebSocket('**/nassav/ws/**', () => {})
      page.on('pageerror', (e) => errors.push(e.message))
      await page.route('**/nassav/api/**', (route) => {
        const path = new URL(route.request().url()).pathname
        let data = {}
        if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
        if (path.endsWith('/setting')) data = { color_mode: theme }
        return route.fulfill({ json: { code: 200, data } })
      })
      await page.goto((process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178') + '/')
      await page.locator('body.' + theme + '-mode').waitFor()
      const results = await page.evaluate(() =>
        [
          ['bg-primary', 'backgroundColor', '--bg-primary'],
          ['bg-secondary', 'backgroundColor', '--bg-secondary'],
          ['text-primary', 'color', '--text-primary'],
          ['text-secondary', 'color', '--text-secondary'],
          ['text-accent-tertiary', 'color', '--accent-tertiary'],
          ['bg-accent-primary', 'backgroundColor', '--accent-primary'],
          ['border-accent-danger/30', 'borderTopColor', '--accent-danger'],
        ].map(([cls, property, token]) => {
          const actual = document.createElement('div'),
            expected = document.createElement('div')
          actual.className = cls
          expected.style[property] = cls.includes('/30')
            ? `color-mix(in oklab, var(${token}) 30%, transparent)`
            : `var(${token})`
          document.body.append(actual, expected)
          const result = [
            cls,
            getComputedStyle(actual)[property],
            getComputedStyle(expected)[property],
          ]
          actual.remove()
          expected.remove()
          return result
        })
      )
      for (const [cls, actual, expected] of results)
        assert.equal(actual, expected, theme + ' ' + cls)
      await page.waitForTimeout(1000)
      const brandGradients = await page.evaluate(() =>
        ['.logo-text', '.home-title'].map(
          (selector) => getComputedStyle(document.querySelector(selector)).backgroundImage
        )
      )
      assert.notEqual(brandGradients[0], 'none')
      assert.equal(
        brandGradients[0],
        brandGradients[1],
        theme + ' home and navigation brand gradient'
      )
      await page.screenshot({ path: '/tmp/nassav-f2-' + theme + '.png', fullPage: true })
      assert.deepEqual(errors, [])
      await page.close()
    }
    console.log('F2 browser PASS: 14 computed token checks, dark/light screenshots, no page errors')
  } finally {
    await browser.close()
  }
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
