const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: process.env.NASSAV_CHROMIUM_PATH } : {}
  )
  try {
    const context = await browser.newContext(),
      errors = []
    let data = {
        color_mode: 'dark',
        font_family: 'Mplus2',
        enable_avatar: 'true',
        display_title: 'source_title',
      },
      gets = 0
    await context.routeWebSocket('**/nassav/ws/**', () => {})
    await context.route('**/nassav/api/**', (route) => {
      const request = route.request(),
        path = new URL(request.url()).pathname
      let value = []
      if (path.endsWith('/auth/session'))
        value = { authenticated: true, username: 'audit', cache_identity: 'cache-user' }
      if (path.endsWith('/setting')) {
        if (request.method() === 'PUT') data = { ...data, ...request.postDataJSON() }
        else gets++
        value = data
      }
      return route.fulfill({
        json: { code: 200, data: value, pagination: { page: 1, pages: 1, total: 0 } },
      })
    })
    const first = await context.newPage(),
      second = await context.newPage()
    for (const page of [first, second]) {
      page.on('pageerror', (e) => errors.push(e.message))
      await page.goto((process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4196') + '/settings')
      await page.locator('body.dark-mode').waitFor()
    }
    assert.equal(gets, 2)
    await first.evaluate(async () => {
      const { useSettingsStore } = await import('/src/features/settings/stores/settings.js')
      const store = useSettingsStore()
      await store.loadSettings()
      await store.loadSettings()
    })
    assert.equal(gets, 2)
    await second.bringToFront()
    await first.evaluate(async () => {
      const { useSettingsStore } = await import('/src/features/settings/stores/settings.js')
      const store = useSettingsStore()
      store.colorMode = 'light'
      await store.saveSettings('general')
    })
    await second.locator('body.light-mode').waitFor()
    assert.equal(gets, 3)
    await second.evaluate(async () => {
      const { useSettingsStore } = await import('/src/features/settings/stores/settings.js')
      useSettingsStore().fontFamily = 'local-draft'
    })
    await first.evaluate(async () => {
      const { useSettingsStore } = await import('/src/features/settings/stores/settings.js')
      const store = useSettingsStore()
      store.fontFamily = 'ZenKakuGothicNew'
      await store.saveSettings('general')
    })
    await second.waitForTimeout(150)
    assert.equal(
      await second.evaluate(async () => {
        const { useSettingsStore } = await import('/src/features/settings/stores/settings.js')
        return useSettingsStore().fontFamily
      }),
      'local-draft'
    )
    assert.equal(gets, 3)
    assert.deepEqual(errors, [])
    console.log(
      'PASS: App cross-tab settings invalidation; fresh reads reuse cache; unsaved local draft survives remote save (isolated API)'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
