const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { randomUUID } = require('node:crypto')
async function main() {
  const storageState = process.env.NASSAV_PERSONAL_STORAGE_STATE
  if (!storageState) {
    console.log('SKIP: disposable personal storage state required')
    return
  }
  assert.ok(storageState.startsWith('/tmp/nassav-local-playback-http-'))
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const context = await browser.newContext({
    storageState,
    viewport: { width: 1440, height: 1000 },
  })
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178',
    api = origin + '/nassav/api',
    sessions = []
  assert.equal(new URL(origin).hostname, '127.0.0.1')
  await context.routeWebSocket('**/nassav/ws/**', () => {})
  const page = await context.newPage(),
    errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const headers = async () => ({
    'X-CSRFToken': (await context.cookies()).find((c) => c.name === 'csrftoken').value,
  })
  const request = async (method, path, data) => {
    const response = await context.request[method](api + path, {
      data,
      headers: await headers(),
      timeout: 10000,
    })
    assert.ok(response.ok(), `${path}: ${response.status()}`)
    return (await response.json()).data
  }
  const wait = async (fn) => {
    for (let i = 0; i < 100; i++) {
      if (await fn()) return
      await page.waitForTimeout(100)
    }
    throw new Error('wait timed out')
  }
  try {
    for (const avid of ['LOCAL-PLAYBACK', 'LOCAL-SECOND']) {
      await request('patch', `/resource/${avid}/status`, {
        watch_later: true,
        watched: avid === 'LOCAL-PLAYBACK',
      })
      const row = await request('post', `/resources/${avid}/playback-sessions`, {
        mode: 'local',
        request_id: randomUUID(),
      })
      sessions.push(row.session_id)
      await wait(
        async () => (await request('get', `/playback-sessions/${row.session_id}`)).state === 'ready'
      )
      await request('post', `/playback-sessions/${row.session_id}/viewed`, {
        session_generation: 1,
        sequence: 1,
      })
    }
    await page.bringToFront()
    await page.goto(origin + '/personal/watch-later', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: '移出已观看', exact: true }).waitFor()
    await wait(async () => (await page.locator('ul li').count()) === 2)
    const bottom = await page
      .locator('ul li a > div')
      .first()
      .evaluate((n) => getComputedStyle(n).borderBottomLeftRadius)
    assert.equal(bottom, '0px')
    await page.getByRole('button', { name: '移出已观看', exact: true }).click()
    await page
      .getByRole('dialog', { name: '确认列表操作' })
      .getByRole('button', { name: '确认', exact: true })
      .click()
    await wait(async () => (await page.locator('ul li').count()) === 1)
    assert.equal((await request('get', '/personal/watch-later')).length, 1)
    const nav = page.getByRole('navigation', { name: '个人中心功能' })
    await nav.getByRole('button', { name: '观看历史', exact: true }).click()
    await wait(async () => (await page.locator('ul li').count()) === 2)
    await page
      .locator('ul li')
      .first()
      .getByRole('button', { name: '删除历史', exact: true })
      .click()
    await page
      .getByRole('dialog', { name: '确认列表操作' })
      .getByRole('button', { name: '确认', exact: true })
      .click()
    await wait(async () => (await page.locator('ul li').count()) === 1)
    await page.getByRole('checkbox', { name: '选择本页全部历史' }).check()
    await page.getByRole('button', { name: /删除所选/ }).click()
    await page
      .getByRole('dialog', { name: '确认列表操作' })
      .getByRole('button', { name: '确认', exact: true })
      .click()
    await page.getByText('暂无观看历史', { exact: true }).waitFor()
    assert.equal((await request('get', '/personal/history')).length, 0)
    assert.equal((await request('get', '/resource/metadata?avid=LOCAL-PLAYBACK')).watched, true)
    for (const mode of ['dark', 'light']) {
      await page.setViewportSize({ width: 390, height: 844 })
      await page.evaluate((m) => {
        document.body.classList.remove('dark-mode', 'light-mode')
        document.body.classList.add(m + '-mode')
      }, mode)
      await nav.getByRole('button', { name: '播放设置', exact: true }).click()
      await page.getByRole('heading', { name: '播放设置', exact: true }).waitFor()
      await page.waitForTimeout(400)
      await page.screenshot({
        path: `/tmp/nassav-personal-playback-${engine.name()}-${mode}.png`,
        fullPage: true,
        animations: 'disabled',
      })
      await nav.getByRole('button', { name: '观看历史', exact: true }).click()
      await page.getByText('暂无观看历史', { exact: true }).waitFor()
    }
    assert.deepEqual(errors, [])
    console.log(
      'PASS real API: queue remove watched, history single/batch delete, cover radius, 390px themes'
    )
  } finally {
    for (const id of sessions) {
      const row = await request('get', `/playback-sessions/${id}`)
      if (!['closed', 'failed'].includes(row.state))
        await request('post', `/playback-sessions/${id}/close`, {
          expected_version: row.version,
          request_id: randomUUID(),
        })
    }
    await browser.close()
  }
}
main().catch((e) => {
  console.error(e)
  process.exitCode = 1
})
