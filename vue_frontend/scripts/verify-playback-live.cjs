// Opt-in: existing resources and an explicitly supplied temporary login only.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
let stage = 'setup',
  currentAvid = ''
async function main() {
  const origin = process.env.NASSAV_PLAYBACK_TEST_ORIGIN
  const stateFile = process.env.NASSAV_PLAYBACK_TEST_LOGIN
  const targets = (process.env.NASSAV_PLAYBACK_TEST_AVIDS || '').split(',').filter(Boolean)
  const seconds = Number(process.env.NASSAV_PLAYBACK_TEST_SECONDS || 30)
  assert.ok(
    origin && stateFile && targets.length === 2,
    'Set origin, temporary storage-state file and exactly two existing AVIDs'
  )
  assert.ok(seconds >= 15 && seconds <= 300)
  const state = JSON.parse(readFileSync(stateFile, 'utf8'))
  const engine = process.env.NASSAV_PLAYBACK_TEST_ENGINE || 'chromium'
  assert.ok(['chromium', 'firefox'].includes(engine), 'Unsupported test engine')
  const selfSigned = process.env.NASSAV_PLAYBACK_TEST_SELF_SIGNED === 'true'
  if (selfSigned) {
    const target = new URL(origin)
    assert.ok(
      target.protocol === 'https:' && ['localhost', '127.0.0.1', '[::1]'].includes(target.hostname),
      'Self-signed exception is restricted to an isolated loopback HTTPS test'
    )
  }
  const browser = await (engine === 'firefox' ? firefox : chromium).launch(
    engine === 'firefox'
      ? {}
      : {
          executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome',
          args: ['--disable-features=LocalNetworkAccessChecks'],
        }
  )
  const context = await browser.newContext({ storageState: state, ignoreHTTPSErrors: selfSigned })
  if (process.env.NASSAV_PLAYBACK_TEST_MSE === 'true')
    await context.addInitScript(() => {
      const original = HTMLMediaElement.prototype.canPlayType
      HTMLMediaElement.prototype.canPlayType = function (type) {
        return type.includes('mpegurl') ? '' : original.call(this, type)
      }
    })
  const sessions = []
  async function play(page) {
    await page.locator('video').evaluate(async (video) => {
      let timer
      try {
        await Promise.race([
          video.play(),
          new Promise((_, reject) => {
            timer = setTimeout(() => reject(new Error('play timed out')), 60000)
          }),
        ])
      } finally {
        clearTimeout(timer)
      }
    })
  }
  async function command(page, id, action) {
    const csrf = await page.evaluate(() =>
      document.cookie
        .split('; ')
        .find((c) => c.startsWith('csrftoken='))
        ?.slice(10)
    )
    const requestId = require('node:crypto').randomUUID()
    for (let attempt = 0; attempt < 4; attempt++) {
      const row = await (
        await page.request.get(`${origin}/nassav/api/playback-sessions/${id}`)
      ).json()
      if (action === 'close' && ['closed', 'failed'].includes(row.data?.state)) return row.data
      const response = await page.request.post(
        `${origin}/nassav/api/playback-sessions/${id}/${action}`,
        {
          headers: { 'X-CSRFToken': csrf || '', Origin: origin },
          data: { expected_version: row.data.version, request_id: requestId },
        }
      )
      if (response.status() === 409 && attempt < 3) continue
      assert.ok([200, 202].includes(response.status()), `${action} returned ${response.status()}`)
      return (await response.json()).data
    }
  }
  try {
    for (const avid of targets) {
      currentAvid = avid
      stage = 'open'
      const page = await context.newPage()
      let sessionId, framesBefore, firstFrameMs
      page.on('response', async (response) => {
        if (
          /\/(manifest|assets)\//.test(new URL(response.url()).pathname) &&
          response.status() >= 400
        ) {
          const error = await response.json().catch(() => ({}))
          console.log(
            JSON.stringify({ avid, media_status: response.status(), code: error.message })
          )
        }
        if (
          response.request().method() === 'POST' &&
          response.url().endsWith('/playback-sessions') &&
          response.status() === 202
        ) {
          const data = (await response.json()).data
          sessionId = data.session_id
          if (!sessions.some((s) => s.id === sessionId)) sessions.push({ page, id: sessionId })
        }
      })
      await page.goto(`${origin}/resource/${encodeURIComponent(avid)}`)
      await page.getByRole('button', { name: '在线播放', exact: true }).click()
      const started = Date.now()
      stage = 'prepare'
      await page.locator('video').waitFor({ timeout: 320000 })
      await page.waitForFunction(
        () => !!document.querySelector('video')?.getAttribute('src'),
        null,
        {
          timeout: 60000,
        }
      )
      await play(page)
      await page.waitForFunction(() => document.querySelector('video')?.currentTime > 0.5, null, {
        timeout: 60000,
      })
      firstFrameMs = Date.now() - started
      framesBefore = await page
        .locator('video')
        .evaluate((video) => video.getVideoPlaybackQuality().totalVideoFrames)
      assert.ok(framesBefore > 0, 'must decode frames')
      stage = 'seek'
      const target = await page.locator('video').evaluate((video) => {
        const time = Math.min(120, video.duration / 2)
        video.currentTime = time
        return time
      })
      await page.waitForFunction(
        (time) => {
          const v = document.querySelector('video')
          return (
            v &&
            !v.seeking &&
            v.currentTime >= time &&
            v.currentTime < time + 5 &&
            v.getVideoPlaybackQuality().totalVideoFrames > 0
          )
        },
        target,
        { timeout: 60000 }
      )
      await page.locator('video').evaluate((video) => video.pause())
      const paused = await page.locator('video').evaluate((video) => video.currentTime)
      await page.waitForTimeout(1000)
      assert.ok(
        Math.abs((await page.locator('video').evaluate((video) => video.currentTime)) - paused) <
          0.2
      )
      await play(page)
      await page.waitForFunction(
        (time) => document.querySelector('video').currentTime > time + 1,
        paused,
        { timeout: 30000 }
      )
      await page.waitForTimeout(seconds * 1000)
      assert.ok(
        (await page
          .locator('video')
          .evaluate((video) => video.getVideoPlaybackQuality().totalVideoFrames)) > framesBefore
      )
      if (process.env.NASSAV_PLAYBACK_TEST_REFRESH === 'true') {
        stage = 'refresh'
        const beforeRefresh = await page.locator('video').evaluate((v) => v.currentTime)
        await command(page, sessionId, 'refresh')
        for (let attempt = 0; attempt < 160; attempt++) {
          const snapshot = await (
            await page.request.get(`${origin}/nassav/api/playback-sessions/${sessionId}`)
          ).json()
          if (snapshot.data?.state === 'ready') break
          assert.ok(
            !['failed', 'closed'].includes(snapshot.data?.state),
            `refresh failed: ${snapshot.data?.error_code}`
          )
          await page.waitForTimeout(2000)
        }
        await page.waitForFunction(
          (time) => {
            const v = document.querySelector('video')
            return v && !v.paused && !v.seeking && v.currentTime > time + 1
          },
          beforeRefresh,
          { timeout: 60000 }
        )
        const status = await (
          await page.request.get(`${origin}/nassav/api/playback-sessions/${sessionId}`)
        ).json()
        assert.equal(status.data.generation, 2)
        assert.equal(status.data.refresh_count, 1)
        assert.equal(status.data.state, 'ready')
      }
      await page.getByRole('button', { name: '关闭播放器', exact: true }).click()
      await command(page, sessionId, 'close')
      const status = await (
        await page.request.get(`${origin}/nassav/api/playback-sessions/${sessionId}`)
      ).json()
      assert.equal(status.data.state, 'closed')
      assert.equal(status.data.manifest_url, undefined)
      console.log(
        JSON.stringify({
          avid,
          engine,
          decoded: true,
          first_frame_ms: firstFrameMs,
          seek: true,
          pause_resume: true,
          continuous_seconds: seconds,
          refresh: process.env.NASSAV_PLAYBACK_TEST_REFRESH === 'true',
          closed: true,
        })
      )
    }
  } finally {
    for (const entry of sessions) await command(entry.page, entry.id, 'close').catch(() => {})
    await context.close()
    await browser.close()
  }
}
main().catch((error) => {
  console.error(
    JSON.stringify({
      name: error.name,
      stage,
      avid: currentAvid,
      reason: error.message.split('\n')[0].replace(/https?:\/\/\S+/g, '<url>'),
    })
  )
  process.exitCode = 1
})
