const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
      page.setDefaultTimeout(15000)
      const errors = [],
        commands = []
      page.on('pageerror', (e) => errors.push(e.message))
      const ids = ['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002']
      const jobs = ids.map((id, i) => ({
        job_id: id,
        task_id: `attempt-${i}`,
        job_type: i ? 'scrape' : 'download',
        avid: `CTRL-${i + 1}`,
        state: 'running',
        stage: i ? 'translation_translating' : 'video_download',
        version: 1,
        allowed_actions: ['pause', 'cancel'],
        cleanup_state: 'not_required',
        resource_saved: true,
        resource_avid: `CTRL-${i + 1}`,
        resource: { source_title: `资源名称 ${i + 1}` },
        timeline: [
          { stage: 'queued', at: 1700000000 },
          { stage: 'running', at: 1700000010 },
        ],
        progress: i ? null : { percent: 40 },
        translation: i ? { state: 'translating' } : {},
      }))
      let socket
      await page.routeWebSocket('**/nassav/ws/**', (s) => {
        socket = s
      })
      await page.route('**/nassav/api/**', async (r) => {
        const req = r.request(),
          path = new URL(req.url()).pathname
        let data = [],
          code = 200
        if (path.endsWith('/auth/session'))
          data = { authenticated: true, username: 'controls-audit' }
        if (path.endsWith('/setting')) data = { color_mode: theme }
        if (path.endsWith('/tasks/queue/status')) data = { active_tasks: [], pending_tasks: [] }
        if (path.endsWith('/tasks/jobs'))
          data = { jobs, pagination: { total: jobs.length, has_more: false } }
        if (path.match(/\/tasks\/jobs\/[\da-f-]+$/))
          data = jobs.find((j) => path.endsWith(j.job_id))
        if (path.endsWith('/tasks/jobs/actions')) {
          const payload = req.postDataJSON()
          commands.push(payload)
          code = 202
          data = {
            results: payload.items.map((item) => {
              const j = jobs.find((job) => job.job_id === item.job_id)
              // Demonstrate a partial batch conflict without discarding successful items.
              if (payload.action === 'pause' && j.job_type === 'scrape')
                return { job_id: j.job_id, code: 409, message: '任务已更新，请重试', job: j }
              j.version++
              j.state =
                payload.action === 'pause'
                  ? 'pausing'
                  : payload.action === 'resume'
                    ? 'queued'
                    : payload.action === 'cancel'
                      ? 'cancelling'
                      : j.state
              if (payload.action === 'cleanup_retry') {
                j.cleanup_state = 'completed'
                j.cleanup_message = ''
                j.allowed_actions = []
              } else
                j.allowed_actions =
                  j.state === 'queued'
                    ? ['pause', 'cancel']
                    : j.state === 'pausing'
                      ? ['cancel']
                      : []
              return { job_id: j.job_id, code: 202, job: j }
            }),
          }
        }
        await r.fulfill({ json: { code, data } })
      })
      const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
      await page.goto(origin + '/downloads')
      const row = (avid) =>
        page
          .getByRole('button', { name: `资源名称 ${avid === 'CTRL-1' ? 1 : 2}，查看任务明细` })
          .locator('xpath=ancestor::tr')
      await row('CTRL-1').waitFor()
      await page.getByRole('checkbox', { name: '选择当前列表全部任务' }).check()
      await page.getByRole('button', { name: '暂停所选', exact: true }).click()
      await row('CTRL-1').getByText('暂停中', { exact: true }).first().waitFor()
      await page.getByRole('alert').getByText('CTRL-2：任务已更新，请重试').waitFor()
      assert.equal(jobs[0].state, 'pausing')
      const detail = page.getByRole('complementary', { name: '任务明细' })
      await detail.getByText('正在处理任务控制操作，请稍候。').waitFor()
      jobs[0].state = 'paused'
      jobs[0].version++
      jobs[0].allowed_actions = ['resume', 'cancel']
      socket.send(
        JSON.stringify({
          type: 'task_job_update',
          data: { job_id: ids[0], version: jobs[0].version },
        })
      )
      await page.getByRole('button', { name: '恢复任务 CTRL-1', exact: true }).waitFor()
      await page.getByRole('button', { name: '恢复任务 CTRL-1', exact: true }).click()
      await row('CTRL-1').getByText('等待中', { exact: true }).waitFor()
      await page.getByRole('button', { name: '取消任务 CTRL-1', exact: true }).click()
      const dialog = page.getByRole('dialog')
      await dialog.getByText(/已保存的资源会保留/).waitFor()
      await dialog.getByRole('button', { name: '取消任务', exact: true }).click()
      await row('CTRL-1').getByText('取消中', { exact: true }).first().waitFor()
      jobs[0].state = 'cancelled'
      jobs[0].version++
      jobs[0].cleanup_state = 'failed'
      jobs[0].cleanup_message = '清理失败，请检查目录权限'
      jobs[0].allowed_actions = ['cleanup_retry']
      socket.send(
        JSON.stringify({
          type: 'task_job_update',
          data: { job_id: ids[0], version: jobs[0].version },
        })
      )
      await detail.getByRole('button', { name: '重试清理', exact: true }).waitFor()
      assert.equal(
        await page.getByRole('button', { name: '不再跟踪已结束任务' }).isDisabled(),
        true
      )
      await detail.getByRole('button', { name: '重试清理', exact: true }).click()
      await detail.getByText('清理完成', { exact: true }).waitFor()
      await page.reload()
      await row('CTRL-1').getByText('已取消', { exact: true }).first().waitFor()
      await page.getByRole('button', { name: '不再跟踪任务 CTRL-1', exact: true }).click()
      await page.getByRole('dialog').getByRole('button', { name: '不再跟踪', exact: true }).click()
      await page.waitForFunction(() => document.querySelectorAll('tbody tr').length === 1)
      await page.reload()
      await row('CTRL-2').waitFor()
      assert.equal(await page.locator('tbody tr').count(), 1)
      assert.equal(commands.length, 4)
      assert.ok(
        commands.every(
          (c) => c.request_id && c.items.every((i) => Number.isInteger(i.expected_version))
        )
      )
      await page.setViewportSize({ width: 390, height: 844 })
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      await page.screenshot({ path: `/tmp/nassav-task-controls-${theme}.png`, fullPage: true })
      assert.deepEqual(errors, [])
      await page.close()
    }
    console.log(
      'Persistent task controls: both themes, batch conflicts, acknowledgements, cleanup retry, refresh, hide and mobile passed'
    )
  } finally {
    await browser.close()
  }
})().catch((e) => {
  console.error(e)
  process.exitCode = 1
})
