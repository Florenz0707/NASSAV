const { chromium } = require('playwright')
const assert = require('node:assert/strict')

async function main() {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
    const errors = [],
      cancelled = []
    let sequence = 0,
      mode = 'queued',
      legacy = false
    let addRequests = 0
    const addJob = {
      job_id: 'scrape-rec',
      job_type: 'scrape',
      avid: 'REC-001',
      action: 'add',
      version: 2,
      state: 'running',
      stage: 'translation',
      resource_saved: true,
      resource_avid: 'REC-001',
      allowed_actions: [],
    }
    page.on('pageerror', (error) => errors.push(error.message))
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    await page.route('**/nassav/api/**', async (route) => {
      const request = route.request(),
        path = new URL(request.url()).pathname
      let data = {},
        code = 200
      if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      else if (path.endsWith('/setting')) data = { color_mode: 'dark' }
      else if (path.endsWith('/resource/jobs') && request.method() === 'POST') {
        addRequests++
        data = { job_id: addJob.job_id, job: addJob }
        code = 202
      } else if (path.endsWith('/tasks/jobs/scrape-rec')) data = addJob
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
          progress: {
            stage: 'details',
            candidate_count: 24,
            verified_count: 4,
            elapsed_seconds: 120,
            recalled_count: 24,
            detail_success_count: 6,
            blacklist_excluded_count: 2,
            unverified_count: 18,
            qualified_count: 4,
            detail_attempt_count: 8,
          },
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
            seeds: [
              {
                seed_type: 'actor',
                value: '用于测试动态内容自动换行的演员名称'.repeat(8),
                resource_count: 12,
              },
            ],
            meta: {
              partial: true,
              returned_count: 1,
              requested_count: 12,
              verification_context: {
                excluded_unverified_count: 2,
                detail_success_count: 2,
                blacklist_excluded_count: 1,
                unverified_count: 2,
                qualified_count: 1,
                detail_attempt_count: 2,
              },
            },
          },
        }
      }
      if (legacy && data.result)
        data.result.meta.verification_context = { excluded_unverified_count: 2 }
      await route.fulfill({ status: code, json: { code, data } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    await page.goto(`${origin}/recommendations`)
    await page.getByRole('button', { name: '查看推荐信息' }).click()
    await page.getByText('开始推荐后显示本轮核验信息。').waitFor()
    await page.getByText('暂无高频演员数据').waitFor()
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '开始推荐', exact: true }).click()
    await page.getByRole('button', { name: '取消推荐', exact: true }).waitFor()
    await page.getByRole('button', { name: '取消推荐', exact: true }).click()
    await page.getByRole('button', { name: '取消推荐', exact: true }).waitFor({ state: 'hidden' })
    assert.ok(cancelled.includes('1'))
    mode = 'running'
    await page.locator('.header-actions .ui-button').first().click()
    const stats = page.getByRole('status').filter({ hasText: '详情获取成功' })
    await page.getByRole('button', { name: '查看推荐信息' }).click()
    await stats.waitFor()
    assert.equal(await stats.locator('dd').nth(0).innerText(), '6')
    assert.equal(await stats.locator('dd').nth(1).innerText(), '2')
    assert.equal(await stats.locator('dd').nth(2).innerText(), '18')
    assert.equal(await stats.locator('dd').nth(3).innerText(), '4')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '取消推荐', exact: true }).click()
    mode = 'succeeded'
    await page.locator('.header-actions .ui-button').first().click()
    await page.getByText('异步推荐验收', { exact: true }).waitFor()
    await page.getByRole('button', { name: '加入资源库', exact: true }).click()
    await page.getByRole('button', { name: '已添加', exact: true }).waitFor({ timeout: 4000 })
    assert.equal(await page.getByRole('button', { name: '已添加', exact: true }).isDisabled(), true)
    assert.equal(addRequests, 1)
    assert.equal(await stats.count(), 0)
    assert.ok((await page.getByText('异步推荐验收', { exact: true }).boundingBox()).y < 844)
    assert.equal(await page.locator('.remote-resource-actions .ui-button').count(), 2)
    await page.getByRole('button', { name: '查看推荐信息' }).click()
    await page.getByRole('status').filter({ hasText: '未核验不代表失败' }).waitFor()
    assert.equal(await stats.locator('dd').nth(2).innerText(), '2')
    assert.equal(await stats.locator('dd').nth(3).innerText(), '1')
    const dialog = page.getByRole('dialog', { name: '推荐信息', exact: true })
    assert.equal(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth), true)
    assert.equal(await dialog.getByRole('heading').count(), 7)
    await dialog.getByText('暂无高频类别数据').waitFor()
    await page.screenshot({ path: '/tmp/nassav-ui-recommendation-info-mobile.png' })
    await page.keyboard.press('Escape')
    await page.getByRole('status').filter({ hasText: '已为你保留 1 / 12' }).waitFor()
    await page.screenshot({ path: '/tmp/nassav-ui-recommendation-mobile.png' })
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    await page.evaluate(() => {
      document.body.style.minHeight = '2200px'
      window.scrollTo(0, 700)
    })
    const top = page.getByRole('button', { name: '回到顶部' })
    await top.waitFor()
    const normal = await top.evaluate((el) => getComputedStyle(el).backgroundColor)
    await top.hover()
    await page.waitForTimeout(200)
    assert.notEqual(await top.evaluate((el) => getComputedStyle(el).backgroundColor), normal)
    await top.click()
    await page.waitForFunction(() => window.scrollY === 0)
    await page.evaluate(() => {
      document.body.style.minHeight = ''
    })
    await page.setViewportSize({ width: 1280, height: 900 })
    await page.evaluate(() => {
      document.body.classList.remove('dark-mode')
      document.body.classList.add('light-mode')
    })
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    await page.screenshot({ path: '/tmp/nassav-ui-recommendation-desktop.png' })
    await page.getByRole('button', { name: '查看推荐信息' }).click()
    assert.equal(
      await page.getByRole('dialog').evaluate((el) => el.scrollWidth <= el.clientWidth),
      true
    )
    await page.screenshot({ path: '/tmp/nassav-ui-recommendation-info-desktop.png' })
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '设置推荐偏好' }).click()
    await page.getByRole('dialog', { name: '推荐偏好' }).waitFor()
    await page.keyboard.press('Shift+Tab')
    assert.equal(
      await page.getByRole('dialog').evaluate((el) => el.contains(document.activeElement)),
      true
    )
    await page.keyboard.press('Escape')
    assert.equal(
      await page
        .getByRole('button', { name: '设置推荐偏好' })
        .evaluate((el) => el === document.activeElement),
      true
    )
    legacy = true
    await page.locator('.header-actions .ui-button').first().click()
    await page.getByRole('button', { name: '查看推荐信息' }).click()
    await page.waitForFunction(
      () => document.querySelector('[aria-label="推荐核验统计"] dd')?.textContent.trim() === '—'
    )
    assert.equal(await stats.locator('dd').nth(2).innerText(), '2')
    assert.equal(await stats.locator('dd').nth(3).innerText(), '—')
    await page.keyboard.press('Escape')
    legacy = false
    const cancelCount = cancelled.length
    mode = 'failed'
    await page.locator('.header-actions .ui-button').first().click()
    await page.getByRole('alert').filter({ hasText: '来源暂不可用' }).waitFor()
    assert.equal(cancelled.length, cancelCount)
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
      'PASS: async success, explicit backend cancellation, worker failure, saved-resource add guard, scroll hover, dynamic dialog, verification counts, legacy fallback, mobile/desktop layout and route cleanup'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
