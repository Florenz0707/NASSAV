const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
      page.setDefaultTimeout(15000)
      const errors = [],
        writes = []
      let socket,
        translationReads = 0,
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
          translation: { state: 'not_requested' },
          timeline: [
            { stage: 'metadata', state: 'running', at: 1700000000 },
            { stage: 'failed', state: 'failed', at: 1700000010 },
          ],
        },
        {
          task_id: 'scrape-ok',
          resource: { avid: 'AV-4', source_title: '已保存的资源', translated_title: '资源译文' },
          translation: { task_id: 'child', state: 'queued' },
          avid: 'AV-4',
          action: 'add',
          state: 'succeeded',
          stage: 'translation_queued',
          status_token: 'fake',
          updated_at: 2,
          timeline: [
            { stage: 'saving', state: 'running', at: 1700000000 },
            { stage: 'resource_saved', state: 'succeeded', at: 1700000010 },
          ],
        },
        {
          task_id: 'scrape-translating',
          avid: 'AV-5',
          action: 'add',
          state: 'succeeded',
          status_token: 'fake',
          translation: { task_id: 'waiting-child', state: 'translating' },
          updated_at: 3,
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
        if (path.endsWith('/tasks/jobs'))
          data = { jobs: [], pagination: { total: 0, has_more: false } }
        if (path.endsWith('/setting')) data = { color_mode: theme }
        if (path.includes('/resource/jobs/')) {
          data = jobs.find((job) => path.endsWith(job.task_id))
          if (data?.task_id === 'scrape-ok') {
            translationReads++
            data = {
              ...data,
              translation: {
                task_id: 'child',
                state: translationReads > 1 ? 'completed' : 'queued',
                completed_at: translationReads > 1 ? '2026-10-06T10:00:00+00:00' : undefined,
              },
            }
          }
        }
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
      assert.equal(await page.locator('tbody tr').count(), 5)
      assert.equal(await page.getByRole('button', { name: '打开通知' }).count(), 0)
      assert.equal(await page.locator('tbody img').count(), 0)
      assert.equal(await page.getByRole('columnheader', { name: '类型', exact: true }).count(), 1)
      const downloadRow = page
        .getByRole('button', { name: '正在下载的资源，查看任务明细' })
        .locator('xpath=ancestor::tr')
      const scrapeRow = page
        .getByRole('button', { name: 'AV-3，查看任务明细' })
        .locator('xpath=ancestor::tr')
      assert.equal((await downloadRow.locator('td').nth(1).textContent()).trim(), 'AV-1')
      assert.equal((await downloadRow.locator('td').nth(2).textContent()).trim(), 'download')
      assert.equal((await scrapeRow.locator('td').nth(2).textContent()).trim(), 'scrape')
      const downloadBadge = await downloadRow
        .locator('td')
        .nth(2)
        .locator('span')
        .evaluate((node) => getComputedStyle(node).backgroundColor)
      const scrapeBadge = await scrapeRow
        .locator('td')
        .nth(2)
        .locator('span')
        .evaluate((node) => getComputedStyle(node).backgroundColor)
      assert.notEqual(downloadBadge, scrapeBadge)
      const hideButton = page.getByRole('button', { name: '不再跟踪任务 AV-1', exact: true })
      assert.equal(await hideButton.locator('svg').count(), 1)
      assert.equal((await hideButton.textContent()).trim(), '')
      assert.equal(
        await page
          .getByRole('button', { name: '结束任务 AV-1', exact: true })
          .locator('svg')
          .count(),
        1
      )
      const checkboxVisual = page
        .getByRole('checkbox', { name: '选择任务 AV-1', exact: true })
        .locator('xpath=following-sibling::span')
      const outline = await checkboxVisual.evaluate((node) => {
        const style = getComputedStyle(node)
        return {
          width: style.borderTopWidth,
          border: style.borderTopColor,
          token: getComputedStyle(document.body).getPropertyValue('--text-secondary').trim(),
        }
      })
      assert.equal(outline.width, '2px')
      assert.equal(
        await checkboxVisual.evaluate((node) => {
          const reference = document.createElement('span')
          reference.style.color = 'var(--text-secondary)'
          document.body.append(reference)
          const expected = getComputedStyle(reference).color
          reference.remove()
          return getComputedStyle(node).borderTopColor === expected
        }),
        true
      )
      await page.screenshot({ path: '/tmp/nassav-task-badges-' + theme + '.png', fullPage: true })

      const firstBox = page.getByRole('checkbox', { name: '选择任务 AV-1', exact: true })
      const filter = page.getByRole('button', { name: '任务状态', exact: true })
      const filterWidth = (await filter.boundingBox()).width
      assert.ok(filterWidth >= 128)
      await filter.click()
      await page.getByRole('option', { name: '失败', exact: true }).click()
      assert.ok(Math.abs((await filter.boundingBox()).width - filterWidth) < 1)
      await filter.click()
      await page.getByRole('option', { name: '全部状态', exact: true }).click()
      await firstBox.check()
      await page.getByRole('status', { name: '已选择 1 个任务', exact: true }).waitFor()
      assert.equal(
        (
          await page.getByRole('button', { name: '不再跟踪所选', exact: true }).textContent()
        ).trim(),
        '不再跟踪所选'
      )
      const selectAll = page.getByRole('checkbox', { name: '选择当前列表全部任务' })
      assert.equal(await selectAll.evaluate((node) => node.indeterminate), true)
      const headerBox = await selectAll.boundingBox(),
        rowBox = await firstBox.boundingBox()
      assert.ok(
        Math.abs(headerBox.x - rowBox.x) < 1,
        'Header and row checkbox must share x position'
      )
      await firstBox.uncheck()
      await firstBox.focus()
      await page.keyboard.press('Space')
      assert.equal(await firstBox.isChecked(), true)
      await page.keyboard.press('Space')
      assert.equal(await firstBox.isChecked(), false)
      assert.equal(await page.getByRole('button', { name: '结束所选任务' }).isDisabled(), true)
      assert.equal(
        await page.getByRole('button', { name: '结束任务 AV-1', exact: true }).isDisabled(),
        true
      )
      assert.equal(await detail.getByRole('button', { name: '不再跟踪此任务' }).count(), 0)
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
      assert.equal(await page.getByRole('columnheader', { name: '类型', exact: true }).count(), 0)
      await page.getByRole('button', { name: '已保存的资源，查看任务明细' }).click()
      await detail.getByText('翻译完成', { exact: true }).first().waitFor()
      assert.ok((await detail.locator('time').count()) >= 3)
      const timeEnds = await detail
        .locator('time')
        .evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().right))
      assert.ok(timeEnds.every((end) => Math.abs(end - timeEnds[0]) < 1))
      await page.getByRole('button', { name: 'AV-5，查看任务明细' }).click()
      assert.ok((await detail.textContent()).includes('执行中'))
      await page.getByRole('button', { name: 'AV-3，查看任务明细' }).click()
      assert.equal(await detail.getByRole('alert').textContent(), '来源超时')
      assert.equal(await detail.getByRole('progressbar').count(), 0)
      assert.equal(
        (
          await page
            .getByRole('button', { name: 'AV-3，查看任务明细' })
            .locator('xpath=ancestor::tr')
            .locator('td')
            .nth(3)
            .textContent()
        ).trim(),
        '失败'
      )
      assert.equal(
        await detail.getByRole('link', { name: '查看资源' }).getAttribute('href'),
        '/resource/AV-3'
      )
      const resourceLink = detail.getByRole('link', { name: '查看资源' })
      assert.ok(
        await resourceLink.evaluate(
          (node) =>
            parseFloat(getComputedStyle(node).borderRadius) > 0 &&
            getComputedStyle(node).backgroundColor !== 'rgba(0, 0, 0, 0)'
        )
      )
      await page.screenshot({ path: '/tmp/nassav-task-timeline-' + theme + '.png', fullPage: true })
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
      await page.waitForFunction(() => document.querySelectorAll('tbody tr').length === 3)
      await page.getByRole('button', { name: '不再跟踪当前列表已结束任务' }).click()
      await page
        .getByRole('dialog', { name: '不再跟踪任务' })
        .getByText(/所选 2 个任务/)
        .waitFor()
      await page
        .getByRole('dialog', { name: '不再跟踪任务' })
        .getByRole('button', { name: '不再跟踪', exact: true })
        .click()
      await page.waitForFunction(() => document.querySelectorAll('tbody tr').length === 1)
      await page.getByRole('button', { name: 'AV-5，查看任务明细' }).waitFor()
      assert.equal(
        await page.getByRole('button', { name: '不再跟踪当前列表已结束任务' }).isDisabled(),
        true
      )
      // Per-row operation also requires confirmation and does not touch the API.
      await page.getByRole('button', { name: '不再跟踪任务 AV-5', exact: true }).click()
      await page
        .getByRole('dialog', { name: '不再跟踪任务' })
        .getByRole('button', { name: '取消', exact: true })
        .click()
      await page.getByRole('checkbox', { name: '选择当前列表全部任务' }).check()
      await page.getByRole('button', { name: '不再跟踪所选' }).click()
      await page
        .getByRole('dialog', { name: '不再跟踪任务' })
        .getByRole('button', { name: '不再跟踪', exact: true })
        .click()
      await page.getByText('暂无此类任务', { exact: true }).waitFor()
      console.log(theme, 'legacy empty')
      await page.evaluate(() => window.scrollTo(0, 0))
      const empty = page.getByLabel('任务列表空白区域', { exact: true })
      const region = await empty.boundingBox()
      const content = await empty.locator(':scope > div').boundingBox()
      assert.ok(Math.abs(content.y + content.height / 2 - (region.y + region.height / 2)) < 1)
      assert.ok(region.y + region.height <= 1100, 'Empty region stays within the first viewport')
      assert.ok(
        await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight),
        'Empty list does not add desktop scrolling'
      )
      assert.equal(
        await page.evaluate(() => JSON.parse(localStorage.getItem('nassav:scrape-jobs:v1')).length),
        0
      )
      for (const viewport of [
        { width: 1440, height: 900 },
        { width: 640, height: 900 },
        { width: 390, height: 844 },
      ]) {
        await page.setViewportSize(viewport)
        const emptyRegion = await empty.boundingBox()
        const emptyContent = await empty.locator(':scope > div').boundingBox()
        assert.ok(
          Math.abs(
            emptyContent.y + emptyContent.height / 2 - (emptyRegion.y + emptyRegion.height / 2)
          ) < 1,
          'Empty content remains centered after resizing'
        )
        assert.ok(emptyRegion.y + emptyRegion.height <= viewport.height)
        assert.equal(
          await page.evaluate(
            () =>
              document.documentElement.scrollWidth <= innerWidth &&
              document.documentElement.scrollHeight <= innerHeight
          ),
          true,
          'Empty list fits the first viewport without scrolling'
        )
      }
      await page.screenshot({
        path: '/tmp/nassav-task-empty-' + theme + '.png',
        fullPage: true,
      })
      assert.deepEqual(writes, [])
      assert.deepEqual(errors, [])
      await page.close()
    }
    const demo = await browser.newPage()
    demo.setDefaultTimeout(15000)
    console.log('legacy DEBUG loading')
    let demoQueueReads = 0
    const demoErrors = []
    demo.on('pageerror', (e) => demoErrors.push(e.message))
    await demo.routeWebSocket('**/nassav/ws/**', () => {})
    await demo.route('**/src/views/DownloadsView.vue*', async (route) => {
      const response = await route.fetch()
      const source = await response.text()
      assert.ok(source.includes('const DEBUG_MODE = false'))
      await route.fulfill({
        response,
        body: source.replace('const DEBUG_MODE = false', 'const DEBUG_MODE = true'),
      })
    })
    await demo.route('**/nassav/api/**', (route) => {
      const path = new URL(route.request().url()).pathname
      assert.equal(route.request().method(), 'GET')
      if (path.endsWith('/tasks/queue/status')) demoQueueReads++
      const data = path.endsWith('/auth/session')
        ? { authenticated: true }
        : path.endsWith('/setting')
          ? { color_mode: 'dark' }
          : []
      return route.fulfill({ json: { code: 200, data } })
    })
    await demo.goto((process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178') + '/downloads')
    await demo.getByText('DEBUG · 模拟数据', { exact: true }).waitFor()
    await demo.getByRole('button', { name: '海边的一日，查看任务明细' }).click()
    const demoDetail = demo.getByRole('complementary', { name: '任务明细' })
    await demoDetail.getByText('翻译完成', { exact: true }).first().waitFor()
    await demo.getByRole('button', { name: '演示下一阶段' }).click()
    for (let i = 0; i < 7; i++) await demo.getByRole('button', { name: '演示下一阶段' }).click()
    await demoDetail.getByText('翻译完成', { exact: true }).first().waitFor()
    assert.ok((await demoDetail.textContent()).includes('已完成'))
    assert.equal(demoQueueReads, 0)
    assert.deepEqual(demoErrors, [])
    await demo.close()
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
