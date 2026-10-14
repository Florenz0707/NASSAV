const { chromium } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const browser = await chromium.launch({
    executablePath: process.env.NASSAV_CHROMIUM_PATH,
    headless: true,
  })
  try {
    const page = await browser.newPage(),
      errors = [],
      mutations = [],
      preferenceWrites = []
    let settings = { color_mode: 'light' }
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/nassav/api/**', async (route) => {
      const request = route.request(),
        url = new URL(request.url())
      let data = {},
        pagination
      if (url.pathname.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      else if (url.pathname.endsWith('/setting')) {
        if (request.method() === 'PUT') {
          preferenceWrites.push(request.postDataJSON())
          settings = { ...settings, ...request.postDataJSON() }
        }
        data = settings
      } else if (/\/(actors|genres)$/.test(url.pathname)) {
        const name =
          url.searchParams.get('search') || (url.pathname.endsWith('/actors') ? 'Actor' : 'Genre')
        if (name === 'old') await new Promise((resolve) => setTimeout(resolve, 900))
        data =
          name === 'many'
            ? Array.from({ length: 40 }, (_, index) => ({
                id: index + 1,
                name: `many-${index + 1}`,
                is_blocked: true,
                resource_count: 2,
              }))
            : [{ id: 1, name, is_blocked: false, resource_count: 2 }]
        pagination = { total: 1, pages: 1, page: 1 }
      } else if (url.pathname.endsWith('/recommendations/seed-block')) {
        mutations.push(request.postDataJSON())
        await new Promise((resolve) => setTimeout(resolve, 600))
      } else if (url.pathname.endsWith('/recommendations/avid-blocklist')) {
        if (request.method() === 'POST') mutations.push(request.postDataJSON())
        data =
          request.method() === 'GET'
            ? mutations.filter((x) => x.avid).map((x) => ({ avid: x.avid, is_blocked: true }))
            : {}
        pagination = { total: Array.isArray(data) ? data.length : 0 }
      }
      await route.fulfill({ json: { code: 200, data, pagination } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    await page.goto(`${origin}/recommendations`)
    await page.getByRole('button', { name: '个性化', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '个性化', exact: true })
    await dialog.getByRole('button', { name: '种子偏好', exact: true }).click()
    await dialog.getByRole('option', { name: '类别', exact: true }).click()
    await dialog.getByRole('button', { name: '保存推荐偏好', exact: true }).click()
    await page.getByText('推荐偏好已保存', { exact: true }).waitFor()
    assert.deepEqual(preferenceWrites, [{ recommendation_type_preference: 'genre_heavy' }])
    await dialog.getByText('仅看已屏蔽', { exact: true }).click()
    await dialog.locator('.blacklist-row').filter({ hasText: 'Actor' }).waitFor()
    await dialog.getByRole('button', { name: '屏蔽', exact: true }).click()
    await dialog.getByRole('button', { name: '类别', exact: true }).click()
    await dialog.locator('.blacklist-row').filter({ hasText: 'Genre' }).waitFor()
    await page.waitForTimeout(700)
    assert.equal(mutations[0].seed_type, 'actor')
    assert.match(await dialog.locator('.blacklist-row').innerText(), /未屏蔽/)
    const search = dialog.getByRole('searchbox', { name: '搜索类别名' })
    await search.fill('old')
    await page.waitForTimeout(350)
    await search.fill('new')
    await dialog.locator('.blacklist-row').filter({ hasText: 'new' }).waitFor()
    await page.waitForTimeout(1000)
    assert.match(await dialog.locator('.blacklist-row').innerText(), /new/)
    assert.doesNotMatch(await dialog.locator('.blacklist-row').innerText(), /old/)
    await dialog.getByRole('button', { name: '资源', exact: true }).click()
    await dialog.getByRole('searchbox').fill('av-001')
    await dialog
      .locator('.blacklist-add-strip')
      .getByRole('button', { name: '屏蔽', exact: true })
      .click()
    await dialog.locator('.blacklist-row').filter({ hasText: 'AV-001' }).waitFor()
    assert.equal(mutations.at(-1).avid, 'AV-001')
    await dialog.getByRole('button', { name: '演员', exact: true }).click()
    await dialog.getByRole('searchbox').fill('many')
    await dialog.locator('.blacklist-row').filter({ hasText: 'many-40' }).waitFor()
    for (const height of [900, 600]) {
      await page.setViewportSize({ width: 1280, height })
      const panel = await dialog.boundingBox()
      const list = dialog.locator('.blacklist-list')
      const box = await list.boundingBox()
      assert.ok(Math.abs(panel.y + panel.height - (box.y + box.height) - 24) < 3)
      if (height === 900) assert.ok(box.height > 300)
      await list.evaluate((el) => {
        el.scrollTop = el.scrollHeight
      })
      const last = await list.locator('.blacklist-row').last().boundingBox()
      assert.ok(last.y >= box.y && last.y + last.height <= box.y + box.height + 1)
      assert.ok(panel.y >= 0 && panel.y + panel.height <= height)
    }
    await page.setViewportSize({ width: 390, height: 844 })
    const content = dialog.locator(':scope > div').nth(1)
    await content.evaluate((el) => {
      el.scrollTop = el.scrollHeight
    })
    const mobileBody = await content.boundingBox()
    const mobileLast = await dialog.locator('.blacklist-row').last().boundingBox()
    assert.ok(
      mobileLast.y >= mobileBody.y &&
        mobileLast.y + mobileLast.height <= mobileBody.y + mobileBody.height
    )
    assert.equal(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth), true)
    await page.screenshot({ path: '/tmp/nassav-f6-blacklist.png', fullPage: true })
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    assert.equal(await page.evaluate(() => document.body.style.overflow), '')
    assert.deepEqual(errors, [])
    console.log(
      'PASS: blacklist stale reads, mutation across type switch, normalized AVID, modal close and no page errors'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
