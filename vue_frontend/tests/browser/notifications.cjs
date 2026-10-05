const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    for (const theme of ['dark', 'light']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }),
        errors = [],
        writes = []
      let socket, resolveSocket
      const socketReady = new Promise((resolve) => {
        resolveSocket = resolve
      })
      page.on('pageerror', (e) => errors.push(e.message))
      await page.routeWebSocket('**/nassav/ws/**', (s) => {
        socket = s
        resolveSocket()
      })
      await page.route('**/nassav/api/**', (r) => {
        const request = r.request(),
          path = new URL(request.url()).pathname
        if (request.method() !== 'GET') writes.push(path)
        let data = []
        if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
        if (path.endsWith('/setting')) data = { color_mode: theme }
        if (path.endsWith('/resource/metadata'))
          data = { avid: 'NOTICE-1', source_title: '通知测试资源' }
        if (path.endsWith('/tasks/queue/status')) data = { active_tasks: [], pending_tasks: [] }
        return r.fulfill({
          json: { code: 200, data, pagination: { total: 0, page: 1, page_size: 15, pages: 0 } },
        })
      })
      const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
      await page.goto(origin + '/')
      await page.getByRole('link', { name: '首页', exact: true }).first().waitFor()
      await socketReady
      const metadata = page.waitForResponse((r) => r.url().includes('/resource/metadata'))
      socket.send(
        JSON.stringify({
          type: 'queue_status',
          data: {
            active_tasks: [{ task_id: 'notice-task', avid: 'NOTICE-1', state: 'STARTED' }],
            pending_tasks: [],
          },
        })
      )
      await metadata
      await page.waitForTimeout(30)
      const event = {
        type: 'task_failed',
        data: { task_id: 'notice-task', avid: 'NOTICE-1', error: '示例下载失败' },
      }
      socket.send(JSON.stringify(event))
      socket.send(JSON.stringify(event))
      const bell = page.getByRole('button', { name: '打开通知', exact: true })
      await bell.click()
      const dialog = page.getByRole('dialog', { name: '通知', exact: true })
      await dialog.getByRole('button', { name: '查看通知：下载失败 · 通知测试资源' }).waitFor()
      assert.equal(await dialog.locator('ol > li').count(), 1)
      await dialog.getByRole('button', { name: '关闭通知' }).click()
      await page.getByRole('link', { name: '设置', exact: true }).first().click()
      await page.getByRole('heading', { name: '通用设置' }).waitFor()
      await bell.click()
      await dialog.waitFor()
      assert.ok(
        await dialog
          .getByRole('button', { name: '关闭通知' })
          .evaluate(
            (button) =>
              parseFloat(getComputedStyle(button).borderRadius) > 0 &&
              parseFloat(getComputedStyle(button).paddingTop) > 0
          )
      )
      assert.equal(await dialog.locator('ol > li').count(), 1)
      await dialog.getByRole('button', { name: '全部标为已读' }).click()
      assert.equal(await dialog.getByText('0 条未读', { exact: true }).count(), 1)
      await dialog.getByRole('button', { name: '需要处理', exact: true }).click()
      assert.equal(await dialog.locator('ol > li').count(), 1)
      await dialog.getByRole('button', { name: '查看通知：下载失败 · 通知测试资源' }).click()
      await page.waitForTimeout(700)
      await page.screenshot({
        path: '/tmp/nassav-global-notifications-' + theme + '.png',
        fullPage: true,
      })
      socket.send(
        JSON.stringify({ type: 'queue_status', data: { active_tasks: [], pending_tasks: [] } })
      )
      await dialog.getByRole('link', { name: '查看任务' }).click()
      await page
        .getByText('该任务未被本浏览器跟踪，或已移出当前队列；通知记录保留当时结果。', {
          exact: true,
        })
        .waitFor()
      assert.equal(await page.evaluate(() => document.body.style.overflow), '')
      await page.setViewportSize({ width: 390, height: 844 })
      await bell.click()
      await dialog.waitFor()
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        true
      )
      await page.keyboard.press('Escape')
      assert.equal(await bell.evaluate((el) => el === document.activeElement), true)
      await page.goto(origin + '/resources?demo=notifications')
      const preview = page.getByRole('dialog', { name: '通知预览', exact: true })
      await preview.waitFor()
      assert.equal(await preview.locator('ol > li').count(), 4)
      await preview.getByRole('button', { name: '全部标为已读' }).click()
      assert.equal(await preview.getByText('0 条未读', { exact: true }).count(), 1)
      await page.keyboard.press('Escape')
      await page.getByRole('button', { name: '打开通知', exact: true }).click()
      await preview.waitFor()
      await page.screenshot({
        path: '/tmp/nassav-global-notification-preview-mobile-' + theme + '.png',
        fullPage: true,
      })
      assert.deepEqual(writes, [])
      assert.deepEqual(errors, [])
      await page.close()
    }
    console.log(
      'PASS: global navbar sidebar on home/settings/tasks/resources, deduplication, read/filter/deep links, focus/mobile/themes and isolated preview'
    )
  } finally {
    await browser.close()
  }
})().catch((e) => {
  console.error(e)
  process.exitCode = 1
})
