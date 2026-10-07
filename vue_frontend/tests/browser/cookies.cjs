const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage(),
      writes = [],
      errors = []
    let reads = 0,
      cookie = ''
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/nassav/api/**', (route) => {
      const request = route.request(),
        path = new URL(request.url()).pathname
      let data = []
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      if (path.endsWith('/setting')) data = { color_mode: 'light' }
      if (path.endsWith('/source/list')) data = ['Jable']
      if (path.endsWith('/source/cookie')) {
        if (request.method() === 'GET') reads++
        if (request.method() === 'POST') {
          const body = request.postDataJSON()
          writes.push(body)
          cookie = body.cookie || 'auto-demo'
        }
        if (request.method() === 'DELETE') {
          writes.push('delete')
          cookie = ''
        }
        data = cookie ? [{ source: 'Jable', cookie, mtime: '2026-10-05T00:00:00Z' }] : []
      }
      return route.fulfill({ json: { code: 200, data } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    await page.goto(origin + '/settings')
    await page.getByRole('heading', { name: '通用设置' }).waitFor()
    assert.equal(reads, 0)
    assert.equal(await page.getByText('Cookie 管理', { exact: true }).count(), 0)
    await page.goto(origin + '/add')
    const entry = page.getByRole('button', { name: 'Cookie 设置', exact: true })
    const submitBox = await page
      .getByRole('button', { name: '添加资源', exact: true })
      .boundingBox()
    const sourceBorders = await page
      .getByRole('button', { name: '下载源', exact: true })
      .evaluate((button) => ({
        outer: Number.parseFloat(getComputedStyle(button.parentElement).borderTopWidth),
        inner: Number.parseFloat(getComputedStyle(button).borderTopWidth),
      }))
    assert.equal(sourceBorders.outer, 0, 'download source must not have a nested wrapper border')
    assert.ok(sourceBorders.inner > 0)
    const entryBox = await entry.boundingBox()
    assert.ok(entryBox.x >= submitBox.x + submitBox.width)
    assert.ok(Math.abs(entryBox.y + entryBox.height / 2 - submitBox.y - submitBox.height / 2) < 2)
    assert.equal((await entry.textContent()).trim(), '')
    assert.equal(await entry.locator('svg').count(), 1)
    assert.ok(
      await entry.evaluate((button) => {
        const style = getComputedStyle(button)
        return parseFloat(style.borderRadius) > 0 && style.backgroundColor !== 'rgba(0, 0, 0, 0)'
      })
    )
    await page.setViewportSize({ width: 390, height: 844 })
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    await entry.click()
    await page.getByRole('button', { name: '更新', exact: true }).click()
    const editor = page.getByRole('dialog', { name: '设置 Cookie - Jable' })
    await editor.locator('textarea').fill('demo-cookie')
    await editor.getByLabel('User-Agent（可选）').fill('demo-UA')
    await editor.getByRole('button', { name: '保存', exact: true }).click()
    await page.getByRole('button', { name: '更新', exact: true }).waitFor()
    assert.deepEqual(writes[0], { source: 'Jable', cookie: 'demo-cookie', user_agent: 'demo-UA' })
    await page.getByRole('button', { name: '查看', exact: true }).click()
    await page
      .getByRole('dialog', { name: '查看 Cookie - Jable' })
      .getByRole('button', { name: '关闭', exact: true })
      .click()
    await page.getByRole('button', { name: '更新', exact: true }).click()
    await editor.getByRole('button', { name: '自动获取', exact: true }).click()
    await editor.waitFor({ state: 'hidden' })
    assert.equal(writes[1].auto, true)
    await page.getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('button', { name: '确定清除', exact: true }).click()
    await page.getByRole('button', { name: '更新', exact: true }).waitFor()
    assert.equal(writes[2], 'delete')
    await page.keyboard.press('Escape')
    await page
      .getByRole('dialog', { name: 'Cookie 设置', exact: true })
      .waitFor({ state: 'hidden' })
    assert.deepEqual(errors, [])
    console.log(
      'PASS: cookies only load on add-page dialog; save, view, auto-fetch, delete and nested focus lifecycle'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
