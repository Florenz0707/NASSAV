// Opt-in real HTTP/SQLite check using the disposable local_playback_server fixture.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  if (!process.env.NASSAV_PERSONAL_STORAGE_STATE) {
    console.log('Personal state check skipped: disposable storage state required')
    return
  }
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium
      ? { executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome' }
      : {}
  )
  const context = await browser.newContext({
    storageState: process.env.NASSAV_PERSONAL_STORAGE_STATE,
    viewport: { width: 1440, height: 1000 },
  })
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
  const api = `${origin}/nassav/api`,
    avid = 'LOCAL-PLAYBACK',
    errors = []
  await context.routeWebSocket('**/nassav/ws/**', () => {})
  const page = await context.newPage()
  page.on('pageerror', (error) => errors.push(error.message))
  const headers = async () => ({
    'X-CSRFToken': (await context.cookies(origin)).find((c) => c.name === 'csrftoken').value,
  })
  const patch = async (body) => {
    const response = await context.request.patch(`${api}/resource/${avid}/status`, {
      data: body,
      headers: await headers(),
    })
    assert.equal(response.status(), 200)
    return (await response.json()).data
  }
  const read = async () =>
    (await (await context.request.get(`${api}/resource/metadata?avid=${avid}`)).json()).data
  try {
    assert.equal((await context.request.get(`${api}/auth/session`)).status(), 200)
    await patch({ watched: false, is_favorite: false, notes: '' })
    await page.goto(`${origin}/resource/${avid}`)
    const panel = page.getByRole('region', { name: '个人资源状态' })
    const notes = panel.getByLabel('个人备注', { exact: true })
    await notes.waitFor()
    const draft = '我的私人备注\n<script>只作为文本</script>'
    await notes.fill(draft)
    const save = panel.getByRole('button', { name: '保存备注', exact: true })
    await save.focus()
    await page.keyboard.press('Enter')
    await page.getByText('备注已保存', { exact: true }).waitFor()
    assert.equal((await read()).notes, draft)
    await page.reload()
    await notes.waitFor()
    assert.equal(await notes.inputValue(), draft)
    await panel.getByRole('button', { name: '收藏', exact: true }).click()
    await panel.getByRole('button', { name: '已收藏', exact: true }).waitFor()
    await panel.getByRole('button', { name: '标记观看', exact: true }).click()
    await panel.getByRole('button', { name: '已观看', exact: true }).waitFor()
    assert.equal((await read()).is_favorite, true)
    assert.equal((await read()).watched, true)
    const list = await context.request.get(`${api}/resources?is_favorite=true&watched=true`)
    assert.deepEqual(
      (await list.json()).data.map((r) => r.avid),
      [avid]
    )
    await notes.fill('我的未提交草稿')
    await patch({ notes: '另一页面的更新' })
    await save.click()
    await panel.getByRole('alert').filter({ hasText: '草稿已保留' }).waitFor()
    assert.equal(await notes.inputValue(), '我的未提交草稿')
    assert.equal((await read()).notes, '另一页面的更新')
    await Promise.all([
      page.waitForResponse(
        (response) => response.request().method() === 'PATCH' && response.url().includes('/status')
      ),
      save.click(),
    ])
    await panel.getByRole('alert').waitFor({ state: 'hidden' })
    assert.equal((await read()).notes, '我的未提交草稿')
    await panel.getByRole('button', { name: '清空', exact: true }).click()
    assert.equal((await read()).notes, '我的未提交草稿')
    await save.click()
    await save.waitFor({ state: 'visible' })
    await page.waitForFunction(
      () =>
        document.querySelector('textarea')?.value === '' &&
        [...document.querySelectorAll('button')].some(
          (b) => b.textContent.trim() === '保存备注' && b.disabled
        )
    )
    assert.equal((await read()).notes, '')
    for (const mode of ['light', 'dark']) {
      const settingsResponse = await context.request.put(`${api}/setting`, {
        data: { color_mode: mode },
        headers: await headers(),
      })
      assert.equal(settingsResponse.status(), 200)
      await page.reload()
      await page.locator(`body.${mode}-mode`).waitFor()
      await panel.waitFor()
      await page.setViewportSize({ width: mode === 'dark' ? 390 : 1440, height: 1000 })
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      await page.waitForTimeout(700)
      await page.screenshot({
        path: `/tmp/nassav-personal-${process.env.NASSAV_BROWSER_ENGINE || 'chromium'}-${mode}.png`,
        fullPage: true,
      })
      const style = await save.evaluate((button) => ({
        color: getComputedStyle(button).color,
        background: getComputedStyle(button).backgroundColor,
      }))
      assert.notEqual(style.color, style.background)
    }
    await page.goto(`${origin}/settings`)
    await page.getByRole('button', { name: '浅色', exact: true }).click()
    await page.getByRole('button', { name: '保存设置', exact: true }).click()
    await page.getByText('设置已保存', { exact: true }).waitFor()
    await page.reload()
    await page.locator('body.light-mode').waitFor()
    await page.getByRole('button', { name: '深色', exact: true }).click()
    await page.getByRole('button', { name: '保存设置', exact: true }).click()
    await page.getByText('设置已保存', { exact: true }).waitFor()
    await page.reload()
    await page.locator('body.dark-mode').waitFor()
    const setting = (await (await context.request.get(`${api}/setting`)).json()).data
    assert.equal(setting.color_mode, 'dark')
    assert.deepEqual(errors, [])
    console.log(
      'PASS real API: personal notes save/clear/reload, keyboard, favorites/watched filters, conflict draft, theme persistence and mobile layout'
    )
  } finally {
    await context.close()
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
