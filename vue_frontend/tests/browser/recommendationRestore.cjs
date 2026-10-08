const { chromium } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
    let submissions = 0,
      fail = false
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      let data = {},
        code = 200
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      else if (path.endsWith('/setting')) data = { color_mode: 'dark' }
      else if (path.endsWith('/recommendations/jobs')) {
        submissions++
        code = 202
        data = { job_id: String(submissions), version: 1, state: 'queued' }
      } else if (/recommendations\/jobs\/\d+$/.test(path)) {
        const id = path.split('/').at(-1)
        data = {
          job_id: id,
          version: 2,
          state: fail ? 'failed' : 'succeeded',
          message: '测试来源不可用',
          result: {
            items: [
              {
                avid: `REC-${id}`,
                title: `批次 ${id}`,
                score: 1,
                reasons: ['偏好匹配'],
                raw_metrics: {},
              },
            ],
            seeds: [{ seed_type: 'actor', value: '演员一', resource_count: 3 }],
            meta: { verification_context: { detail_success_count: 2, qualified_count: 1 } },
          },
        }
      } else if (/\/(actors|genres)$/.test(path) || path.endsWith('/avid-blocklist')) data = []
      await route.fulfill({ status: code, json: { code, data } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4190'
    await page.goto(origin + '/recommendations')
    await page.getByRole('button', { name: '开始推荐', exact: true }).click()
    await page.getByText('批次 1', { exact: true }).waitFor()
    await page.goto(origin + '/resources')
    await page.goto(origin + '/recommendations')
    await page.getByText('批次 1', { exact: true }).waitFor()
    await page.locator('.results-footer').getByRole('button', { name: '继续推荐' }).click()
    await page.getByText('批次 2', { exact: true }).waitFor()
    await page.reload()
    await page.getByText('批次 1', { exact: true }).waitFor()
    await page.getByText('批次 2', { exact: true }).waitFor({ timeout: 4000 })
    assert.equal(submissions, 2)
    assert.equal(await page.locator('.recommendation-card .cover-shell button').count(), 0)
    assert.equal(
      await page
        .locator('.recommendation-card .inline-feedback-actions')
        .first()
        .getByRole('button')
        .count(),
      3
    )
    fail = true
    await page.locator('.results-footer').getByRole('button', { name: '继续推荐' }).click()
    const footer = page.locator('.results-footer')
    await footer.getByText('测试来源不可用').waitFor()
    assert.equal(await page.getByRole('alert').count(), 0)
    assert.equal(await page.locator('.header-actions').getByText('测试来源不可用').count(), 0)
    const errorBox = await footer.getByText('测试来源不可用').boundingBox()
    const buttonBox = await footer.getByRole('button', { name: '继续推荐' }).boundingBox()
    assert.ok(errorBox.y > buttonBox.y)
    assert.equal(await page.locator('.recommendation-card').count(), 2)
    await page.getByRole('button', { name: '查看推荐信息' }).click()
    const info = page.getByRole('dialog', { name: '推荐信息' })
    assert.equal(await info.getByRole('heading').count(), 2)
    assert.equal(await info.getByRole('button').count(), 3)
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '设置推荐偏好' }).click()
    const preferences = page.getByRole('dialog', { name: '推荐偏好' })
    const left = await preferences.getByRole('button', { name: '种子偏好' }).boundingBox()
    const right = await preferences.getByRole('button', { name: '演员黑名单' }).boundingBox()
    assert.ok(left.x < right.x)
    await page.screenshot({ path: '/tmp/nassav-recommendation-preferences-desktop.png' })
    await page.setViewportSize({ width: 390, height: 844 })
    assert.equal(await preferences.evaluate((el) => el.scrollWidth <= el.clientWidth), true)
    const panel = await preferences.boundingBox()
    assert.ok(panel.height < 844)
    await page.screenshot({ path: '/tmp/nassav-recommendation-preferences-mobile.png' })
    await page.keyboard.press('Escape')
    await page.screenshot({ path: '/tmp/nassav-recommendation-context-mobile.png' })
    await page.reload()
    await page.getByText('批次 2', { exact: true }).waitFor()
    assert.equal(submissions, 3)
    await page.getByRole('button', { name: '清空页面', exact: true }).click()
    await page.getByRole('heading', { name: '尚未开始推荐' }).waitFor()
    await page.reload()
    await page.getByRole('heading', { name: '尚未开始推荐' }).waitFor()
    await page.getByRole('button', { name: '开始推荐', exact: true }).click()
    await page.locator('.results-footer').getByText('测试来源不可用').waitFor()
    assert.equal(await page.getByRole('alert').count(), 0)
    assert.equal(await page.locator('.recommendation-card').count(), 0)
    assert.deepEqual(errors, [])
    console.log(
      'PASS: multi-batch hard reload, failed continuation and initial failure footer, clear persistence, compact context, card controls and combined preferences'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
