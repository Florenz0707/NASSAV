const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
      let coverArtwork = null
      const errors = [],
        orders = []
      page.on('pageerror', (e) => errors.push(e.message))
      const jobs = [0, 1, 2].map((i) => ({
        job_id: `00000000-0000-4000-8000-00000000000${i + 1}`,
        task_id: null,
        job_type: i === 2 ? 'scrape' : 'download',
        avid: 'SAME-1',
        state: 'succeeded',
        stage: 'succeeded',
        version: 1,
        allowed_actions: [],
        created_at: 1700000000 + i,
        updated_at: 1700000010 - i,
        resource_saved: true,
        resource_avid: 'SAME-1',
        resource: { source_title: `任务 ${i}` },
        timeline: [{ stage: 'succeeded', at: 1700000020 + i }],
      }))
      await page.routeWebSocket('**/nassav/ws/**', () => {})
      await page.route('**/nassav/api/**', async (r) => {
        const url = new URL(r.request().url()),
          path = url.pathname
        let data = [],
          pagination,
          code = 200
        if (path.endsWith('/auth/session'))
          data = { authenticated: true, username: 'resource-task-audit' }
        if (path.endsWith('/setting')) data = { color_mode: theme }
        if (path.includes('/cover')) {
          await r.fulfill(
            coverArtwork
              ? { contentType: 'image/svg+xml', body: coverArtwork }
              : { status: 404, body: '' }
          )
          return
        }
        if (path.endsWith('/tasks/queue/status')) data = { active_tasks: [], pending_tasks: [] }
        if (path.endsWith('/tasks/jobs')) {
          orders.push(url.searchParams.get('ordering'))
          data = { jobs, pagination: { total: 3, page_size: 50, has_more: false } }
        }
        if (path.match(/\/tasks\/jobs\/[\da-f-]+$/))
          data = jobs.find((j) => path.endsWith(j.job_id))
        if (path.endsWith('/resource/metadata'))
          data = { avid: 'SAME-1', source_title: '资源名称', genres: [], actors: [] }
        if (path.endsWith('/resources')) {
          data = [{ avid: 'SAME-1', source_title: '资源名称' }]
          pagination = { page: 1, page_size: 15, total: 1, pages: 1 }
        }
        await r.fulfill({
          json: { code, message: 'success', data, ...(pagination ? { pagination } : {}) },
        })
      })
      const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
      await page.goto(origin + '/downloads')
      await page
        .getByRole('button', { name: /查看任务明细/ })
        .first()
        .waitFor()
      const rows = page.locator('tbody tr')
      for (let i = 0; i < 3; i++) {
        await rows
          .nth(i)
          .getByRole('button', { name: /查看任务明细/ })
          .click()
        const label = await rows
          .nth(i)
          .getByRole('button', { name: /查看任务明细/ })
          .getAttribute('aria-label')
        await page.getByRole('heading', { name: label.split('，')[0], exact: true }).waitFor()
      }
      await page.getByRole('button', { name: '任务排序' }).click()
      await page.getByRole('option', { name: '最近更新', exact: true }).click()
      await page.waitForFunction(() =>
        document
          .querySelector('tbody tr button[aria-pressed]')
          ?.getAttribute('aria-label')
          ?.startsWith('任务 0')
      )
      assert(orders.includes('-updated_at'))
      const tracked = page.getByText(/当前跟踪.*个已加载持久任务/)
      assert.match(await tracked.innerText(), /当前跟踪 3/)
      await rows.first().getByRole('button', { name: '不再跟踪任务 SAME-1', exact: true }).click()
      await page.getByRole('dialog').getByRole('button', { name: '不再跟踪', exact: true }).click()
      await page.waitForFunction(() => document.body.textContent.includes('当前跟踪 2'))
      assert.match(await tracked.innerText(), /已隐藏\s+1/)
      await page.reload()
      await page.getByText(/当前跟踪 2/).waitFor()
      await page.goto(origin + '/resources')
      await page.getByRole('img', { name: '封面尚未获取' }).waitFor()
      async function equalActions(names) {
        const sizes = await Promise.all(
          names.map(async (name) => {
            const box = await page.getByRole('button', { name, exact: true }).boundingBox()
            return [Math.round(box.width), Math.round(box.height)]
          })
        )
        assert.deepEqual(sizes[0], sizes[1])
        assert.deepEqual(sizes[0], sizes[2])
      }
      const cover = page.locator('[data-avid="SAME-1"]')
      const relativeTop = () =>
        cover.evaluate(
          (el) => el.getBoundingClientRect().top - el.parentElement.getBoundingClientRect().top
        )
      const beforeBatch = await relativeTop()
      await page.getByRole('button', { name: '批量操作', exact: true }).click()
      await page.getByRole('checkbox', { name: '选择资源 SAME-1', exact: true }).waitFor()
      assert(
        Math.abs((await relativeTop()) - beforeBatch) < 1,
        'batch checkbox must not displace cover'
      )
      await page.getByRole('checkbox', { name: '选择资源 SAME-1', exact: true }).check()
      assert(Math.abs((await relativeTop()) - beforeBatch) < 1)
      await page.getByRole('button', { name: '退出批量', exact: true }).click()
      const cardButtons = await Promise.all(
        ['刷新资源', '下载', '删除'].map((name) =>
          page.getByRole('button', { name, exact: true }).boundingBox()
        )
      )
      assert(cardButtons.every((box) => box.width < 90 && Math.round(box.height) === 40))
      assert.equal(
        await page.getByRole('button', { name: '刷新资源', exact: true }).innerText(),
        '刷新'
      )
      await page.goto(origin + '/resource/SAME-1')
      await page.getByRole('img', { name: '封面尚未获取' }).waitFor()
      await equalActions(['刷新信息', '下载视频', '删除数据'])
      for (const [width, height] of [
        [960, 540],
        [360, 540],
      ]) {
        coverArtwork = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="steelblue" /></svg>`
        await page.reload()
        const image = page.getByRole('img', { name: '资源名称 · 资源封面', exact: true })
        await image.waitFor()
        await image.evaluate((el) => el.decode())
        const geometry = await image.evaluate((el) => {
          const img = el.getBoundingClientRect(),
            frame = el.parentElement.getBoundingClientRect()
          return {
            width: img.width,
            height: img.height,
            frameWidth: frame.width,
            frameHeight: frame.height,
            radius: parseFloat(getComputedStyle(el).borderTopLeftRadius),
            background: getComputedStyle(el.parentElement).backgroundColor,
          }
        })
        assert(Math.abs(geometry.width / geometry.height - width / height) < 0.01)
        assert(geometry.width <= geometry.frameWidth && geometry.height <= geometry.frameHeight)
        assert(geometry.radius > 0)
        assert.equal(geometry.background, 'rgba(0, 0, 0, 0)')
        await equalActions(['刷新信息', '下载视频', '删除数据'])
      }
      await page.setViewportSize({ width: 390, height: 844 })
      await equalActions(['刷新信息', '下载视频', '删除数据'])
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
      assert.deepEqual(errors, [])
      await page.close()
    }
    console.log(
      'PASS: hidden counts persist across reload, batch covers stay aligned, same AVID details, card/detail sizes and covers in both themes'
    )
  } finally {
    await browser.close()
  }
})().catch((e) => {
  console.error(e)
  process.exitCode = 1
})
