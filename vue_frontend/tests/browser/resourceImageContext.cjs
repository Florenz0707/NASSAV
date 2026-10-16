const assert = require('node:assert/strict')
const { chromium, firefox } = require('playwright')
;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: process.env.NASSAV_CHROMIUM_PATH } : {}
  )
  try {
    const page = await browser.newPage()
    const images = [],
      errors = []
    let context = 'image-login-a'
    page.on('pageerror', (error) => errors.push(error.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', async (route) => {
      const url = new URL(route.request().url()),
        path = url.pathname
      let data = [],
        pagination
      if (path.endsWith('/auth/session'))
        data = {
          authenticated: true,
          username: 'image-audit',
          cache_identity: context,
          capabilities: { shared_library: true, source_credentials: true, ordinary_login: true },
        }
      if (path.endsWith('/setting')) data = { color_mode: 'light', enable_avatar: false }
      if (path.endsWith('/resource/cover')) {
        images.push(url)
        const allowed =
          url.searchParams.getAll('_context').length === 1 &&
          url.searchParams.get('_context') === context
        return route.fulfill(
          allowed
            ? {
                contentType: 'image/svg+xml',
                body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90"><rect width="160" height="90"/></svg>',
              }
            : { status: 409, json: { code: 409, data: { error_code: 'browser_context_changed' } } }
        )
      }
      if (path.endsWith('/resources')) {
        data = [
          {
            avid: 'YUJ-036',
            source_title: '封面上下文验收',
            membership_state: 'active',
            entry_id: 'entry-one',
            thumbnail_url: '/nassav/api/resource/cover?avid=YUJ-036&size=small&v=version-one',
          },
        ]
        pagination = { page: 1, page_size: 15, total: 1, pages: 1 }
      }
      if (path.endsWith('/my-operations')) {
        data = [
          {
            operation_id: '10000000-0000-4000-8000-000000000001',
            avid: 'YUJ-036',
            kind: 'scrape',
            action: 'add',
            state: 'succeeded',
            stage: 'succeeded',
            version: 1,
            allowed_actions: [],
            created_at: '2026-10-16T00:00:00Z',
            updated_at: '2026-10-16T00:00:01Z',
          },
        ]
        pagination = { page: 1, pages: 1, total: 1 }
      }
      await route.fulfill({ json: { code: 200, data, ...(pagination ? { pagination } : {}) } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4196'
    for (const value of ['image-login-a', 'image-login-b']) {
      context = value
      await page.goto(origin + '/resources')
      await page.waitForFunction(
        () =>
          [...document.querySelectorAll('.library-grid img')].some(
            (image) => image.complete && image.naturalWidth > 0
          ),
        null,
        { timeout: 8000 }
      )
      const request = images.at(-1)
      assert.equal(request.searchParams.get('_context'), value)
      assert.equal(request.searchParams.get('size'), 'small')
      assert.equal(request.searchParams.get('v'), 'version-one')
      await page.locator('a[href="/downloads"]').first().click()
      await page
        .getByRole('button', { name: /查看任务明细/ })
        .first()
        .click()
      await page.waitForFunction(
        () =>
          [...document.querySelectorAll('img')].some(
            (image) =>
              image.src.includes('avid=YUJ-036') && image.complete && image.naturalWidth > 0
          ),
        null,
        { timeout: 8000 }
      )
      assert.equal(images.at(-1).searchParams.get('_context'), value)
    }
    assert.deepEqual(errors, [])
    console.log(
      'PASS: server-provided cover URLs carry the current login context; size/version preserved across login changes'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
