// Real loopback Django/SQLite sessions. Only the response timing is controlled.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
async function main() {
  const first = process.env.NASSAV_PERSONAL_STORAGE_STATE
  const second = process.env.NASSAV_SECOND_STORAGE_STATE
  if (!first || !second) {
    console.log('SKIP: two disposable login storage states required')
    return
  }
  for (const path of [first, second]) assert.ok(path.startsWith('/tmp/nassav-local-playback-http-'))
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:9780'
  assert.equal(new URL(origin).hostname, '127.0.0.1')
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium
      ? { executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome' }
      : {}
  )
  const timeout = setTimeout(() => {
    console.error('Session browser acceptance timed out')
    process.exitCode = 1
    void browser.close()
  }, 90000)
  const context = await browser.newContext({ storageState: first })
  const api = origin + '/nassav/api'
  let release
  const held = new Promise((resolve) => {
    release = resolve
  })
  let captured
  const ready = new Promise((resolve) => {
    captured = resolve
  })
  const errors = []
  try {
    const initial = await (await context.request.get(api + '/auth/session')).json()
    const headers = async () => ({
      'X-CSRFToken': (await context.cookies(origin)).find((c) => c.name === 'csrftoken').value,
    })
    assert.equal(
      (
        await context.request.put(api + '/setting', {
          data: { color_mode: 'dark' },
          headers: await headers(),
        })
      ).status(),
      200
    )
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    page.on('pageerror', (error) => errors.push(error.message))
    let heldOnce = false
    await page.route('**/nassav/api/setting', async (route) => {
      if (route.request().method() !== 'GET' || heldOnce) return route.continue()
      heldOnce = true
      const response = await route.fetch()
      const body = await response.json()
      assert.equal(body.data.color_mode, 'dark')
      captured()
      await held
      await route.fulfill({ response })
    })
    await page.goto(origin + '/personal/general', { waitUntil: 'domcontentloaded' })
    await ready
    assert.equal(
      (
        await context.request.put(api + '/setting', {
          data: { color_mode: 'light' },
          headers: await headers(),
        })
      ).status(),
      200
    )
    // Replace only this disposable browser's login cookie with its second real session.
    await context.addCookies(JSON.parse(readFileSync(second, 'utf8')).cookies)
    const changed = await (await context.request.get(api + '/auth/session')).json()
    assert.equal(changed.data.user_id, initial.data.user_id)
    assert.notEqual(changed.data.cache_identity, initial.data.cache_identity)
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
    await page.waitForFunction(() => document.body.classList.contains('light-mode'))
    const delivered = page.waitForResponse((response) =>
      response.url().endsWith('/nassav/api/setting')
    )
    release()
    await delivered
    // An actual next event loop and another authoritative read follow the old response.
    await page.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    )
    assert.equal(await page.evaluate(() => document.body.classList.contains('light-mode')), true)
    assert.equal(
      (await (await context.request.get(api + '/setting')).json()).data.color_mode,
      'light'
    )
    assert.deepEqual(errors, [])
    console.log(
      'PASS: real login rotation keeps the current settings and discards a delayed old response'
    )
  } finally {
    clearTimeout(timeout)
    release?.()
    await context.close()
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
