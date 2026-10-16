const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')

;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium
      ? { executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome' }
      : {}
  )
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4188'
  assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/)
  assert.ok(process.env.NASSAV_LIBRARY_STORAGE_STATE, 'Isolated login state required')
  try {
    const context = await browser.newContext({
      storageState: process.env.NASSAV_LIBRARY_STORAGE_STATE,
      viewport: { width: 1440, height: 1050 },
    })
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    const errors = [],
      writes = [],
      releases = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (['POST', 'DELETE'].includes(request.method()))
        writes.push({ path: new URL(request.url()).pathname, body: request.postDataJSON() })
    })
    await page.goto(origin + '/add')
    await page.getByLabel('视频编号 (AVID)', { exact: false }).fill('LIBRARY-NEW')
    const source = page.locator('#add-source')
    await source.click()
    assert.equal(await page.getByRole('option', { name: '自动', exact: true }).count(), 0)
    await page.getByRole('option', { name: 'Jable', exact: false }).click()
    await page.getByLabel('来源凭证', { exact: true }).click()
    await page.getByRole('option', { name: '个人凭证', exact: true }).click()
    await page.getByRole('button', { name: '添加资源', exact: true }).click()
    await page.getByText('LIBRARY-NEW:403', { exact: true }).waitFor()
    assert.equal(
      await page.getByLabel('视频编号 (AVID)', { exact: false }).inputValue(),
      'LIBRARY-NEW'
    )
    await page.getByLabel('来源凭证', { exact: true }).click()
    await page.getByRole('option', { name: '默认凭证', exact: true }).click()
    await page.getByRole('button', { name: '添加资源', exact: true }).click()
    await page.getByRole('link', { name: '查看我的请求', exact: true }).waitFor()
    const added = writes.filter((item) => item.path === '/nassav/api/library/entries').at(-1)
    assert.equal(added.body.source, 'jable')
    assert.equal(added.body.credential_mode, 'public')
    assert.ok(added.body.request_id)
    await page.goto(origin + '/resource/LIBRARY-METADATA')
    await page.getByRole('button', { name: '刷新信息', exact: true }).click()
    assert.equal(await page.getByRole('menuitem', { name: '仅M3U8', exact: true }).count(), 0)
    await page.getByRole('menuitem', { name: '刷新资源', exact: true }).click()
    let dialog = page.getByRole('dialog')
    await dialog.getByLabel('来源', { exact: true }).click()
    await page.getByRole('option', { name: 'Jable', exact: false }).click()
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    const beforeRefresh = writes.filter((item) => item.path.endsWith('/operations')).length
    await page.getByRole('button', { name: '刷新信息', exact: true }).click()
    await page.getByRole('menuitem', { name: '刷新资源', exact: true }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel('来源', { exact: true }).click()
    await page.getByRole('option', { name: 'Jable', exact: false }).click()
    await dialog.getByRole('button', { name: '确认提交', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' })
    assert.equal(
      writes.filter((item) => item.path.endsWith('/operations')).length,
      beforeRefresh + 1
    )
    assert.equal(
      writes.filter((item) => item.path.endsWith('/operations')).at(-1).body.action,
      'refresh'
    )
    const before = writes.filter((item) => item.path.endsWith('/operations')).length
    await page.getByRole('button', { name: '下载视频', exact: true }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel('来源', { exact: true }).click()
    await page.getByRole('option', { name: 'Jable', exact: false }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('listbox').waitFor({ state: 'hidden' })
    for (const theme of ['dark', 'light']) {
      await page.evaluate((mode) => {
        document.body.classList.toggle('dark-mode', mode === 'dark')
        document.body.classList.toggle('light-mode', mode === 'light')
      }, theme)
      await page.waitForTimeout(400)
      await page.keyboard.press('Tab')
      assert.equal(await dialog.evaluate((node) => node.contains(document.activeElement)), true)
      const bounds = await dialog.boundingBox()
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 844)
      await page.screenshot({ path: `/tmp/nassav-library-command-${engine.name()}-${theme}.png` })
    }
    await dialog.getByRole('button', { name: '确认提交', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' })
    await page.setViewportSize({ width: 1440, height: 1050 })
    assert.equal(writes.filter((item) => item.path.endsWith('/operations')).length, before + 1)
    await page.getByRole('button', { name: '下载中...', exact: true }).waitFor()
    assert.equal(
      await page.getByRole('button', { name: '下载中...', exact: true }).isDisabled(),
      true
    )
    let releaseDone
    const firstRelease = new Promise((resolve) => {
      releaseDone = resolve
    })
    await page.route('**/nassav/api/library/entries/*', async (route) => {
      if (route.request().method() !== 'DELETE') return route.continue()
      releases.push(route.request().postDataJSON())
      if (releases.length !== 1) return route.continue()
      const response = await route.fetch()
      assert.equal(response.status(), 200)
      await route.abort('failed')
      releaseDone()
    })
    async function release() {
      await page.getByRole('button', { name: '删除数据', exact: true }).click()
      assert.equal(await page.getByRole('menuitem', { name: '删除视频', exact: true }).count(), 0)
      await page.getByRole('menuitem', { name: '删除资源', exact: true }).click()
      await page.getByRole('dialog').getByRole('button', { name: '确认删除', exact: true }).click()
    }
    await release()
    await firstRelease
    await page.getByText('网络错误', { exact: true }).waitFor()
    await release()
    await page.waitForURL((url) => url.pathname !== '/resource/LIBRARY-METADATA')
    assert.equal(releases.length, 2)
    assert.deepEqual(
      releases[0],
      releases[1],
      'Lost outcome must replay same command and original membership CAS'
    )
    const statuses = await page.request.post(origin + '/nassav/api/library/entries/status', {
      data: { avids: ['LIBRARY-METADATA', 'LIBRARY-NEW', 'LOCAL-PLAYBACK'] },
      headers: {
        'X-CSRFToken': (await context.cookies()).find((cookie) => cookie.name === 'csrftoken')
          .value,
      },
    })
    const rows = (await statuses.json()).data
    assert.deepEqual(
      rows.map((row) => row.is_in_my_library),
      [false, true, true]
    )
    assert.ok(
      !writes.some(
        (item) =>
          /\/resource\/jobs|\/download\//.test(item.path) || /\/resource\/LIBRARY/.test(item.path)
      )
    )
    assert.deepEqual(errors, [])
    console.log(
      'Native shared library commands passed: explicit scope, failed private draft, queued add/refresh/download, cancelled dialog, CAS release and lost-response replay'
    )
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
