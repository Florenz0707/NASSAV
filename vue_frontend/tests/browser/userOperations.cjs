const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')

;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium
      ? { executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome' }
      : {}
  )
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4187'
  assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/)
  const target = process.env.NASSAV_OPERATION_AVID || 'OPERATION-UI'
  const remaining = target === 'OPERATION-UI' ? 'OPERATION-SECOND' : 'OPERATION-UI'
  const state = process.env.NASSAV_OPERATION_STORAGE_STATE
  assert.ok(state, 'Explicit isolated HTTP login state is required')
  try {
    const context = await browser.newContext({
      storageState: state,
      viewport: { width: 1440, height: 1050 },
    })
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    const failures = [],
      legacy = [],
      commands = []
    page.on('pageerror', (error) => failures.push(error.message))
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname
      if (/\/tasks\/(jobs|queue)|\/resource\/jobs|\/download\//.test(path)) legacy.push(path)
      if (request.method() === 'POST') commands.push(path)
    })
    await page.goto(origin + '/downloads')
    await page.getByRole('heading', { name: '任务详情', exact: true }).waitFor()
    await page.getByText('OPERATION-UI', { exact: true }).first().waitFor()
    assert.equal(await page.getByRole('columnheader', { name: '暂停/恢复' }).count(), 0)
    assert.equal(await page.getByRole('button', { name: '暂停所选' }).count(), 0)
    const before = await page.request.get(origin + '/nassav/api/my-operations')
    const initial = await before.json()
    assert.equal(initial.data.length, 2)
    const id = initial.data.find((item) => item.avid === target).operation_id
    for (const theme of ['dark', 'light']) {
      await page.evaluate((mode) => {
        document.body.classList.toggle('dark-mode', mode === 'dark')
        document.body.classList.toggle('light-mode', mode === 'light')
      }, theme)
      await page.getByRole('button', { name: '查看任务跟踪说明' }).click()
      const information = page.getByRole('dialog')
      await information.getByText('取消任务不会删除已保存的资源', { exact: false }).waitFor()
      await page.keyboard.press('Escape')
      await information.waitFor({ state: 'hidden' })
    }
    await page.getByRole('button', { name: `取消任务 ${target}`, exact: true }).click()
    let dialog = page.getByRole('dialog')
    await dialog.getByText('已保存的资源会保留', { exact: false }).waitFor()
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    assert.equal(commands.filter((path) => path.endsWith('/cancel')).length, 0)
    if (process.env.NASSAV_OPERATION_USE_BULK === '1') {
      await page.getByRole('checkbox', { name: `选择任务 ${target}`, exact: true }).check()
      await page.getByRole('button', { name: '取消所选任务', exact: true }).click()
    } else await page.getByRole('button', { name: `取消任务 ${target}`, exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: '取消任务', exact: true }).click()
    await page.waitForFunction(
      async ({ origin, id }) => {
        const response = await fetch(`${origin}/nassav/api/my-operations/${id}`)
        return (await response.json()).data.state === 'cancelled'
      },
      { origin, id }
    )
    assert.equal(commands.filter((path) => path.endsWith('/cancel')).length, 1)
    await page.getByRole('button', { name: `取消任务 ${target}`, exact: true }).waitFor()
    assert.equal(
      await page.getByRole('button', { name: `取消任务 ${target}`, exact: true }).isDisabled(),
      true
    )
    const finishedRow = page
      .getByRole('row')
      .filter({ has: page.getByRole('button', { name: `不再跟踪任务 ${target}`, exact: true }) })
    assert.equal(await finishedRow.getByText('已取消', { exact: true }).count(), 2)
    await page.getByRole('button', { name: `不再跟踪任务 ${target}`, exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: '不再跟踪', exact: true }).click()
    await page
      .getByRole('button', { name: `不再跟踪任务 ${target}`, exact: true })
      .waitFor({ state: 'hidden' })
    await page.reload()
    await page.getByText(remaining, { exact: true }).first().waitFor()
    assert.equal(
      await page.getByRole('button', { name: `不再跟踪任务 ${target}`, exact: true }).count(),
      0
    )
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '查看任务跟踪说明' }).click()
    dialog = page.getByRole('dialog')
    assert.ok(await dialog.isVisible())
    await page.keyboard.press('Escape')
    assert.deepEqual(legacy, [], 'Shared mode must never poll legacy jobs or queues')
    assert.deepEqual(failures, [])
    console.log(
      'Native HTTP user operations passed: cancel, hidden persistence, themes, dialog keyboard, mobile, no legacy task access'
    )
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
