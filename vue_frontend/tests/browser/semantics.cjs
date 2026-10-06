const { chromium } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', (route) => {
      const path = new URL(route.request().url()).pathname
      let data = {},
        pagination
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      if (path.endsWith('/setting')) data = { color_mode: 'dark' }
      if (path.endsWith('/source/list')) data = ['Jable']
      if (path.endsWith('/actors')) {
        data = [{ id: 1, name: 'Actor audit', resource_count: 2 }]
        pagination = { page: 1, pages: 2, total: 2, page_size: 15 }
      }
      if (path.endsWith('/tasks/jobs')) data = { jobs: [], pagination: { total: 0 } }
      return route.fulfill({ json: { code: 200, data, pagination } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    await page.goto(origin + '/add')
    await page.getByRole('heading', { name: '添加资源', exact: true }).waitFor()
    await page.getByText('视频编号 (AVID)', { exact: true }).click()
    assert.equal(
      await page.locator('#add-avids').evaluate((el) => el === document.activeElement),
      true
    )
    assert.equal(await page.getByLabel('下载源', { exact: true }).count(), 1)
    await page.getByRole('link', { name: '跳转到主要内容' }).focus()
    await page.keyboard.press('Enter')
    assert.equal(await page.locator('main').evaluate((el) => el === document.activeElement), true)
    await page.getByRole('link', { name: '设置', exact: true }).click()
    await page.waitForFunction(() => document.activeElement.id === 'main-content')
    await page.getByRole('heading', { name: '系统设置', exact: true }).waitFor()
    await page.goto(origin + '/resources/actors')
    const actor = page.getByRole('link', { name: 'Actor audit', exact: false })
    await actor.waitFor()
    assert.ok((await actor.getAttribute('href')).startsWith('/actors/1?from='))
    await page.getByRole('spinbutton', { name: '跳转页码' }).waitFor()
    await page.getByRole('spinbutton', { name: '每页条数' }).waitFor()
    assert.equal(await page.locator('label label').count(), 0)
    await page.goto(origin + '/recommendations')
    for (const name of ['种子偏好', '演员偏好', '类别偏好', '返回数量']) {
      await page.getByRole('button', { name, exact: true }).waitFor()
    }
    assert.equal(
      await page
        .locator('.meta-card')
        .first()
        .evaluate((el) => getComputedStyle(el).paddingTop),
      '15.2px'
    )
    assert.deepEqual(errors, [])
    console.log(
      'PASS: associated labels, skip link, route focus, directory links and pagination names'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
