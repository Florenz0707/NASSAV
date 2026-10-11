const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')

async function main() {
  const storage = process.env.NASSAV_LOCAL_PLAYBACK_STORAGE_STATE
  if (!storage) {
    console.log('SKIP: local MP4 real-API check needs an isolated local_playback_server fixture')
    return
  }
  assert.ok(storage.startsWith('/tmp/nassav-local-playback-http-'))
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
  assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(origin).hostname))
  const engine = process.env.NASSAV_BROWSER_ENGINE || 'chromium'
  assert.ok(['chromium', 'firefox'].includes(engine))
  const browser = await (engine === 'firefox' ? firefox : chromium).launch(
    engine === 'firefox' ? {} : { executablePath: '/bin/google-chrome' }
  )
  try {
    const context = await browser.newContext({ storageState: storage })
    const errors = [],
      submissions = [],
      media = []
    context.on('page', (page) => page.on('pageerror', (error) => errors.push(error.message)))
    // The test isolates global hints; playback HTTP/session/Redis remain real.
    await context.routeWebSocket('**/nassav/ws/**', () => {})
    context.on('request', (request) => {
      if (
        request.method() === 'POST' &&
        new URL(request.url()).pathname.endsWith('/playback-sessions')
      )
        submissions.push(request.postDataJSON())
      assert.ok(!request.url().includes('/refresh'), 'local playback cannot refresh a source')
    })
    context.on('response', (response) => {
      if (new URL(response.url()).pathname.endsWith('/file')) media.push(response.status())
    })
    const detail = await context.newPage()
    await detail.goto(`${origin}/resource/LOCAL-PLAYBACK`)
    const created = context.waitForEvent('page')
    await detail.getByRole('button', { name: '点击播放', exact: true }).click()
    const player = await created
    await player.waitForURL(`${origin}/play/LOCAL-PLAYBACK?mode=local`)
    await player.getByText('LOCAL-PLAYBACK · 本地播放', { exact: true }).waitFor()
    await player.locator('video').waitFor()
    await player.waitForFunction(() => document.querySelector('video')?.readyState >= 2, null, {
      timeout: 30000,
    })
    assert.equal(await player.evaluate(() => window.opener), null)
    assert.equal(submissions.length, 1)
    assert.equal(submissions[0].mode, 'local')
    await player.locator('video').evaluate((video) => video.play())
    await player.waitForFunction(() => document.querySelector('video').currentTime > 0.5)
    assert.ok(
      await player
        .locator('video')
        .evaluate(
          (video) => video.videoWidth > 0 && video.getVideoPlaybackQuality().totalVideoFrames > 0
        )
    )
    await player.locator('video').evaluate((video) => {
      video.currentTime = 35
    })
    await player.waitForFunction(() => document.querySelector('video').currentTime > 35.5)
    await player.locator('video').evaluate((video) => video.pause())
    const paused = await player.locator('video').evaluate((video) => video.currentTime)
    await player.waitForTimeout(500)
    assert.ok(
      Math.abs((await player.locator('video').evaluate((video) => video.currentTime)) - paused) <
        0.2
    )
    assert.ok(media.includes(206), 'native MP4 must exercise partial content')
    await player.setViewportSize({ width: 390, height: 844 })
    const geometry = await player
      .getByRole('region', { name: '视频播放器', exact: true })
      .boundingBox()
    assert.ok(Math.abs(geometry.width / geometry.height - 16 / 9) < 0.01)
    assert.equal(await player.locator('nav').count(), 0)
    assert.equal(
      await player.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    const sid = await player
      .locator('video')
      .evaluate((video) => new URL(video.src).pathname.split('/')[4])
    await detail.close()
    assert.equal(await player.locator('video').evaluate((video) => video.paused), true)
    await player.getByRole('link', { name: 'NASSAV', exact: true }).click()
    await player.waitForURL(origin + '/')
    await player.waitForTimeout(400)
    const response = await context.request.get(`${origin}/nassav/api/playback-sessions/${sid}`)
    assert.equal(response.status(), 200)
    assert.equal((await response.json()).data.state, 'closed')
    assert.deepEqual(errors, [])
    await context.close()
    console.log(
      `PASS: ${engine} native MP4 first frame, seek/pause, local tab, mobile frame and close (isolated real API)`
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
