const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { randomUUID } = require('node:crypto')
;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4188'
  const avid = process.env.NASSAV_WORK_UI_AVID || 'OPERATION-UI'
  assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/)
  assert.ok(process.env.NASSAV_LIBRARY_STORAGE_STATE, 'Disposable administrator fixture required')
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
        request.method() === 'POST' &&
        /\/tasks\/jobs\/.+\/(pause|resume|cancel)$/.test(new URL(request.url()).pathname)
      )
        commands.push(request.postDataJSON())
    })
    await page.goto(origin + '/manage/work')
    await page.getByRole('heading', { name: '全局执行管理', exact: true }).waitFor()
    const csrf = (await context.cookies()).find((cookie) => cookie.name === 'csrftoken').value
    async function api(method, path, body) {
      const response = await page.request[method](origin + '/nassav/api' + path, {
        headers: { 'X-CSRFToken': csrf },
        ...(body ? { data: body } : {}),
      })
      assert.ok(response.ok(), `${method} ${path}: ${response.status()}`)
      return (await response.json()).data
    }
    const row = page
      .getByRole('row')
      .filter({ has: page.getByRole('rowheader', { name: new RegExp('^' + avid) }) })
    const operation = (await api('get', '/my-operations')).find((item) => item.avid === avid)
    assert.ok(operation)
    const job = (await api('get', '/tasks/jobs')).jobs.find((item) => item.avid === avid)
    assert.equal(job.state, 'queued')
    let dropped = false
    await page.route('**/nassav/api/tasks/jobs/*/pause', async (route) => {
      if (dropped) return route.continue()
      dropped = true
      const response = await route.fetch()
      assert.equal(response.status(), 202)
      await route.abort('failed')
    })
    const dialog = (title) => page.getByRole('dialog', { name: title, exact: true })
    async function submit(title) {
      await dialog(title).getByRole('button', { name: '下一步', exact: true }).click()
      await page.getByRole('button', { name: '确认执行', exact: true }).click()
    }
    await row.getByRole('button', { name: '暂停执行 ' + job.job_id, exact: true }).click()
    await submit('暂停执行')
    await dialog('暂停执行').getByText('网络错误', { exact: true }).waitFor()
    await submit('暂停执行')
    await dialog('暂停执行').waitFor({ state: 'hidden' })
    await row.getByText('已暂停', { exact: true }).first().waitFor()
    assert.deepEqual(commands[0], commands[1])
    assert.equal((await api('get', '/my-operations/' + operation.operation_id)).state, 'paused')
    await row.getByRole('button', { name: '恢复执行 ' + job.job_id, exact: true }).click()
    const current = await api('get', '/tasks/jobs/' + job.job_id)
    await api('post', '/tasks/jobs/' + job.job_id + '/resume', {
      expected_version: current.version,
      reason: 'maintenance',
      request_id: randomUUID(),
    })
    await submit('恢复执行')
    await dialog('恢复执行')
      .getByText('执行状态已变化，请关闭后刷新列表再确认。不会自动采用新版本执行。', {
        exact: true,
      })
      .waitFor()
    await dialog('恢复执行').getByRole('button', { name: '关闭', exact: true }).click()
    await page.getByRole('button', { name: '刷新执行', exact: true }).click()
    await row.getByText('排队中', { exact: true }).waitFor()
    await row.getByRole('button', { name: '暂停执行 ' + job.job_id, exact: true }).click()
    await submit('暂停执行')
    await dialog('暂停执行').waitFor({ state: 'hidden' })
    await row.getByText('已暂停', { exact: true }).first().waitFor()
    await row.getByRole('button', { name: '恢复执行 ' + job.job_id, exact: true }).click()
    await submit('恢复执行')
    await dialog('恢复执行').waitFor({ state: 'hidden' })
    await row.getByText('排队中', { exact: true }).waitFor()
    for (const theme of ['light', 'dark']) {
      await page.setViewportSize({ width: 390, height: 844 })
      await page.evaluate(
        (theme) => document.documentElement.classList.toggle('dark', theme === 'dark'),
        theme
      )
      await row.getByRole('button', { name: '终止执行 ' + job.job_id, exact: true }).click()
      const cancel = dialog('终止执行')
      await cancel.getByRole('button', { name: '下一步', exact: true }).click()
      await page.keyboard.press('Escape')
      await dialog('确认终止执行').waitFor({ state: 'hidden' })
      assert.ok(await cancel.isVisible())
      const bounds = await cancel.boundingBox()
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 845)
      await cancel.getByRole('button', { name: '关闭', exact: true }).click()
    }
    await page.setViewportSize({ width: 1440, height: 1050 })
    await row.getByRole('button', { name: '终止执行 ' + job.job_id, exact: true }).click()
    await submit('终止执行')
    await dialog('终止执行').waitFor({ state: 'hidden' })
    await row.getByText('已终止', { exact: true }).first().waitFor()
    assert.equal((await api('get', '/my-operations/' + operation.operation_id)).state, 'cancelled')
    assert.equal(
      await row.getByRole('button', { name: '终止执行 ' + job.job_id, exact: true }).isDisabled(),
      true
    )
    const audit = await api('get', '/admin/audit')
    assert.equal(
      audit.filter((item) => item.action === 'work.pause' && item.object_id === job.job_id).length,
      2,
      'Lost response replay must not duplicate the pause audit'
    )
    assert.ok(audit.some((item) => item.action === 'work.cancel' && item.object_id === job.job_id))
    assert.deepEqual(errors, [])
    console.log(
      'Native administrator work pause/replay/conflict/resume/cancel/own projection/mobile checks passed'
    )
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
