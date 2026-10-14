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
    async function checkHover(kind) {
      const card = page.locator('ul li').first()
      for (const mode of ['dark', 'light']) {
        await page.evaluate((value) => {
          document.body.classList.remove('dark-mode', 'light-mode')
          document.body.classList.add(value + '-mode')
        }, mode)
        await card.hover()
        await page.waitForTimeout(350)
        const style = await card.evaluate((node) => ({
          transform: getComputedStyle(node).transform,
          shadow: getComputedStyle(node).boxShadow,
        }))
        assert.notEqual(style.transform, 'none')
        assert.notEqual(style.shadow, 'none')
        await page.screenshot({
          path: `/tmp/nassav-viewing-${engine.name()}-${kind}-${mode}.png`,
          fullPage: true,
          animations: 'disabled',
        })
        await page.mouse.move(0, 0)
        await page.waitForTimeout(350)
      }
    }
    await checkHover('watch-later')
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
    assert.equal(await page.getByRole('checkbox').count(), 0)
    await checkHover('history')
    const card = page.locator('ul li').first(),
      before = await card.boundingBox(),
      url = page.url()
    await page.getByRole('button', { name: '批量操作', exact: true }).click()
    const checkbox = card.getByRole('checkbox')
    const cover = await card.locator('a').boundingBox(),
      check = await checkbox.boundingBox()
    assert.ok(check.x >= cover.x && check.x - cover.x < 20)
    assert.ok(check.y >= cover.y && check.y - cover.y < 20)
    assert.ok(Math.abs((await card.boundingBox()).height - before.height) < 1)
    await checkbox.focus()
    await page.keyboard.press('Space')
    assert.equal(await checkbox.isChecked(), true)
    assert.equal(page.url(), url, 'checkbox does not navigate to detail')
    assert.equal(await card.evaluate((node) => node.classList.contains('is-selected')), true)
    assert.equal(
      await page
        .getByRole('checkbox', { name: '选择本页全部历史' })
        .evaluate((node) => node.indeterminate),
      true
    )
    await page.getByRole('button', { name: '退出批量', exact: true }).click()
    assert.equal(await page.getByRole('checkbox').count(), 0)
    assert.ok(Math.abs((await card.boundingBox()).height - before.height) < 1)
    await page.getByRole('button', { name: '批量操作', exact: true }).click()
    assert.equal(await checkbox.isChecked(), false)
    await page.getByRole('button', { name: '退出批量', exact: true }).click()
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await card.hover()
    assert.equal(await card.evaluate((node) => getComputedStyle(node).transform), 'none')
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await page.mouse.move(0, 0)

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
    await page.getByRole('button', { name: '批量操作', exact: true }).click()
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
      'PASS real API: queue actions, card hover/themes/reduced motion, batch mode overlay/keyboard/no layout shift, 390px themes'
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
