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
      passwordCommands = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (new URL(request.url()).pathname.endsWith('/reset-password')) {
        const body = request.postDataJSON()
        passwordCommands.push({
          request_id: body.request_id,
          expected_version: body.expected_version,
        })
      }
    })
    const password = 'Temporary-' + randomUUID() + '-A9!'
    const nextPassword = 'Changed-' + randomUUID() + '-B8!'
    await page.goto(origin + '/personal/general')
    await page.getByRole('button', { name: '管理中心', exact: true }).click()
    await page.getByRole('heading', { name: '管理中心', exact: true }).waitFor()
    await page
      .getByText('多账号登录尚未开放；创建账号不会改变当前登录策略。', { exact: true })
      .waitFor()
    const editor = page
      .getByRole('dialog')
      .filter({ has: page.getByRole('button', { name: '下一步', exact: true }) })
    const row = (username) =>
      page
        .getByRole('row')
        .filter({ has: page.getByRole('rowheader', { name: new RegExp('^' + username) }) })
    const refreshed = () =>
      page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname.endsWith('/admin/users') &&
          response.request().method() === 'GET' &&
          response.status() === 200
      )
    async function execute() {
      await editor.getByRole('button', { name: '下一步', exact: true }).click()
      const loaded = refreshed()
      await page.getByRole('button', { name: '确认执行', exact: true }).click()
      await loaded
      await editor.waitFor({ state: 'hidden' })
    }
    async function discard() {
      await editor.getByRole('button', { name: '关闭', exact: true }).click()
      await page
        .getByRole('dialog', { name: '放弃未提交的输入', exact: true })
        .getByRole('button', { name: '放弃输入', exact: true })
        .click()
      await editor.waitFor({ state: 'hidden' })
    }
    await page.getByRole('button', { name: '创建账号', exact: true }).click()
    await editor.getByRole('button', { name: '下一步', exact: true }).click()
    await editor.getByText('密码长度需为12至256个字符', { exact: true }).waitFor()
    await editor.getByLabel('用户名', { exact: true }).fill('ui-member')
    await editor.getByLabel('新密码', { exact: true }).fill(password)
    await execute()
    await row('ui-member').waitFor()
    const csrf = (await context.cookies()).find((cookie) => cookie.name === 'csrftoken').value
    async function api(path, method = 'get', body) {
      const response = await page.request[method](origin + '/nassav/api' + path, {
        headers: { 'X-CSRFToken': csrf },
        ...(body ? { data: body } : {}),
      })
      assert.ok(response.ok(), `${method} ${path}: ${response.status()}`)
      return (await response.json()).data
    }
    let member = (await api('/admin/users')).find((item) => item.username === 'ui-member')
    await row('ui-member').getByRole('button', { name: '编辑账号 ui-member', exact: true }).click()
    await editor.getByLabel('活动请求上限', { exact: true }).fill('4')
    await api(`/admin/users/${member.user_id}`, 'patch', {
      expected_version: member.version,
      request_id: await page.evaluate(() => crypto.randomUUID()),
      reason: 'quota_adjustment',
      max_active_operations: 3,
    })
    await editor.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '确认执行', exact: true }).click()
    await editor
      .getByText('账号版本或状态已变化。输入已保留，请关闭后刷新列表并重新编辑。', { exact: true })
      .waitFor()
    assert.equal(await editor.getByLabel('活动请求上限', { exact: true }).inputValue(), '4')
    await discard()
    const loaded = refreshed()
    await page.getByRole('button', { name: '刷新账号', exact: true }).click()
    await loaded
    await row('ui-member').getByRole('cell', { name: '3', exact: true }).waitFor()
    await row('ui-member').getByRole('button', { name: '编辑账号 ui-member', exact: true }).click()
    await editor.getByLabel('活动请求上限', { exact: true }).fill('4')
    await editor.getByRole('checkbox', { name: '不限制存储配额', exact: true }).uncheck()
    await editor.getByLabel('存储配额（GiB）', { exact: true }).fill('1.5')
    await execute()
    member = (await api('/admin/users')).find((item) => item.username === 'ui-member')
    assert.equal(member.max_active_operations, 4)
    assert.equal(member.storage_quota_bytes, 1.5 * 1024 ** 3)
    let dropped = false
    await page.route('**/nassav/api/admin/users/*/reset-password', async (route) => {
      if (dropped) return route.continue()
      dropped = true
      const response = await route.fetch()
      assert.equal(response.status(), 200)
      await route.abort('failed')
    })
    await row('ui-member').getByRole('button', { name: '重置密码 ui-member', exact: true }).click()
    await editor.getByLabel('新密码', { exact: true }).fill(nextPassword)
    await editor.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '确认执行', exact: true }).click()
    await editor.getByText('网络错误', { exact: true }).waitFor()
    assert.equal(await editor.getByLabel('新密码', { exact: true }).inputValue(), nextPassword)
    await execute()
    assert.equal(passwordCommands.length, 2)
    assert.deepEqual(passwordCommands[0], passwordCommands[1])
    await row('ui-member').getByRole('button', { name: '撤销会话 ui-member', exact: true }).click()
    await execute()
    for (const role of ['管理员', '普通用户']) {
      await row('ui-member')
        .getByRole('button', { name: '编辑账号 ui-member', exact: true })
        .click()
      await editor.getByLabel('应用角色', { exact: true }).click()
      await page.getByRole('option', { name: role, exact: true }).click()
      await execute()
      await row('ui-member').getByRole('cell', { name: role, exact: true }).waitFor()
    }
    await row('operation-other')
      .getByRole('button', { name: '编辑账号 operation-other', exact: true })
      .click()
    await editor.getByRole('checkbox', { name: '启用账号', exact: true }).uncheck()
    await execute()
    await row('operation-other').getByRole('cell', { name: '停用', exact: true }).waitFor()
    await row('operation-other')
      .getByRole('button', { name: '编辑账号 operation-other', exact: true })
      .click()
    await editor.getByRole('checkbox', { name: '启用账号', exact: true }).check()
    await execute()
    await row('operation-other').getByRole('cell', { name: '启用', exact: true }).waitFor()
    await row('nassav').getByRole('button', { name: '编辑账号 nassav', exact: true }).click()
    await editor.getByRole('checkbox', { name: '启用账号', exact: true }).uncheck()
    await editor.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '确认执行', exact: true }).click()
    await editor.getByText('需要保留至少一个启用的管理员，未执行修改', { exact: true }).waitFor()
    await discard()
    const login = await page.request.post(origin + '/nassav/api/auth/login', {
      headers: { 'X-CSRFToken': csrf },
      data: { username: 'ui-member', password: nextPassword },
    })
    assert.equal(login.status(), 401, 'Account creation must not open multi-account admission')
    const audit = await api('/admin/audit')
    assert.ok(audit.some((item) => item.action === 'account.reset_password'))
    assert.ok(
      !JSON.stringify(audit).includes(password) && !JSON.stringify(audit).includes(nextPassword),
      'Audit must exclude passwords'
    )
    await page.getByRole('button', { name: '审计记录', exact: true }).click()
    await page.getByRole('heading', { name: '审计记录', exact: true }).waitFor()
    await page.getByRole('cell', { name: '重置密码', exact: true }).waitFor()
    const disk = JSON.stringify(await context.storageState())
    assert.ok(
      !disk.includes(password) && !disk.includes(nextPassword),
      'Passwords must not persist to browser storage'
    )
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '账号管理', exact: true }).click()
    await row('ui-member').getByRole('button', { name: '编辑账号 ui-member', exact: true }).click()
    for (const theme of ['light', 'dark']) {
      await page.evaluate((mode) => {
        document.body.classList.toggle('dark-mode', mode === 'dark')
        document.body.classList.toggle('light-mode', mode === 'light')
      }, theme)
      await page.waitForTimeout(400)
      const bounds = await editor.boundingBox()
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 844)
      await editor.getByRole('button', { name: '下一步', exact: true }).focus()
      await page.keyboard.press('Tab')
      assert.equal(await editor.evaluate((node) => node.contains(document.activeElement)), true)
    }
    await page.keyboard.press('Escape')
    await editor.waitFor({ state: 'hidden' })
    assert.deepEqual(errors, [])
    console.log(
      'Native admin account UI passed: create, quota CAS, password lost-response replay, revoke, disable/enable, last-admin protection, closed login, audit, mobile and secrets cleanup'
    )
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
