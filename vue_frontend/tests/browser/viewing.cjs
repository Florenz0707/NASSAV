// Opt-in disposable real API, synthetic MP4, two login contexts.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { randomUUID } = require('node:crypto')
async function main() {
  const states = [
    process.env.NASSAV_PROGRESS_STORAGE_STATE,
    process.env.NASSAV_PROGRESS_SECOND_STORAGE_STATE,
  ]
  if (states.some((path) => !path)) {
    console.log('SKIP: disposable login states required')
    return
  }
  states.forEach((path) => assert.ok(path.startsWith('/tmp/nassav-local-playback-http-')))
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
  assert.equal(new URL(origin).hostname, '127.0.0.1')
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const a = await browser.newContext({ storageState: states[0] }),
    b = await browser.newContext({ storageState: states[1] })
  const errors = [],
    sessions = new Map()
  let stage = 'setup'
  const timer = setTimeout(() => {
    console.error(`Timeout: ${stage}`)
    process.exitCode = 1
    void browser.close()
  }, 90000)
  for (const context of [a, b]) {
    await context.routeWebSocket('**/nassav/ws/**', () => {})
    context.on('page', (page) => {
      page.on('pageerror', (error) => errors.push(error.message))
      page.on('response', async (response) => {
        if (
          response.request().method() === 'POST' &&
          new URL(response.url()).pathname.endsWith('/playback-sessions')
        ) {
          const row = (await response.json().catch(() => null))?.data
          if (row?.session_id) sessions.set(row.session_id, context)
        }
      })
    })
  }
  const csrf = async (context) =>
    (await context.cookies()).find((c) => c.name === 'csrftoken')?.value
  const get = async (path) => {
    const response = await a.request.get(`${origin}/nassav/api/${path}`, { timeout: 10000 })
    assert.ok(response.ok(), `${path}: ${response.status()}`)
    return response.json()
  }
  const until = async (check) => {
    for (let i = 0; i < 70; i++) {
      if (await check()) return
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    throw new Error(`Timed out: ${stage}`)
  }
  const history = async () => (await get('personal/history')).data
  const close = async (page) => {
    const id = await page
      .locator('video')
      .evaluate((video) => new URL(video.src).pathname.split('/')[4])
    const context = page.context()
    await page.close()
    // pagehide can close concurrently with this cleanup request. A 409 is
    // acceptable only after verifying the current owned snapshot is terminal.
    for (let attempt = 0; attempt < 3; attempt++) {
      const row = (
        await (
          await context.request.get(`${origin}/nassav/api/playback-sessions/${id}`, {
            timeout: 10000,
          })
        ).json()
      ).data
      if (['closed', 'failed'].includes(row.state)) break
      const response = await context.request.post(
        `${origin}/nassav/api/playback-sessions/${id}/close`,
        {
          data: { expected_version: row.version, request_id: randomUUID() },
          headers: { 'X-CSRFToken': await csrf(context) },
          timeout: 10000,
        }
      )
      assert.ok(response.ok() || response.status() === 409)
    }
    const final = (
      await (
        await context.request.get(`${origin}/nassav/api/playback-sessions/${id}`, {
          timeout: 10000,
        })
      ).json()
    ).data
    assert.equal(final.state, 'closed')
    sessions.delete(id)
  }
  const openPlay = async (context, avid, readonly = false) => {
    const page = await context.newPage()
    await page.bringToFront()
    await page.goto(`${origin}/play/${avid}?mode=local`, { waitUntil: 'domcontentloaded' })
    await page.bringToFront()
    await page.locator('video').waitFor()
    await page.waitForTimeout(350)
    const read = page.getByRole('button', { name: '仅播放，不保存进度', exact: true })
    const start = page.getByRole('button', { name: '从头播放', exact: true })
    if (readonly) {
      await read.waitFor()
      await read.click()
    } else if (await start.isVisible()) await start.click()
    else
      await page.locator('video').evaluate(async (video) => {
        video.muted = true
        await video.play()
      })
    await page.waitForFunction(() => !document.querySelector('video')?.paused)
    return page
  }
  try {
    const listing = await a.newPage()
    await listing.bringToFront()
    stage = 'empty or existing history'
    await listing.goto(`${origin}/resources/viewing`, { waitUntil: 'domcontentloaded' })
    await listing.getByRole('heading', { name: '我的观看' }).waitFor()
    const detail = await a.newPage()
    await detail.bringToFront()
    stage = 'add watch later from detail'
    await detail.goto(`${origin}/resource/LOCAL-PLAYBACK`, { waitUntil: 'domcontentloaded' })
    await detail.getByRole('button', { name: /^(稍后观看|已加入稍后观看)$/ }).waitFor()
    const add = detail.getByRole('button', { name: '稍后观看', exact: true })
    if (await add.isVisible()) await add.click()
    await detail.getByRole('button', { name: '已加入稍后观看', exact: true }).waitFor()
    await listing.bringToFront()
    await listing.getByRole('button', { name: '稍后观看', exact: true }).click()
    await listing.getByRole('link', { name: 'LOCAL-PLAYBACK 资源详情' }).waitFor()
    stage = 'first playback and no automatic removal'
    const first = await openPlay(a, 'LOCAL-PLAYBACK')
    await until(async () => (await history()).some((row) => row.avid === 'LOCAL-PLAYBACK'))
    assert.equal((await get('personal/watch-later')).data.length, 1)
    const firstId = await first
      .locator('video')
      .evaluate((v) => new URL(v.src).pathname.split('/')[4])
    await until(async () => (await get(`playback-sessions/${firstId}/progress`)).data.is_writer)
    await first.locator('video').evaluate((v) => v.pause())
    stage = 'read only playback records history without claiming progress'
    const before = (await history()).find((row) => row.avid === 'LOCAL-PLAYBACK').queue_time
    const readonly = await openPlay(b, 'LOCAL-PLAYBACK', true)
    await until(
      async () =>
        (await history()).find((row) => row.avid === 'LOCAL-PLAYBACK').queue_time !== before
    )
    assert.equal((await history()).filter((row) => row.avid === 'LOCAL-PLAYBACK').length, 1)
    // Query with each login; same user ledger remains owned by the first page.
    const id = await readonly
      .locator('video')
      .evaluate((v) => new URL(v.src).pathname.split('/')[4])
    const progress = await (
      await b.request.get(`${origin}/nassav/api/playback-sessions/${id}/progress`)
    ).json()
    assert.equal(progress.data.is_writer, false)
    await close(readonly)
    await close(first)
    stage = 'second resource then repeat viewing moves to head'
    const second = await openPlay(a, 'LOCAL-SECOND')
    await until(async () => (await history())[0]?.avid === 'LOCAL-SECOND')
    await close(second)
    const repeat = await openPlay(a, 'LOCAL-PLAYBACK')
    await until(async () => (await history())[0]?.avid === 'LOCAL-PLAYBACK')
    assert.equal((await history()).length, 2)
    await close(repeat)
    stage = 'pagination and refreshed list'
    await listing.bringToFront()
    await listing.getByRole('button', { name: '观看历史', exact: true }).click()
    await listing.getByRole('button', { name: '刷新', exact: true }).click()
    await listing.getByRole('link', { name: 'LOCAL-SECOND 资源详情' }).waitFor()
    const paged = listing.waitForResponse(
      (r) =>
        new URL(r.url()).pathname.endsWith('/personal/history') &&
        new URL(r.url()).searchParams.get('page_size') === '1'
    )
    await listing.getByLabel('每页条数').fill('1')
    await listing.getByRole('heading', { name: '我的观看' }).click()
    assert.equal((await (await paged).json()).pagination.pages, 2)
    await until(
      async () => !(await listing.getByRole('link', { name: 'LOCAL-SECOND 资源详情' }).isVisible())
    )
    await listing.getByRole('button', { name: '下一页', exact: true }).click()
    await listing.getByRole('link', { name: 'LOCAL-SECOND 资源详情' }).waitFor()
    stage = 'mobile and theme'
    await listing.setViewportSize({ width: 390, height: 844 })
    await listing.evaluate(() => {
      document.body.classList.remove('light-mode')
      document.body.classList.add('dark-mode')
    })
    const darkBackground = await listing.evaluate(() =>
      getComputedStyle(document.body).getPropertyValue('--bg-secondary')
    )
    await listing.screenshot({
      path: `/tmp/nassav-viewing-${engine.name()}-dark.png`,
      fullPage: true,
      animations: 'disabled',
    })
    assert.ok(await listing.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
    await listing.evaluate(() => {
      document.body.classList.remove('dark-mode')
      document.body.classList.add('light-mode')
    })
    assert.notEqual(
      await listing.evaluate(() =>
        getComputedStyle(document.body).getPropertyValue('--bg-secondary')
      ),
      darkBackground
    )
    await listing.screenshot({
      path: `/tmp/nassav-viewing-${engine.name()}-light.png`,
      fullPage: true,
      animations: 'disabled',
    })
    stage = 'remove and refresh persists'
    await listing.getByRole('button', { name: '稍后观看', exact: true }).click()
    await listing.getByRole('button', { name: '移除', exact: true }).click()
    await listing.getByRole('heading', { name: '暂无稍后观看资源' }).waitFor()
    await listing.reload()
    await listing.getByRole('button', { name: '稍后观看', exact: true }).click()
    await listing.getByRole('heading', { name: '暂无稍后观看资源' }).waitFor()
    assert.deepEqual(errors, [])
    console.log(
      'PASS: real API viewing dedupe, readonly, rewatch head, watch later persistence/removal, pagination, mobile and themes'
    )
  } finally {
    clearTimeout(timer)
    for (const [id, context] of sessions) {
      try {
        const row = (
          await (
            await context.request.get(`${origin}/nassav/api/playback-sessions/${id}`, {
              timeout: 3000,
            })
          ).json()
        ).data
        if (row && !['closed', 'failed'].includes(row.state))
          await context.request.post(`${origin}/nassav/api/playback-sessions/${id}/close`, {
            data: { expected_version: row.version, request_id: randomUUID() },
            headers: { 'X-CSRFToken': await csrf(context) },
            timeout: 3000,
          })
      } catch {
        /* Only disposable fixtures; server cleanup owns remaining sessions. */
      }
    }
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
