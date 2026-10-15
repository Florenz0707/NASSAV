const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { randomUUID } = require('node:crypto')
;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4188'
  const gcEnabled = process.env.NASSAV_EXPECT_GC_ENABLED === '1'
  assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/)
  assert.ok(
    process.env.NASSAV_LIBRARY_STORAGE_STATE,
    'Disposable managed administrator state required'
  )
  try {
    const context = await browser.newContext({
      storageState: process.env.NASSAV_LIBRARY_STORAGE_STATE,
      viewport: { width: 1440, height: 1050 },
    })
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    const errors = [],
      commands = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (
        request.method() !== 'GET' &&
        /\/(retention|availability|gc|retry)$/.test(new URL(request.url()).pathname)
      ) {
        const body = request.postDataJSON()
        commands.push({
          path: new URL(request.url()).pathname,
          id: body.request_id,
          version: body.expected_version,
        })
      }
    })
    await page.goto(origin + '/manage/resources')
    await page.getByRole('heading', { name: '共享资源管理', exact: true }).waitFor()
    const csrf = (await context.cookies()).find((cookie) => cookie.name === 'csrftoken').value
    async function api(method, path, body) {
      const response = await page.request[method](origin + '/nassav/api' + path, {
        headers: { 'X-CSRFToken': csrf },
        ...(body ? { data: body } : {}),
      })
      assert.ok(response.ok(), `${method} ${path}: ${response.status()}`)
      return (await response.json()).data
    }
    const row = (avid) =>
      page
        .getByRole('row')
        .filter({ has: page.getByRole('rowheader', { name: new RegExp('^' + avid) }) })
    const editor = (name) => page.getByRole('dialog', { name, exact: true })
    const target = gcEnabled ? 'GC-UI-EMPTY' : 'LIBRARY-METADATA'
    await row(target)
      .getByRole('button', { name: '预览回收 ' + target, exact: true })
      .click()
    const preview = editor('回收预览')
    if (gcEnabled) await preview.getByText('当前未发现阻塞条件', { exact: true }).waitFor()
    else {
      await preview.getByText('仍有用户持有', { exact: true }).waitFor()
      assert.equal(
        await preview.getByRole('button', { name: '登记回收', exact: true }).isDisabled(),
        true
      )
    }
    await preview.getByRole('button', { name: '关闭', exact: true }).click()
    await row(target)
      .getByRole('button', { name: '保留资源 ' + target, exact: true })
      .click()
    const retention = editor('保留资源')
    const pool = (await api('get', '/admin/resource-pools')).find((item) => item.avid === target)
    await api('put', `/admin/resource-pools/${pool.pool_id}/retention`, {
      request_id: randomUUID(),
      reason: 'maintenance',
      expected_version: pool.pool_version,
      retained: true,
    })
    await retention.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '确认执行', exact: true }).click()
    await retention
      .getByText('状态或保护条件已变化，未执行本次修改。请关闭后刷新确认。', { exact: true })
      .waitFor()
    await retention.getByRole('button', { name: '关闭', exact: true }).click()
    await page.getByRole('button', { name: '刷新资源池', exact: true }).click()
    await row(target)
      .getByRole('button', { name: '取消保留 ' + target, exact: true })
      .waitFor()
    await row(target)
      .getByRole('button', { name: '取消保留 ' + target, exact: true })
      .click()
    const unretain = editor('取消保留')
    await unretain.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '确认执行', exact: true }).click()
    await unretain.waitFor({ state: 'hidden' })
    await row(target)
      .getByRole('button', { name: '保留资源 ' + target, exact: true })
      .waitFor()
    let dropped = false
    await page.route('**/nassav/api/admin/resources/*/availability', async (route) => {
      if (dropped) return route.continue()
      dropped = true
      const response = await route.fetch()
      assert.equal(response.status(), 200)
      await route.abort('failed')
    })
    await row(target)
      .getByRole('button', { name: '下架资源 ' + target, exact: true })
      .click()
    const availability = editor('下架资源')
    await availability.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '确认执行', exact: true }).click()
    await availability.getByText('网络错误', { exact: true }).waitFor()
    await availability.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '确认执行', exact: true }).click()
    await availability.waitFor({ state: 'hidden' })
    const repeated = commands.filter((item) => item.path.endsWith('/availability'))
    assert.equal(repeated.length, 2)
    assert.deepEqual(repeated[0], repeated[1])
    await row(target)
      .getByRole('button', { name: '恢复访问 ' + target, exact: true })
      .click()
    const restore = editor('恢复资源访问')
    await restore.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '确认执行', exact: true }).click()
    await restore.waitFor({ state: 'hidden' })
    for (const theme of ['light', 'dark']) {
      await page.setViewportSize({ width: 390, height: 844 })
      await page.evaluate(
        (theme) => document.documentElement.classList.toggle('dark', theme === 'dark'),
        theme
      )
      await row(target)
        .getByRole('button', { name: '预览回收 ' + target, exact: true })
        .click()
      await preview.getByRole('button', { name: '关闭', exact: true }).scrollIntoViewIfNeeded()
      const bounds = await preview.boundingBox()
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 845)
      await page.keyboard.press('Escape')
      await preview.waitFor({ state: 'hidden' })
    }
    await page.setViewportSize({ width: 1440, height: 1050 })
    if (gcEnabled) {
      await row(target)
        .getByRole('button', { name: '预览回收 ' + target, exact: true })
        .click()
      await preview.getByText('当前未发现阻塞条件', { exact: true }).waitFor()
      await preview.getByRole('button', { name: '登记回收', exact: true }).click()
      await page.getByRole('button', { name: '确认执行', exact: true }).click()
      await preview.waitFor({ state: 'hidden' })
      await page.getByText('回收请求已登记，文件处理结果以回收记录为准', { exact: true }).waitFor()
      await page.getByRole('button', { name: '回收记录', exact: true }).click()
      const failed = page
        .getByRole('row')
        .filter({ has: page.getByRole('cell', { name: 'permission_denied', exact: true }) })
      await failed.getByRole('button', { name: /^重试回收 / }).click()
      const retry = editor('重试失败回收')
      await retry.getByRole('button', { name: '下一步', exact: true }).click()
      await page.getByRole('button', { name: '确认执行', exact: true }).click()
      await retry.waitFor({ state: 'hidden' })
      await page.getByRole('cell', { name: '已排队', exact: true }).nth(1).waitFor()
      assert.equal(await page.getByRole('cell', { name: '已排队', exact: true }).count(), 2)
    } else {
      assert.equal(
        commands.some((item) => item.path.endsWith('/gc') || item.path.endsWith('/retry')),
        false
      )
      await page.getByRole('button', { name: '回收记录', exact: true }).click()
      await page.getByText('暂无回收记录', { exact: true }).waitFor()
    }
    assert.deepEqual(errors, [])
    console.log(
      `Native resource retention/availability/replay/CAS/theme/mobile checks passed; GC enabled=${gcEnabled}`
    )
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
