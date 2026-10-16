const assert = require('node:assert/strict')
const { chromium } = require('playwright')
;(async () => {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    let operation = null
    const resource = {
      avid: 'AV-1',
      source: 'jable',
      source_title: '任务提示验收',
      membership_state: 'active',
      entry_id: 'entry-a',
      entry_version: 1,
    }
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      let data = [],
        pagination
      if (path.endsWith('/auth/session'))
        data = {
          authenticated: true,
          username: 'audit',
          cache_identity: 'audit-a',
          capabilities: { shared_library: true, source_credentials: true, ordinary_login: true },
        }
      if (path.endsWith('/setting')) data = { color_mode: 'light', enable_avatar: false }
      if (path.endsWith('/source/list')) data = ['Jable']
      if (path.endsWith('/resources')) {
        data = [resource]
        pagination = { page: 1, pages: 1, total: 1, page_size: 15 }
      }
      if (path.endsWith('/library/entries/status'))
        data = [{ ...resource, is_in_my_library: true, is_available: true }]
      if (path.endsWith('/operations') && route.request().method() === 'POST') {
        operation = {
          operation_id: 'operation-a',
          avid: 'AV-1',
          kind: 'scrape',
          action: 'refresh',
          state: 'queued',
          stage: 'queued',
          version: 1,
          allowed_actions: ['cancel'],
          timeline: [{ stage: 'queued', state: 'queued', at: 1792108800 }],
        }
        data = operation
      }
      if (path.endsWith('/my-operations')) {
        data = operation ? [operation] : []
        pagination = { page: 1, pages: 1, total: data.length }
      }
      if (path.endsWith('/my-operations/operation-a')) data = operation
      await route.fulfill({ json: { code: 200, data, ...(pagination ? { pagination } : {}) } })
    })
    await page.goto((process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4196') + '/resources')
    await page.getByRole('button', { name: '刷新资源', exact: true }).first().click()
    await page.getByRole('menuitem', { name: '刷新资源', exact: true }).click()
    await page.getByRole('button', { name: '确认提交', exact: true }).click()
    await page.getByRole('status').filter({ hasText: 'AV-1 刷新任务已排队' }).waitFor()
    assert.equal(
      await page.getByRole('status').filter({ hasText: 'AV-1 刷新任务已排队' }).count(),
      1
    )
    operation = {
      ...operation,
      state: 'running',
      stage: 'translating',
      version: 2,
      timeline: [
        ...operation.timeline,
        { stage: 'running', state: 'running', at: 1792108801 },
        { stage: 'translating', state: 'running', at: 1792108802 },
        { stage: 'validating', state: 'running', at: 1792108803 },
      ],
    }
    await page.locator('a[href="/downloads"]').first().click()
    await page
      .getByRole('button', { name: /查看任务明细/ })
      .first()
      .click()
    const timeline = page.getByRole('region', { name: '活动时间线' })
    await timeline.getByText('正在翻译', { exact: true }).waitFor()
    assert.match(await timeline.innerText(), /任务已排队/)
    assert.match(await timeline.innerText(), /开始刮削/)
    assert.match(await timeline.innerText(), /校验视频/)
    assert.doesNotMatch(await timeline.innerText(), /queued|running|translating|validating/)
    assert.deepEqual(errors, [])
    console.log(
      'PASS: shared refresh shows one toast; production task timeline displays Chinese phases'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
