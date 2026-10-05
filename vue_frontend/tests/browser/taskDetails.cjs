const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
      const errors = [],
        writes = []
      let socket,
        queueReads = 0
      const jobs = [
        {
          task_id: 'scrape-fail',
          avid: 'AV-3',
          action: 'refresh',
          state: 'failed',
          message: '来源超时',
          status_token: 'fake',
          updated_at: 1,
        },
        {
          task_id: 'scrape-ok',
          avid: 'AV-4',
          action: 'add',
          state: 'succeeded',
          stage: 'translation_queued',
          status_token: 'fake',
          updated_at: 2,
        },
      ]
      await page.addInitScript(
        (j) => localStorage.setItem('nassav:scrape-jobs:v1', JSON.stringify(j)),
        jobs
      )
      page.on('pageerror', (e) => errors.push(e.message))
      await page.routeWebSocket('**/nassav/ws/**', (s) => {
        socket = s
      })
      await page.route('**/nassav/api/**', (r) => {
        const req = r.request(),
          url = new URL(req.url()),
          path = url.pathname
        if (req.method() !== 'GET') writes.push(path)
        let data = []
        if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
        if (path.endsWith('/setting')) data = { color_mode: theme }
        if (path.endsWith('/tasks/queue/status')) {
          queueReads++
          data = {
            active_tasks: [
              {
                task_id: 'download-one',
                avid: 'AV-1',
                state: 'STARTED',
                title: '正在下载的资源',
                progress: { percent: 45, speed: '2 MB/s', downloaded: '450 MB', total: '1 GB' },
              },
            ],
            pending_tasks: [{ task_id: 'download-two', avid: 'AV-2', title: '等待下载的资源' }],
            active_count: 1,
            pending_count: 1,
          }
        }
        if (path.endsWith('/resource/metadata'))
          data = {
            avid: url.searchParams.get('avid'),
            source_title:
              url.searchParams.get('avid') === 'AV-1' ? '正在下载的资源' : '等待下载的资源',
          }
        if (path.endsWith('/resource/cover')) {
          if (url.searchParams.get('avid') === 'AV-2') return r.fulfill({ status: 404, body: '' })
          return r.fulfill({
            contentType: 'image/svg+xml',
            body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="currentColor"/></svg>',
          })
        }
        return r.fulfill({ json: { code: 200, data } })
      })
      const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
      await page.goto(origin + '/downloads')
      const detail = page.getByRole('complementary', { name: '任务明细' })
      await detail.getByRole('heading', { name: '正在下载的资源' }).waitFor()
      assert.equal(await page.locator('tbody tr').count(), 4)
      assert.equal(await detail.getByRole('progressbar').getAttribute('value'), '45')
      assert.equal(
        await detail.locator('img').evaluate((img) => img.complete && img.naturalWidth > 0),
        true
      )
      assert.ok(queueReads > 0)
      socket.send(
        JSON.stringify({
          type: 'progress_update',
          data: { task_id: 'download-one', percent: 66, speed: '3 MB/s' },
        })
      )
      await page.waitForFunction(() => document.querySelector('aside progress')?.value === 66)
      await page.getByRole('button', { name: '等待下载的资源，查看任务明细' }).click()
      await detail.getByRole('heading', { name: '等待下载的资源' }).waitFor()
      await page.getByRole('button', { name: '刮削任务', exact: true }).click()
      await page.getByRole('button', { name: 'AV-3，查看任务明细' }).click()
      assert.equal(await detail.getByRole('alert').textContent(), '来源超时')
      assert.equal(await detail.getByRole('progressbar').count(), 0)
      assert.equal(
        (
          await page
            .getByRole('button', { name: 'AV-3，查看任务明细' })
            .locator('xpath=ancestor::tr')
            .locator('td')
            .last()
            .textContent()
        ).trim(),
        '失败'
      )
      assert.equal(
        await detail.getByRole('link', { name: '查看资源' }).getAttribute('href'),
        '/resource/AV-3'
      )
      assert.equal(await page.getByRole('button', { name: '演示重试' }).count(), 0)
      await page.getByRole('button', { name: '全部任务', exact: true }).click()
      socket.send(
        JSON.stringify({
          type: 'queue_status',
          data: {
            active_tasks: [],
            pending_tasks: [],
            active_count: 0,
            pending_count: 0,
            total_count: 0,
          },
        })
      )
      await page.waitForFunction(() => document.querySelectorAll('tbody tr').length === 2)
      await page.getByRole('checkbox', { name: '选择当前列表全部任务' }).check()
      await page.getByRole('button', { name: '不再跟踪所选 (2)' }).click()
      await page
        .getByRole('dialog', { name: '不再跟踪任务' })
        .getByRole('button', { name: '不再跟踪', exact: true })
        .click()
      await page.getByText('暂无此类任务', { exact: true }).waitFor()
      assert.equal(
        await page.evaluate(() => JSON.parse(localStorage.getItem('nassav:scrape-jobs:v1')).length),
        0
      )
      await page.setViewportSize({ width: 390, height: 844 })
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        true
      )
      await page.screenshot({
        path: '/tmp/nassav-task-production-' + theme + '.png',
        fullPage: true,
      })
      assert.deepEqual(writes, [])
      assert.deepEqual(errors, [])
      await page.close()
    }
    console.log(
      'PASS: production download/scrape details, covers, WebSocket progress/removal, filters and mobile; no synthetic actions'
    )
  } finally {
    await browser.close()
  }
})().catch((e) => {
  console.error(e)
  process.exitCode = 1
})
