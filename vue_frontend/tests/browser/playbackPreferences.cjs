// Opt-in: real temporary API and synthetic MP4, never deployment credentials.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const storage = process.env.NASSAV_PROGRESS_STORAGE_STATE
  if (!storage) {
    console.log('SKIP: disposable playback API storage state required')
    return
  }
  assert.ok(storage.startsWith('/tmp/nassav-local-playback-http-'))
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
  assert.ok(['127.0.0.1', 'localhost'].includes(new URL(origin).hostname))
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const context = await browser.newContext({ storageState: storage })
  await context.routeWebSocket('**/nassav/ws/**', () => {})
  const page = await context.newPage(),
    errors = [],
    writes = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('request', (request) => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname.endsWith('/setting'))
      writes.push(request.postDataJSON())
  })
  try {
    await context.request.get(origin + '/nassav/api/auth/session')
    const csrf = (await context.cookies()).find((cookie) => cookie.name === 'csrftoken')?.value
    const reset = await context.request.put(origin + '/nassav/api/setting', {
      headers: { 'X-CSRFToken': csrf },
      data: {
        playback_volume: 0.8,
        playback_muted: false,
        playback_rate: 1.25,
        playback_subtitles_enabled: true,
        playback_default_mode: 'auto',
      },
    })
    assert.equal(reset.status(), 200)
    await page.goto(origin + '/settings')
    await page.getByRole('heading', { name: '播放设置', exact: true }).waitFor()
    await page.locator('#playback-volume').fill('0.35')
    await page.getByRole('switch', { name: '默认静音', exact: true }).click()
    await page.getByRole('button', { name: '默认倍速', exact: true }).click()
    await page.getByRole('option', { name: '1.5×', exact: true }).click()
    await page.getByRole('switch', { name: '默认显示字幕', exact: true }).click()
    await page.getByRole('button', { name: '保存设置', exact: true }).click()
    await page.getByText('设置已保存', { exact: true }).waitFor()
    assert.equal(writes.at(-1).playback_volume, 0.35)
    await page.goto(origin + '/play/LOCAL-PLAYBACK')
    await page.waitForFunction(() => document.querySelector('video')?.readyState >= 1)
    const initialWrites = writes.length
    assert.deepEqual(
      await page
        .locator('video')
        .evaluate((video) => [video.volume, video.muted, video.playbackRate]),
      [0.35, true, 1.5]
    )
    await page.waitForTimeout(700)
    assert.equal(writes.length, initialWrites, 'initialization must not write preferences')
    const saved = page.waitForResponse(
      (response) => response.request().method() === 'PUT' && response.url().endsWith('/setting')
    )
    await page.locator('video').evaluate((video) => {
      video.volume = 0.65
      video.muted = false
      video.playbackRate = 1.25
    })
    assert.equal((await saved).status(), 200)
    assert.deepEqual(writes.at(-1), {
      playback_volume: 0.65,
      playback_muted: false,
      playback_rate: 1.25,
    })
    await page.reload()
    await page.waitForFunction(() => document.querySelector('video')?.readyState >= 1)
    assert.deepEqual(
      await page
        .locator('video')
        .evaluate((video) => [video.volume, video.muted, video.playbackRate]),
      [0.65, false, 1.25]
    )
    await page.goto(origin + '/settings')
    await page.getByRole('heading', { name: '播放设置', exact: true }).waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.locator('#playback-volume').scrollIntoViewIfNeeded()
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    await page.screenshot({
      path:
        '/tmp/nassav-playback-preferences-' + (engine === chromium ? 'chrome' : 'firefox') + '.png',
      fullPage: true,
    })
    assert.deepEqual(errors, [])
    console.log(
      'PASS: real API personal playback preferences, initialization no-op, native changes, reload and mobile settings'
    )
  } finally {
    await context.close()
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
