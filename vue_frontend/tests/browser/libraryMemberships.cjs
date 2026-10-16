const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')

;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4188'
  assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/)
  assert.ok(process.env.NASSAV_LIBRARY_STORAGE_STATE, 'Disposable HTTP state required')
  try {
    const context = await browser.newContext({
      storageState: process.env.NASSAV_LIBRARY_STORAGE_STATE,
      viewport: { width: 1440, height: 1050 },
    })
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    const writes = [],
      errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (request.method() === 'DELETE') writes.push(new URL(request.url()).pathname)
    })
    await page.goto(origin + '/resources')
    await page.getByRole('button', { name: '管理资源', exact: true }).click()
    const modal = page.getByRole('dialog', { name: '管理资源', exact: true })
    await modal.getByRole('rowheader', { name: 'LIBRARY-UNAVAILABLE', exact: true }).waitFor()
    assert.ok(!(await modal.innerText()).includes('unavailable-facts-must-not-be-disclosed'))
    await modal.getByRole('button', { name: '资源可用性' }).click()
    await page.getByRole('option', { name: '暂不可用', exact: true }).click()
    await modal
      .getByRole('button', { name: '删除资源 LOCAL-PLAYBACK', exact: true })
      .waitFor({ state: 'hidden' })
    await modal.getByRole('button', { name: '删除资源 LIBRARY-UNAVAILABLE', exact: true }).click()
    await page.getByRole('dialog', { name: '删除资源', exact: true }).waitFor()
    await page.keyboard.press('Escape')
    assert.equal(await modal.isVisible(), true)
    assert.equal(writes.length, 0)
    await modal.getByRole('button', { name: '删除资源 LIBRARY-UNAVAILABLE', exact: true }).click()
    await page
      .getByRole('dialog', { name: '删除资源', exact: true })
      .getByRole('button', { name: '确认删除', exact: true })
      .click()
    await modal.getByRole('heading', { name: '暂无匹配的持有关系', exact: true }).waitFor()
    await modal.getByRole('button', { name: '资源可用性' }).click()
    await page.getByRole('option', { name: '全部可用性', exact: true }).click()
    await modal.getByRole('rowheader', { name: 'LIBRARY-METADATA', exact: true }).waitFor()
    const csrf = (await context.cookies()).find((cookie) => cookie.name === 'csrftoken').value
    async function json(path, method = 'get', data) {
      const response = await page.request[method](origin + '/nassav/api' + path, {
        headers: { 'X-CSRFToken': csrf },
        ...(data ? { data } : {}),
      })
      assert.ok(response.ok(), `${method} ${path}: ${response.status()}`)
      return (await response.json()).data
    }
    const before = (await json('/library/memberships')).find(
      (item) => item.avid === 'LIBRARY-METADATA'
    )
    await json(`/library/entries/${before.entry_id}`, 'delete', {
      expected_version: before.entry_version,
      request_id: await page.evaluate(() => crypto.randomUUID()),
    })
    const fresh = await json('/library/entries', 'post', {
      avid: 'LIBRARY-METADATA',
      kind: 'scrape',
      action: 'add',
      source: 'jable',
      credential_mode: 'public',
      request_id: await page.evaluate(() => crypto.randomUUID()),
    })
    assert.notEqual(fresh.entry_id, before.entry_id)
    await modal.getByRole('button', { name: '删除资源 LIBRARY-METADATA', exact: true }).click()
    await page
      .getByRole('dialog', { name: '删除资源', exact: true })
      .getByRole('button', { name: '确认删除', exact: true })
      .click()
    await modal
      .getByText('LIBRARY-METADATA：持有关系已变化，请刷新列表后重试', { exact: true })
      .waitFor()
    assert.equal(writes.includes('/nassav/api/library/entries/' + fresh.entry_id), false)
    const current = (await json('/library/memberships')).find(
      (item) => item.avid === 'LIBRARY-METADATA'
    )
    assert.equal(current.entry_id, fresh.entry_id)
    for (const avid of ['OPERATION-UI', 'OPERATION-SECOND'])
      await modal.getByRole('checkbox', { name: `选择资源 ${avid}`, exact: true }).check()
    await modal.getByRole('button', { name: '删除所选', exact: true }).click()
    await page
      .getByRole('dialog', { name: '删除资源', exact: true })
      .getByRole('button', { name: '确认删除', exact: true })
      .click()
    await modal.getByText('已删除 2 个，失败 0 个', { exact: true }).waitFor()
    await modal
      .getByRole('rowheader', { name: 'OPERATION-UI', exact: true })
      .waitFor({ state: 'hidden' })
    for (const theme of ['light', 'dark']) {
      await page.evaluate((mode) => {
        document.body.classList.toggle('dark-mode', mode === 'dark')
        document.body.classList.toggle('light-mode', mode === 'light')
      }, theme)
      await page.waitForTimeout(400)
      await page.setViewportSize({ width: 390, height: 844 })
      const bounds = await modal.boundingBox()
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 844)
      await modal.getByRole('button', { name: '关闭弹窗', exact: true }).focus()
      await page.keyboard.press('Shift+Tab')
      assert.equal(await modal.evaluate((node) => node.contains(document.activeElement)), true)
    }
    await page.keyboard.press('Escape')
    await modal.waitFor({ state: 'hidden' })
    assert.equal(await page.evaluate(() => document.body.style.overflow), '')
    assert.deepEqual(errors, [])
    console.log(
      'Native membership management passed: unavailable redaction/release, nested Escape, old-row CAS, batch own release, mobile/theme/focus lifecycle'
    )
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
