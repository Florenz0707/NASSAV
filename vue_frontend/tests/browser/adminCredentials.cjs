const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { randomUUID } = require('node:crypto')
;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4188'
  assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/)
  assert.ok(process.env.NASSAV_LIBRARY_STORAGE_STATE, 'Disposable administrator state required')
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
        new URL(request.url()).pathname.includes('/admin/source-credentials')
      ) {
        const body = request.postDataJSON()
        commands.push({
          method: request.method(),
          id: body.request_id,
          version: body.expected_version,
        })
      }
    })
    await page.goto(origin + '/manage/sources')
    await page.getByRole('heading', { name: '系统来源凭证', exact: true }).waitFor()
    const csrf = (await context.cookies()).find((cookie) => cookie.name === 'csrftoken').value
    async function api(method, path, body) {
      const response = await page.request[method](origin + '/nassav/api' + path, {
        headers: { 'X-CSRFToken': csrf },
        ...(body ? { data: body } : {}),
      })
      assert.ok(response.ok(), `${method} ${path}: ${response.status()}`)
      return (await response.json()).data
    }
    const cookie = 'cf_clearance=Temporary-' + randomUUID()
    const agent = 'Nassav-isolated-browser/1.0'
    const editor = page.getByRole('dialog', { name: '系统访问验证凭证', exact: true })
    const row = () =>
      page.getByRole('row').filter({ has: page.getByRole('rowheader', { name: /^jable/ }) })
    const existing = (await api('get', '/admin/source-credentials')).find(
      (item) => item.source_name === 'jable'
    )
    if (existing)
      await row().getByRole('button', { name: '更新系统凭证 jable', exact: true }).click()
    else {
      await page.getByRole('button', { name: '添加系统凭证', exact: true }).click()
      await editor.getByLabel('来源', { exact: true }).click()
      await page.getByRole('option', { name: /^jable$/i }).click()
    }
    await editor
      .getByLabel('新的访问验证 Cookie', { exact: true })
      .fill('account_session=private-account')
    await editor.getByLabel('配套 User-Agent', { exact: true }).fill(agent)
    await editor.getByRole('button', { name: '下一步', exact: true }).click()
    await editor
      .getByText('仅接受 cf_clearance、__cf_bm、__cflb，不能包含账号 Cookie', { exact: true })
      .waitFor()
    assert.equal(commands.length, 0)
    await editor.getByLabel('新的访问验证 Cookie', { exact: true }).fill(cookie)
    let dropped = false
    await page.route('**/nassav/api/admin/source-credentials{,/*}', async (route) => {
      if (route.request().method() === 'GET' || dropped) return route.continue()
      dropped = true
      const response = await route.fetch()
      assert.equal(response.status(), 200)
      await route.abort('failed')
    })
    async function execute() {
      await editor.getByRole('button', { name: '下一步', exact: true }).click()
      await page.getByRole('button', { name: '确认执行', exact: true }).click()
    }
    await execute()
    await editor.getByText('网络错误', { exact: true }).waitFor()
    assert.equal(
      await editor.getByLabel('新的访问验证 Cookie', { exact: true }).inputValue(),
      cookie
    )
    await execute()
    await editor.waitFor({ state: 'hidden' })
    assert.deepEqual(commands[0], commands[1])
    assert.ok(!JSON.stringify(await api('get', '/admin/source-credentials')).includes(cookie))
    await row().getByRole('button', { name: '更新系统凭证 jable', exact: true }).click()
    assert.equal(await editor.getByLabel('新的访问验证 Cookie', { exact: true }).inputValue(), '')
    await editor.getByLabel('新的访问验证 Cookie', { exact: true }).fill(cookie)
    await editor.getByLabel('配套 User-Agent', { exact: true }).fill(agent)
    let credential = (await api('get', '/admin/source-credentials')).find(
      (item) => item.source_name === 'jable'
    )
    await api('put', '/admin/source-credentials/' + credential.id, {
      expected_version: credential.version,
      request_id: randomUUID(),
      reason: 'maintenance',
      cookie: 'cf_clearance=another-editor',
      user_agent: agent,
      kind: 'clearance',
    })
    await execute()
    await editor
      .getByText('凭证版本已变化，输入已保留。请关闭后刷新列表并重新编辑。', { exact: true })
      .waitFor()
    assert.equal(
      await editor.getByLabel('新的访问验证 Cookie', { exact: true }).inputValue(),
      cookie
    )
    await editor.getByRole('button', { name: '关闭', exact: true }).click()
    await page
      .getByRole('dialog', { name: '尚未保存', exact: true })
      .getByRole('button', { name: '放弃输入', exact: true })
      .click()
    await editor.waitFor({ state: 'hidden' })
    await page.getByRole('button', { name: '刷新凭证', exact: true }).click()
    credential = (await api('get', '/admin/source-credentials')).find(
      (item) => item.source_name === 'jable'
    )
    await row()
      .getByRole('cell', { name: String(credential.version), exact: true })
      .waitFor()
    await row().getByRole('button', { name: '撤销系统凭证 jable', exact: true }).click()
    const revoke = page.getByRole('dialog', { name: '撤销系统凭证', exact: true })
    await revoke.getByRole('button', { name: '下一步', exact: true }).click()
    await page.keyboard.press('Escape')
    await page
      .getByRole('dialog', { name: '确认撤销系统凭证', exact: true })
      .waitFor({ state: 'hidden' })
    await revoke.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '确认执行', exact: true }).click()
    await revoke.waitFor({ state: 'hidden' })
    await row().getByRole('cell', { name: '已撤销', exact: true }).waitFor()
    assert.equal(
      await row().getByRole('button', { name: '撤销系统凭证 jable', exact: true }).isDisabled(),
      true
    )
    for (const theme of ['light', 'dark']) {
      await page.setViewportSize({ width: 390, height: 844 })
      await page.evaluate(
        (theme) => document.documentElement.classList.toggle('dark', theme === 'dark'),
        theme
      )
      await row().getByRole('button', { name: '更新系统凭证 jable', exact: true }).click()
      await editor.getByLabel('新的访问验证 Cookie', { exact: true }).fill(cookie)
      await editor.getByLabel('配套 User-Agent', { exact: true }).fill(agent)
      await editor.getByRole('button', { name: '下一步', exact: true }).scrollIntoViewIfNeeded()
      const bounds = await editor.boundingBox()
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 845)
      assert.equal(
        await page.evaluate(() => Boolean(document.activeElement.closest('[role=dialog]'))),
        true
      )
      await page.keyboard.press('Escape')
      await page
        .getByRole('dialog', { name: '尚未保存', exact: true })
        .getByRole('button', { name: '放弃输入', exact: true })
        .click()
      await editor.waitFor({ state: 'hidden' })
    }
    const audit = await api('get', '/admin/audit')
    assert.ok(!JSON.stringify(audit).includes(cookie))
    const storage = JSON.stringify(await context.storageState())
    assert.ok(!storage.includes(cookie) && !storage.includes(agent))
    assert.deepEqual(errors, [])
    console.log('Native system credential blind write/replay/CAS/revoke/theme/mobile checks passed')
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
