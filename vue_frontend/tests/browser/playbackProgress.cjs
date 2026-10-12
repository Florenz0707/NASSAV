// Opt-in: requires the disposable real API in tests/helpers/local_playback_server.py.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  if (!process.env.NASSAV_PROGRESS_STORAGE_STATE) {
    console.log('Playback progress real API check skipped: disposable storage state required')
    return
  }
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium
      ? { executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome' }
      : {}
  )
  const context = await browser.newContext({
    storageState: process.env.NASSAV_PROGRESS_STORAGE_STATE,
  })
  await context.routeWebSocket('**/nassav/ws/**', () => {})
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
  const errors = [],
    ids = []
  context.on('page', (page) => {
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('response', async (response) => {
      if (
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname.endsWith('/playback-sessions')
      ) {
        const json = await response.json().catch(() => null)
        if (json?.data?.session_id) ids.push(json.data.session_id)
      }
    })
  })
  const progress = async (id) => {
    const response = await context.request.get(
      `${origin}/nassav/api/playback-sessions/${id}/progress`
    )
    const body = await response.json()
    return body.data
  }
  const until = async (check) => {
    for (let i = 0; i < 100; i++) {
      if (await check()) return
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    throw new Error('Timed out waiting for progress assertion')
  }
  const seekPause = async (page, position) => {
    await page.locator('video').evaluate(async (video, target) => {
      await video.play()
      video.currentTime = target
      await new Promise((resolve) => video.addEventListener('seeked', resolve, { once: true }))
      video.pause()
    }, position)
  }
  try {
    const page = await context.newPage()
    await page.goto(`${origin}/play/LOCAL-PLAYBACK?mode=local`)
    await page.waitForFunction(() => document.querySelector('video')?.readyState >= 1)
    await seekPause(page, 30)
    await until(async () => (await progress(ids.at(-1)))?.position_seconds >= 30)
    await page.reload()
    await page.getByRole('group', { name: '恢复播放进度' }).waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    const frame = await page.getByRole('region', { name: '视频播放器' }).boundingBox()
    assert.ok(Math.abs(frame.width / frame.height - 16 / 9) < 0.05)
    const resume = page.getByRole('button', { name: '继续上次播放' })
    await resume.focus()
    await page.keyboard.press('Enter')
    await page.waitForFunction(() => document.querySelector('video')?.currentTime >= 30)
    await page.locator('video').evaluate((video) => video.pause())
    const oldId = ids.at(-1)
    const other = await context.newPage()
    await other.goto(`${origin}/play/LOCAL-PLAYBACK?mode=local`)
    await other.getByRole('button', { name: '从头播放' }).click()
    await other.locator('video').evaluate((video) => video.pause())
    const otherId = ids.at(-1)
    await until(async () => (await progress(otherId))?.position_seconds < 5)
    await seekPause(page, 40)
    await page.getByRole('status').filter({ hasText: '进度保存权已失效' }).waitFor()
    assert.ok((await progress(otherId)).position_seconds < 5)
    const cleared = await other.evaluate(async () => {
      const csrf = document.cookie
        .split('; ')
        .find((v) => v.startsWith('csrftoken='))
        ?.slice(10)
      return (
        await fetch('/nassav/api/resources/LOCAL-PLAYBACK/playback-progress', {
          method: 'DELETE',
          headers: { 'X-CSRFToken': decodeURIComponent(csrf || '') },
        })
      ).status
    })
    assert.equal(cleared, 200)
    await seekPause(other, 20)
    await other.getByRole('status').filter({ hasText: '进度保存权已失效' }).waitFor()
    assert.equal((await progress(otherId)).position_seconds, 0)
    await page.close()
    await other.close()
    await until(async () => {
      const response = await context.request.get(`${origin}/nassav/api/playback-sessions/${oldId}`)
      return (await response.json()).data?.state === 'closed'
    })
    const final = await context.newPage()
    await final.goto(`${origin}/play/LOCAL-PLAYBACK?mode=local`)
    await final.waitForFunction(() => document.querySelector('video')?.readyState >= 1)
    await seekPause(final, 55)
    const finalId = ids.at(-1)
    await until(async () => (await progress(finalId))?.position_seconds >= 55)
    await final.goto(`${origin}/`)
    await final.goto(`${origin}/play/LOCAL-PLAYBACK?mode=local`)
    await final.getByRole('button', { name: '继续上次播放' }).click()
    await final.waitForFunction(() => document.querySelector('video')?.currentTime >= 55)
    await final.locator('video').evaluate((video) => {
      video.currentTime = video.duration - 0.2
    })
    await final.waitForFunction(() => document.querySelector('video')?.ended)
    await until(async () => (await progress(ids.at(-1)))?.completed === true)
    await final.reload()
    await final.waitForFunction(() => document.querySelector('video')?.readyState >= 1)
    assert.equal(await final.getByRole('group', { name: '恢复播放进度' }).count(), 0)
    await final.close()
    const unavailable = await context.newPage()
    await unavailable.route('**/playback-sessions/*/progress', (route) =>
      route.request().method() === 'GET'
        ? route.fulfill({ status: 503, json: { code: 503 } })
        : route.continue()
    )
    await unavailable.goto(`${origin}/play/LOCAL-PLAYBACK?mode=local`)
    await unavailable.waitForFunction(() => document.querySelector('video')?.readyState >= 1)
    await unavailable.locator('video').evaluate((video) => video.play())
    await unavailable.waitForFunction(() => document.querySelector('video')?.currentTime > 0.1)
    await unavailable.getByRole('status').filter({ hasText: '无法读取播放进度' }).waitFor()
    await unavailable.close()
    assert.deepEqual(errors, [])
    console.log(
      'Real API progress: reload/keyboard/mobile, backward seek, takeover, clear, route leave and completed passed'
    )
  } finally {
    // Closing a browser document cannot guarantee delivery; clean only sessions
    // created by this disposable test through the real authorized close API.
    const csrf = (await context.cookies()).find((value) => value.name === 'csrftoken')?.value
    for (const id of ids) {
      const response = await context.request.get(`${origin}/nassav/api/playback-sessions/${id}`)
      const row = (await response.json()).data
      if (row && row.state !== 'closed')
        await context.request.post(`${origin}/nassav/api/playback-sessions/${id}/close`, {
          headers: { 'X-CSRFToken': csrf || '' },
          data: { expected_version: row.version, request_id: crypto.randomUUID() },
        })
    }
    await context.close()
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
