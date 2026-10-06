const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
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
          await r.fulfill({ status: 404, body: '' })
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
      await page.getByRole('img', { name: '封面尚未获取' }).waitFor()
      await page.goto(origin + '/resources')
      await page.getByRole('img', { name: '封面尚未获取' }).waitFor()
      await page.goto(origin + '/resource/SAME-1')
      await page.getByRole('img', { name: '封面尚未获取' }).waitFor()
      assert.deepEqual(errors, [])
      await page.close()
    }
    console.log(
      'PASS: same AVID details, descending time order, card/detail cover placeholders in both themes'
    )
  } finally {
    await browser.close()
  }
})().catch((e) => {
  console.error(e)
  process.exitCode = 1
})
