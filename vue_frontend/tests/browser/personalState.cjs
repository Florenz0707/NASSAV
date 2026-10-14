// Opt-in real HTTP/SQLite; synthetic fixture only, no production writes.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
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
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
  assert.equal(new URL(origin).hostname, '127.0.0.1')
  await context.routeWebSocket('**/nassav/ws/**', () => {})
  const page = await context.newPage(),
    errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  let stage = 'setup'
  const timer = setTimeout(() => {
    console.error(`Timeout: ${stage}`)
    process.exitCode = 1
    void browser.close()
  }, 120000)
  const api = `${origin}/nassav/api`,
    avid = 'LOCAL-PLAYBACK'
  const headers = async () => ({
    'X-CSRFToken': (await context.cookies(origin)).find((c) => c.name === 'csrftoken').value,
  })
  const patch = async (body) => {
    const response = await context.request.patch(`${api}/resource/${avid}/status`, {
      data: body,
      headers: await headers(),
      timeout: 10000,
    })
    assert.equal(response.status(), 200)
    return (await response.json()).data
  }
  const read = async () =>
    (
      await (
        await context.request.get(`${api}/resource/metadata?avid=${avid}`, { timeout: 10000 })
      ).json()
    ).data
  const edit = page.getByRole('button', { name: '编辑个人备注' })
  const modal = page.getByRole('dialog', { name: '编辑个人备注', exact: true })
  const notes = modal.getByLabel('个人备注', { exact: true }),
    save = modal.getByRole('button', { name: '保存', exact: true })
  const until = async (check) => {
    for (let i = 0; i < 80; i++) {
      if (await check()) return
      await page.waitForTimeout(100)
    }
    throw new Error(`Timeout: ${stage}`)
  }
  try {
    await patch({ watched: false, is_favorite: false, watch_later: false, notes: '' })
    await page.bringToFront()
    await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded' })
    assert.equal(await page.getByRole('region', { name: '继续观看', exact: true }).count(), 0)
    assert.equal(
      await page
        .locator('nav.navbar')
        .getByRole('button', { name: '退出登录', exact: true })
        .count(),
      0
    )
    await page.locator('nav.navbar').getByRole('link', { name: '个人中心', exact: true }).click()
    await page.getByRole('heading', { name: '个人中心', exact: true }).waitFor()
    const navigation = page.getByRole('navigation', { name: '个人中心功能' })
    const counts = new Map()
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname
      if (
        request.method() === 'GET' &&
        /personal\/(history|watch-later)$|\/setting$|search-capabilities$/.test(path)
      )
        counts.set(path, (counts.get(path) || 0) + 1)
    })
    for (const name of ['稍后再看', '观看历史', '通用设置', '播放设置', '退出登录'])
      await navigation.getByRole('button', { name, exact: true }).waitFor()
    await navigation.getByRole('button', { name: '通用设置', exact: true }).click()
    await page.getByRole('heading', { name: '通用设置', exact: true }).waitFor()
    assert.equal(await page.locator('#playback-volume').count(), 0)
    await navigation.getByRole('button', { name: '播放设置', exact: true }).click()
    await page.locator('#playback-volume').waitFor()
    assert.equal(await page.getByRole('heading', { name: '通用设置', exact: true }).count(), 0)
    await navigation.getByRole('button', { name: '观看历史', exact: true }).click()
    await page.getByRole('heading', { name: '观看历史', exact: true }).waitFor()
    await page.getByText('暂无观看历史', { exact: true }).waitFor()
    const before = new Map(counts)
    for (const name of ['通用设置', '播放设置', '观看历史']) {
      await navigation.getByRole('button', { name, exact: true }).click()
      await page.getByRole('heading', { name, exact: true }).waitFor()
    }
    assert.deepEqual(counts, before, 'section switches within TTL do not re-fetch')
    stage = 'detail alignment and icon buttons'
    await page.goto(`${origin}/resource/${avid}`, { waitUntil: 'domcontentloaded' })
    await edit.waitFor()
    assert.equal(await page.locator('textarea').count(), 0)
    const panel = page.getByRole('region', { name: '个人资源状态' })
    const favorite = panel.getByRole('button', { name: '收藏', exact: true }),
      watched = panel.getByRole('button', { name: '已观看', exact: true }),
      later = panel.getByRole('button', { name: '稍后再看', exact: true })
    for (const button of [favorite, watched, later])
      assert.equal((await button.innerText()).trim(), '')
    await favorite.click()
    await until(async () => (await favorite.getAttribute('aria-pressed')) === 'true')
    await watched.click()
    await until(async () => (await watched.getAttribute('aria-pressed')) === 'true')
    await later.click()
    await until(async () => (await later.getAttribute('aria-pressed')) === 'true')
    assert.equal((await read()).watch_later, true)
    const image = page.getByRole('img', { name: /资源封面/ }).first()
    await image.waitFor()
    await page.waitForFunction(() => document.querySelector('img')?.complete)
    const imageBox = await image.boundingBox(),
      avidBox = await page.getByText(avid, { exact: true }).first().boundingBox()
    assert.ok(Math.abs(imageBox.y - avidBox.y) < 2, `cover ${imageBox.y} vs info ${avidBox.y}`)
    const boxes = await Promise.all(
      [favorite, watched, later].map((button) => button.boundingBox())
    )
    assert.ok(Math.abs(boxes[0].x - imageBox.x) < 2)
    assert.ok(Math.abs(boxes[2].x + boxes[2].width - imageBox.x - imageBox.width) < 2)
    assert.ok(Math.abs(boxes[0].y - imageBox.y - imageBox.height - 19.2) < 2, 'cover gap is 1.2rem')
    assert.ok(Math.abs(boxes[0].width - boxes[2].width) < 1)
    assert.equal((await edit.innerText()).trim(), '')
    stage = 'dirty close escape route and save'
    await edit.click()
    await notes.fill('未保存的草稿')
    await modal.getByRole('button', { name: '关闭', exact: true }).click()
    const warning = page.getByRole('dialog', { name: '尚未保存', exact: true })
    await warning.getByRole('button', { name: '继续编辑' }).click()
    await warning.waitFor({ state: 'hidden' })
    assert.equal(await notes.inputValue(), '未保存的草稿')
    await page.keyboard.press('Escape')
    await warning.waitFor()
    await warning.getByRole('button', { name: '继续编辑' }).click()
    await warning.waitFor({ state: 'hidden' })
    // Focus stays in the nested editor and returns after cancelling the warning.
    assert.ok(await modal.evaluate((node) => node.contains(document.activeElement)))
    const failedNavigation = page.evaluate(() =>
      window.dispatchEvent(new Event('beforeunload', { cancelable: true }))
    )
    assert.equal(await failedNavigation, false)
    await page
      .locator('nav.navbar')
      .getByRole('link', { name: '个人中心', exact: true })
      .evaluate((node) => node.click())
    await warning.waitFor()
    assert.ok(page.url().includes('/resource/'))
    await warning.getByRole('button', { name: '继续编辑' }).click()
    await warning.waitFor({ state: 'hidden' })
    const draft = '我的私人备注\n<script>只作为文本</script>'
    await notes.fill(draft)
    await save.focus()
    await page.keyboard.press('Enter')
    await modal.waitFor({ state: 'hidden' })
    assert.equal((await read()).notes, draft)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await edit.waitFor()
    assert.equal(await page.locator('textarea').count(), 0)
    await edit.click()
    assert.equal(await notes.inputValue(), draft)
    stage = 'conflict and failed save keep draft'
    await notes.fill('我的未提交草稿')
    await patch({ notes: '另一页面的更新' })
    await save.click()
    await modal.getByRole('alert').filter({ hasText: '草稿已保留' }).waitFor()
    assert.equal(await notes.inputValue(), '我的未提交草稿')
    await save.click()
    await modal.waitFor({ state: 'hidden' })
    assert.equal((await read()).notes, '我的未提交草稿')
    await edit.click()
    await modal.getByRole('button', { name: '清空', exact: true }).click()
    assert.equal((await read()).notes, '我的未提交草稿')
    await save.click()
    await modal.waitFor({ state: 'hidden' })
    assert.equal((await read()).notes, '')
    await edit.click()
    await notes.fill('放弃的修改')
    await modal.getByRole('button', { name: '关闭', exact: true }).click()
    await warning.getByRole('button', { name: '放弃修改' }).click()
    await modal.waitFor({ state: 'hidden' })
    assert.equal((await read()).notes, '')
    stage = 'themes mobile long notes and dialog keyboard'
    await patch({ notes: '长备注'.repeat(600) })
    for (const mode of ['light', 'dark']) {
      await context.request.put(`${api}/setting`, {
        data: { color_mode: mode },
        headers: await headers(),
      })
      await page.reload({ waitUntil: 'domcontentloaded' })
      await edit.waitFor()
      await page.locator(`body.${mode}-mode`).waitFor()
      await page.setViewportSize({ width: mode === 'dark' ? 390 : 1440, height: 1000 })
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
      await page.waitForFunction(() => {
        const img = document.querySelector('.detail-cover img')
        return img?.complete && img.naturalWidth > 0
      })
      const geometry = await panel.evaluate((node) => {
        const box = (element) => {
          const r = element.getBoundingClientRect()
          return { x: r.x, y: r.y, width: r.width, height: r.height }
        }
        return {
          cover: box(node.querySelector('.detail-cover img')),
          controls: ['收藏', '已观看', '稍后再看'].map((label) =>
            box(node.querySelector(`button[aria-label="${label}"]`))
          ),
          rem: parseFloat(getComputedStyle(document.documentElement).fontSize),
        }
      })
      const { cover, controls, rem } = geometry
      assert.ok(Math.abs(controls[0].x - cover.x) < 2, JSON.stringify(geometry))
      assert.ok(
        Math.abs(controls[2].x + controls[2].width - cover.x - cover.width) < 2,
        JSON.stringify(geometry)
      )
      assert.ok(
        Math.abs(controls[0].y - cover.y - cover.height - 1.2 * rem) < 2,
        JSON.stringify(geometry)
      )
      await edit.click()
      await modal.waitFor()
      await modal.getByRole('button', { name: '保存', exact: true }).waitFor()
      await page.keyboard.press('Shift+Tab')
      assert.ok(await modal.evaluate((node) => node.contains(document.activeElement)))
      await page.screenshot({
        path: `/tmp/nassav-center-${engine.name()}-${mode}.png`,
        fullPage: true,
        animations: 'disabled',
      })
      await modal.getByRole('button', { name: '关闭', exact: true }).click()
    }
    stage = 'center mobile settings and logout'
    await page.goto(`${origin}/personal/general`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('heading', { name: '通用设置', exact: true }).waitFor()
    await page.getByRole('button', { name: '浅色', exact: true }).click()
    await page.getByRole('button', { name: '保存设置', exact: true }).click()
    await page.getByText('设置已保存', { exact: true }).waitFor()
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('body.light-mode').waitFor()
    await page
      .getByRole('navigation', { name: '个人中心功能' })
      .getByRole('button', { name: '退出登录', exact: true })
      .click()
    const logoutDialog = page.getByRole('dialog', { name: '退出登录', exact: true })
    await logoutDialog.getByText('是否要登出', { exact: true }).waitFor()
    await logoutDialog.getByRole('button', { name: '取消', exact: true }).click()
    await logoutDialog.waitFor({ state: 'hidden' })
    await page
      .getByRole('navigation', { name: '个人中心功能' })
      .getByRole('button', { name: '退出登录', exact: true })
      .click()
    await logoutDialog.getByRole('button', { name: '登出', exact: true }).click()
    await page.getByRole('button', { name: '登录', exact: true }).waitFor()
    assert.deepEqual(errors, [])
    console.log(
      'PASS real API: personal center, navigation, aligned detail, icon states, note modal/discard/conflict/route guard, themes, mobile, settings and logout'
    )
  } finally {
    clearTimeout(timer)
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
