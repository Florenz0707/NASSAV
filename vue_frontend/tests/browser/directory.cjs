const { chromium } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const browser = await chromium.launch({
    executablePath: process.env.NASSAV_CHROMIUM_PATH,
    headless: true,
  })
  try {
    const page = await browser.newPage()
    const errors = [],
      requests = []
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/nassav/api/**', async (route) => {
      const url = new URL(route.request().url())
      let data = {},
        pagination
      if (url.pathname.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      else if (url.pathname.endsWith('/setting'))
        data = { color_mode: 'light', enable_avatar: 'false' }
      else if (/\/(actors|genres)$/.test(url.pathname)) {
        requests.push(url)
        const search = url.searchParams.get('search') || ''
        if (search === 'failure')
          return route.fulfill({ status: 500, json: { code: 500, message: '模拟加载失败' } })
        if (search === 'old') await new Promise((resolve) => setTimeout(resolve, 900))
        const current = Number(url.searchParams.get('page'))
        data = [{ id: 1, name: search || `Page ${current}`, resource_count: 2 }]
        pagination = {
          page: current,
          pages: 3,
          total: 3,
          page_size: Number(url.searchParams.get('page_size')),
        }
      }
      await route.fulfill({ json: { code: 200, data, pagination } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    for (const [entity, size, label] of [
      ['actors', 15, '演员'],
      ['genres', 15, '类别'],
    ]) {
      await page.goto(`${origin}/resources/${entity}?page=2`)
      await page.getByRole('link', { name: 'Page 2', exact: false }).waitFor()
      assert.equal(Number(requests.at(-1).searchParams.get('page_size')), size)
      assert.equal(
        await page
          .getByRole('button', { name: '下一页', exact: true })
          .evaluate((el) => getComputedStyle(el).paddingLeft),
        '16px'
      )
      await page.getByRole('button', { name: '下一页', exact: true }).click()
      await page.getByRole('link', { name: 'Page 3', exact: false }).waitFor()
      assert.equal(new URL(page.url()).searchParams.get('page'), '3')
      const search = page.getByRole('searchbox', { name: `搜索 ${label} 名称...` })
      await search.fill('old')
      await page.waitForTimeout(350)
      await search.fill('new')
      await page.getByRole('link', { name: 'new', exact: false }).waitFor()
      await page.waitForTimeout(1000)
      assert.equal(
        await page.locator(entity === 'actors' ? '.actor-name' : '.genre-name').innerText(),
        'new'
      )
      assert.equal(new URL(page.url()).searchParams.get('page'), '1')
      await search.fill('failure')
      await page.getByRole('alert').waitFor()
      assert.match(await page.getByRole('alert').innerText(), /模拟加载失败/)
      await page.setViewportSize({ width: 390, height: 844 })
      assert.equal(
        await page.getByRole('button', { name: '跳转开头', exact: true }).isVisible(),
        false
      )
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
        true
      )
      await page.screenshot({ path: `/tmp/nassav-f4-${entity}-mobile.png`, fullPage: true })
      await page.setViewportSize({ width: 1280, height: 900 })
    }
    assert.deepEqual(errors, [])
    console.log(
      'PASS: directory defaults, restored page, pagination URL, stale queries, error state and mobile layout'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
