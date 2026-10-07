const { chromium } = require('playwright')
const assert = require('node:assert/strict')

async function main() {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
    const errors = [],
      cancelled = []
    let sequence = 0,
      mode = 'queued'
    page.on('pageerror', (error) => errors.push(error.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', async (route) => {
      const request = route.request(),
        path = new URL(request.url()).pathname
      let data = {},
        code = 200
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      else if (path.endsWith('/setting')) data = { color_mode: 'dark' }
      else if (path.endsWith('/recommendations/jobs')) {
        sequence++
        data = { job_id: String(sequence), version: 1, state: 'queued' }
        code = 202
      } else if (path.endsWith('/cancel')) {
        cancelled.push(path.split('/').at(-2))
        data = { job_id: path.split('/').at(-2), version: 3, state: 'cancelled' }
      } else if (/recommendations\/jobs\/[^/]+$/.test(path)) {
        data = {
          job_id: path.split('/').at(-1),
          version: 2,
          state: mode,
          message: '来源暂不可用',
          result: {
            items: [
              {
                avid: 'REC-001',
                title: '异步推荐验收',
                source: 'Jable',
                matched_seeds: [],
                raw_metrics: {},
                score_breakdown: [],
              },
            ],
            seeds: [],
            meta: { verification_context: { excluded_unverified_count: 2 } },
          },
        }
      }
      await route.fulfill({ status: code, json: { code, data } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    await page.goto(`${origin}/recommendations`)
    await page.getByRole('button', { name: '开始推荐', exact: true }).click()
    await page.getByRole('button', { name: '取消推荐', exact: true }).waitFor()
    await page.getByRole('button', { name: '取消推荐', exact: true }).click()
    await page.getByRole('button', { name: '取消推荐', exact: true }).waitFor({ state: 'hidden' })
    assert.ok(cancelled.includes('1'))
    mode = 'succeeded'
    await page.locator('.header-actions .ui-button').first().click()
    await page.getByText('异步推荐验收', { exact: true }).waitFor()
    await page.getByRole('status').filter({ hasText: '2 条候选因详情未核验' }).waitFor()
    mode = 'failed'
    await page.locator('.header-actions .ui-button').first().click()
    await page.getByRole('alert').filter({ hasText: '来源暂不可用' }).waitFor()
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    mode = 'queued'
    await page.locator('.header-actions .ui-button').first().click()
    await page.getByRole('button', { name: '取消推荐', exact: true }).waitFor()
    await page.evaluate(() => {
      history.pushState({}, '', '/resources')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await page.waitForTimeout(500)
    assert.ok(cancelled.includes(String(sequence)))
    assert.deepEqual(errors, [])
    console.log(
      'PASS: async success, explicit backend cancellation, worker failure, mobile layout and route cleanup'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
