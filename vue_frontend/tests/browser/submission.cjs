const { chromium } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage(),
      errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', (route) => {
      const path = new URL(route.request().url()).pathname
      let data = {}
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      if (path.endsWith('/setting')) data = { color_mode: 'dark' }
      if (path.endsWith('/source/list')) data = ['Jable']
      if (path.endsWith('/tasks/jobs')) data = { jobs: [], pagination: { total: 0 } }
      if (path.endsWith('/resource/jobs/batch'))
        data = {
          results: ['AAA-1', 'BBB-2'].map((avid, i) => ({
            code: 202,
            avid,
            task_id: 'initial-' + i,
            job_id: 'job-' + i,
            action: 'add',
          })),
        }
      if (/\/tasks\/jobs\/job-/.test(path)) {
        const i = path.endsWith('0') ? 0 : 1
        data = {
          job_id: 'job-' + i,
          task_id: 'translation-' + i,
          job_type: 'scrape',
          avid: i === 0 ? 'AAA-1' : 'BBB-2',
          action: 'add',
          state: 'succeeded',
          version: 2,
          resource_saved: true,
          updated_at: 100 + i,
        }
      }
      return route.fulfill({ json: { code: 200, data } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    for (const mode of ['dark', 'light']) {
      await page.goto(origin + '/add')
      await page.locator('body').evaluate((el, mode) => (el.className = mode + '-mode'), mode)
      await page.getByLabel(/视频编号/).fill('AAA-1 BBB-2')
      await page.getByRole('button', { name: '批量添加 (2)', exact: true }).click()
      await page.getByRole('heading', { name: '已完成 (2)', exact: true }).waitFor()
      assert.equal(await page.locator('.result-tag.success').count(), 2)
      assert.equal(
        await page.locator('.batch-result-card').evaluate((el) => getComputedStyle(el).paddingTop),
        '32px'
      )
    }
    assert.deepEqual(errors, [])
    console.log(
      'PASS: extracted submission workflow follows translation attempts; result styles preserved in both themes'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
