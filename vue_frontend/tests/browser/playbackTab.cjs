const { chromium } = require('playwright')
const assert = require('node:assert/strict')

async function main() {
  const browser = await chromium.launch({
    executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome',
  })
  const context = await browser.newContext()
  const errors = [],
    submitted = [],
    closed = [],
    sessions = new Map()
  context.on('page', (page) => page.on('pageerror', (error) => errors.push(error.message)))
  try {
    await context.routeWebSocket('**/nassav/ws/**', () => {})
    await context.route('**/nassav/api/**', async (route) => {
      const request = route.request(),
        path = new URL(request.url()).pathname
      let data = {},
        code = 200
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      else if (path.endsWith('/setting')) data = { color_mode: 'dark', enable_avatar: 'false' }
      else if (path.endsWith('/resource/metadata'))
        data = {
          avid: 'DEMO-1',
          source_title: '独立播放测试资源',
          source: 'jable',
          file_exists: false,
        }
      else if (path.endsWith('/resource/cover')) return route.fulfill({ status: 404 })
      else if (path.endsWith('/playback-sessions') && request.method() === 'POST') {
        submitted.push(path)
        data = { session_id: `tab-${submitted.length}`, version: 1, generation: 1, state: 'queued' }
        sessions.set(data.session_id, data)
        code = 202
      } else if (path.endsWith('/close')) {
        const id = path.split('/').at(-2)
        closed.push(id)
        data = { ...sessions.get(id), version: 2, state: 'closed' }
        sessions.set(id, data)
      } else if (/\/playback-sessions\/[^/]+$/.test(path))
        data = sessions.get(path.split('/').at(-1))
      else if (path.endsWith('/tasks/jobs')) data = []
      await route.fulfill({ status: code, json: { code, data } })
    })
    const detail = await context.newPage()
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    await detail.goto(`${origin}/resource/DEMO-1`)
    const actions = detail.getByLabel('资源操作', { exact: true })
    await actions.waitFor()
    assert.deepEqual(
      (await actions.getByRole('button').allTextContents()).map((text) => text.trim()),
      ['刷新信息', '下载视频', '在线播放', '删除数据']
    )
    for (const width of [1440, 1024, 390]) {
      await detail.setViewportSize({ width, height: 900 })
      const boxes = await actions.getByRole('button').evaluateAll((buttons) =>
        buttons.map((button) => {
          const box = button.getBoundingClientRect()
          return { width: box.width, height: box.height, top: box.top }
        })
      )
      assert.ok(
        boxes.every(
          (box) =>
            Math.abs(box.width - boxes[0].width) < 1 &&
            Math.abs(box.height - boxes[0].height) < 1 &&
            box.height >= 48
        ),
        JSON.stringify({ width, boxes })
      )
      assert.equal(new Set(boxes.map((box) => box.top)).size, width === 390 ? 2 : 1)
      assert.equal(
        await detail.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        true
      )
    }
    assert.equal(submitted.length, 0, 'detail page must not create a playback session')
    const opened = context.waitForEvent('page')
    await actions.getByRole('button', { name: '在线播放', exact: true }).click()
    const player = await opened
    await player.waitForURL(`${origin}/play/DEMO-1`)
    await player.getByRole('heading', { name: '独立播放测试资源', exact: true }).waitFor()
    assert.equal(await player.locator('nav').count(), 0)
    assert.equal(await player.getByRole('button', { name: '菜单', exact: true }).count(), 0)
    assert.equal(await player.getByRole('button', { name: '停止播放', exact: true }).count(), 0)
    assert.equal(await player.getByRole('link', { name: '查看资源详情', exact: true }).count(), 0)
    await player.getByRole('link', { name: 'NASSAV', exact: true }).waitFor()
    await player.waitForFunction(() => document.body.textContent.includes('正在准备播放'))
    assert.equal(await player.evaluate(() => window.opener), null)
    assert.equal(submitted.length, 1)
    assert.equal(new URL(detail.url()).pathname, '/resource/DEMO-1')
    await detail.close()
    assert.equal(closed.length, 0, 'closing detail must not stop the playback tab')
    const viewport = player.getByRole('region', { name: '视频播放器', exact: true })
    for (const mode of ['light-mode', 'dark-mode']) {
      await player.evaluate((theme) => {
        document.body.classList.remove('light-mode', 'dark-mode')
        document.body.classList.add(theme)
      }, mode)
      for (const width of [1440, 1024, 390]) {
        await player.setViewportSize({ width, height: 900 })
        await player.waitForTimeout(350)
        const box = await viewport.boundingBox()
        assert.ok(Math.abs(box.width / box.height - 16 / 9) < 0.01)
        assert.ok(Math.abs(box.x + box.width / 2 - width / 2) < 1)
        if (width === 1440)
          assert.ok(Math.abs(box.width - 1024) < 1, 'preserve desktop maximum width')
        assert.equal(
          await player.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
          true
        )
        assert.equal(
          await player.getByText('在线播放不保存视频文件。', { exact: false }).count(),
          0
        )
      }
    }
    // Exercise pagehide before reload: Playwright can discard intercepted keepalive
    // requests when their old document is destroyed; this is not a backend receipt check.
    await player.evaluate(() => window.dispatchEvent(new Event('pagehide')))
    await player.waitForTimeout(200)
    assert.deepEqual(closed, ['tab-1'])
    await player.reload()
    await player.getByRole('heading', { name: '独立播放测试资源', exact: true }).waitFor()
    await player.waitForFunction(() => document.body.textContent.includes('正在准备播放'))
    assert.equal(submitted.length, 2)
    assert.deepEqual(closed, ['tab-1'])
    await player.getByRole('link', { name: 'NASSAV', exact: true }).click()
    await player.waitForURL(origin + '/')
    await player.waitForTimeout(500)
    assert.deepEqual(closed, ['tab-1', 'tab-2'])
    assert.equal(
      await player.locator('nav').count(),
      1,
      'normal navigation returns after leaving playback'
    )
    assert.deepEqual(errors, [])
    console.log(
      'PASS: equal-sized ordered actions, mobile layout, isolated new playback tab, logo-only playback layout, fixed 16:9 viewport, pagehide call, reload/unmount cleanup and restored navigation'
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
