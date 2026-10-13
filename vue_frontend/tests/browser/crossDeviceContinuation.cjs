// Opt-in real API: two independent logins/browser contexts of the same temporary user.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { randomUUID } = require('node:crypto')
async function main() {
  const first = process.env.NASSAV_PROGRESS_STORAGE_STATE,
    second = process.env.NASSAV_PROGRESS_SECOND_STORAGE_STATE
  if (!first || !second) {
    console.log('SKIP: two disposable login storage states required')
    return
  }
  for (const path of [first, second]) assert.ok(path.startsWith('/tmp/nassav-local-playback-http-'))
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
  assert.ok(['127.0.0.1', 'localhost'].includes(new URL(origin).hostname))
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const a = await browser.newContext({ storageState: first }),
    b = await browser.newContext({ storageState: second })
  const owned = new Map(),
    errors = []
  let stage = 'setup'
  const timeout = setTimeout(() => {
    console.error(`Timeout during ${stage}`)
    process.exitCode = 1
    void browser.close()
  }, 90000)
  let oldBody = null
  for (const context of [a, b]) {
    await context.routeWebSocket('**/nassav/ws/**', () => {})
    context.on('page', (page) => {
      page.on('pageerror', (error) => errors.push(error.message))
      page.on('response', async (response) => {
        if (
          response.request().method() === 'POST' &&
          new URL(response.url()).pathname.endsWith('/playback-sessions')
        ) {
          const data = (await response.json().catch(() => null))?.data
          if (data?.session_id) owned.set(data.session_id, context)
        }
      })
    })
  }
  a.on('request', (request) => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname.endsWith('/progress'))
      oldBody = request.postDataJSON()
  })
  const csrf = async (context) =>
    (await context.cookies()).find((cookie) => cookie.name === 'csrftoken')?.value
  const get = async (context, id) =>
    (
      await (
        await context.request.get(`${origin}/nassav/api/playback-sessions/${id}/progress`, {
          timeout: 10000,
        })
      ).json()
    ).data
  const until = async (check) => {
    for (let i = 0; i < 100; i++) {
      if (await check()) return
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    throw new Error('Timed out waiting for continuation')
  }
  const sid = async (page) =>
    page.locator('video').evaluate((video) => new URL(video.src).pathname.split('/')[4])
  const seek = async (page, position) => {
    await page.locator('video').evaluate(async (video, target) => {
      video.muted = true
      await video.play()
      video.currentTime = target
    }, position)
    await page.waitForFunction(() => !document.querySelector('video')?.seeking)
    await page.locator('video').evaluate((video) => video.pause())
  }
  try {
    const cookiesA = await a.cookies(),
      cookiesB = await b.cookies()
    assert.notEqual(
      cookiesA.find((c) => c.name === 'sessionid').value,
      cookiesB.find((c) => c.name === 'sessionid').value
    )
    // Reset only this fixture user's ledger, preserving the independent login identities.
    await b.request.get(origin + '/nassav/api/auth/session')
    assert.equal(
      (
        await b.request.delete(origin + '/nassav/api/resources/LOCAL-PLAYBACK/playback-progress', {
          headers: { 'X-CSRFToken': await csrf(b) },
        })
      ).status(),
      200
    )
    stage = 'first device'
    const pageA = await a.newPage()
    await pageA.goto(origin + '/play/LOCAL-PLAYBACK?mode=local')
    await pageA.waitForFunction(() => document.querySelector('video')?.readyState >= 1)
    await seek(pageA, 30)
    const idA = await sid(pageA)
    await until(async () => (await get(a, idA))?.position_seconds >= 30)
    const original = await get(a, idA)
    stage = 'second device opening'
    const home = await b.newPage()
    await home.goto(origin + '/')
    const panel = home.getByRole('region', { name: '继续观看', exact: true })
    await panel.getByText('LOCAL-PLAYBACK · 本地视频', { exact: true }).waitFor()
    const opened = b.waitForEvent('page')
    await panel.getByRole('button', { name: '继续播放', exact: true }).click()
    const pageB = await opened
    await pageB.getByRole('button', { name: '在此接续', exact: true }).waitFor()
    const idB = await sid(pageB)
    assert.equal(
      (await get(a, idA)).writer_generation,
      original.writer_generation,
      'merely opening another device cannot claim'
    )
    assert.equal(
      (await a.request.get(`${origin}/nassav/api/playback-sessions/${idB}/progress`)).status(),
      404,
      'a different login cannot control the new session'
    )
    await pageB.bringToFront()
    await pageB.setViewportSize({ width: 390, height: 844 })
    const prompt = pageB.getByRole('group', { name: '恢复播放进度' })
    const readonly = prompt.getByRole('button', { name: '仅播放，不保存进度', exact: true })
    await readonly.scrollIntoViewIfNeeded()
    const promptBox = await prompt.boundingBox(),
      actionBox = await readonly.boundingBox()
    assert.ok(
      actionBox.y >= promptBox.y &&
        actionBox.y + actionBox.height <= promptBox.y + promptBox.height + 1
    )
    stage = 'explicit transfer'
    // The first device saves a newer position after the second has already shown the prompt.
    await seek(pageA, 42)
    await until(async () => (await get(a, idA))?.position_seconds >= 42)
    const stale = {
      ...oldBody,
      request_id: randomUUID(),
      sequence: oldBody.sequence + 1,
      position_seconds: 70,
    }
    await pageB.getByRole('button', { name: '在此接续', exact: true }).click()
    await pageB.waitForFunction(() => document.querySelector('video')?.currentTime >= 42)
    await pageB.locator('video').evaluate((video) => video.pause())
    await until(async () => (await get(b, idB))?.writer_generation > original.writer_generation)
    const transferred = await get(b, idB)
    const late = await a.request.put(`${origin}/nassav/api/playback-sessions/${idA}/progress`, {
      headers: { 'X-CSRFToken': await csrf(a) },
      data: stale,
    })
    assert.equal(late.status(), 409)
    assert.equal((await get(b, idB)).position_seconds, transferred.position_seconds)
    stage = 'late writer rejection'
    await seek(pageA, 55)
    await pageA.getByText('进度保存权已失效；本页仍可播放', { exact: false }).waitFor()
    assert.ok((await get(b, idB)).position_seconds < 55)
    await pageB.bringToFront()
    await pageB.setViewportSize({ width: 390, height: 844 })
    const frame = await pageB.getByRole('region', { name: '视频播放器' }).boundingBox()
    assert.ok(Math.abs(frame.width / frame.height - 16 / 9) < 0.02)
    stage = 'mobile home'
    await home.bringToFront()
    await home.setViewportSize({ width: 390, height: 844 })
    await panel.scrollIntoViewIfNeeded()
    assert.equal(
      await home.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    stage = 'mobile screenshot'
    await home.screenshot({
      path: '/tmp/nassav-continuation-' + (engine === chromium ? 'chrome' : 'firefox') + '.png',
      fullPage: true,
    })
    await home.evaluate(() => {
      document.body.classList.remove('dark-mode')
      document.body.classList.add('light-mode')
    })
    assert.equal(
      await home.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    await home.screenshot({
      path:
        '/tmp/nassav-continuation-light-' + (engine === chromium ? 'chrome' : 'firefox') + '.png',
      fullPage: true,
    })
    assert.equal(
      (
        await b.request.delete(origin + '/nassav/api/resources/LOCAL-PLAYBACK/playback-progress', {
          headers: { 'X-CSRFToken': await csrf(b) },
        })
      ).status(),
      200
    )
    stage = 'cleared list'
    await panel.getByRole('button', { name: '刷新', exact: true }).click()
    await panel.getByRole('heading', { name: '暂无可接续记录', exact: true }).waitFor()
    assert.equal((await get(b, idB)).position_seconds, 0)
    assert.deepEqual(errors, [])
    console.log(
      'PASS: two independent real logins, home continuation, read-only open, latest-position explicit transfer, late writer 409, mobile and cleared ledger'
    )
  } catch (error) {
    console.error(`Failure during ${stage}: ${error.message}`)
    throw error
  } finally {
    clearTimeout(timeout)
    for (const [id, context] of owned) {
      try {
        const row = (
          await (
            await context.request.get(`${origin}/nassav/api/playback-sessions/${id}`, {
              timeout: 3000,
            })
          ).json()
        ).data
        if (row)
          await context.request.post(`${origin}/nassav/api/playback-sessions/${id}/close`, {
            timeout: 3000,
            headers: { 'X-CSRFToken': await csrf(context) },
            data: { expected_version: row.version, request_id: randomUUID() },
          })
      } catch (error) {
        console.error('Fixture cleanup request failed: ' + error.message)
        process.exitCode = 1
      }
    }
    await a.close()
    await b.close()
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
