const { chromium } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const browser = await chromium.launch({
    executablePath: process.env.NASSAV_CHROMIUM_PATH,
    headless: true,
  })
  try {
    const page = await browser.newPage()
    const errors = [],
      submissions = [],
      resourceQueries = [],
      jobs = new Map()
    await page.routeWebSocket('**/nassav/ws/**', () => {})
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/nassav/api/**', async (route) => {
      const request = route.request(),
        url = new URL(request.url())
      let data = {},
        pagination
      if (url.pathname.endsWith('/auth/session')) data = { authenticated: true, username: 'audit' }
      else if (url.pathname.endsWith('/setting'))
        data = { color_mode: 'dark', enable_avatar: 'false' }
      else if (url.pathname.endsWith('/source/search-capabilities'))
        data = ['jable', 'missav'].map((source) => ({
          source,
          label: source,
          actor: true,
          genre: true,
          orderings: ['-views', 'views', '-likes', 'likes', '-latest', 'latest'],
        }))
      else if (/\/(actors|genres)$/.test(url.pathname))
        data = [{ id: 1, name: 'Audit entity', resource_count: 0 }]
      else if (url.pathname.endsWith('/resources')) {
        resourceQueries.push(url)
        data = []
        pagination = {
          page: Number(url.searchParams.get('page')),
          pages: 2,
          total: 0,
          page_size: 18,
        }
      } else if (url.pathname.endsWith('/search/jobs') && request.method() === 'POST') {
        const query = request.postDataJSON()
        submissions.push(query)
        const task_id = `job-${submissions.length}`
        data = {
          task_id,
          token: 'audit',
          state: 'running',
          version: 1,
          pages_completed: 1,
          result: {
            data: {
              detail: { id: 1, name: 'Audit entity' },
              external_results: [
                { avid: 'EXT-001', source_title: 'Partial result', source: query.source },
              ],
              external_meta: { partial: true, fetch_pages: 2 },
            },
            pagination: { page: 1, pages: 1, total: 1 },
          },
        }
        jobs.set(task_id, data)
      } else if (/\/search\/jobs\/[^/]+\/cancel$/.test(url.pathname)) {
        const id = url.pathname.split('/').at(-2)
        data = { ...jobs.get(id), state: 'cancelled', version: 2 }
        jobs.set(id, data)
      } else if (/\/search\/jobs\/[^/]+$/.test(url.pathname))
        data = jobs.get(url.pathname.split('/').at(-1))
      await route.fulfill({ json: { code: 200, data, pagination } })
    })
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    for (const type of ['actor', 'genre']) {
      await page.goto(`${origin}/${type}s/1?page=2`)
      await page.getByRole('button', { name: '本地资源', exact: true }).waitFor()
      await page.waitForFunction(
        () =>
          document.body.textContent.includes('暂无匹配资源') ||
          document.body.textContent.includes('暂无资源')
      )
      assert.equal(resourceQueries.at(-1).searchParams.get(type), '1')
      assert.equal(resourceQueries.at(-1).searchParams.get('page'), '2')
      const before = submissions.length
      await page.getByRole('button', { name: '外部搜索', exact: true }).click()
      await page.waitForTimeout(100)
      assert.equal(submissions.length, before)
      assert.equal(await page.getByRole('heading', { name: '外部搜索', exact: true }).count(), 0)
      await page.getByRole('button', { name: '搜索设置', exact: true }).click()
      const source = page
        .getByRole('dialog', { name: '搜索设置', exact: true })
        .getByRole('button', { name: '搜索源', exact: true })
      await source.click()
      await page.getByRole('option', { name: 'missav', exact: true }).click()
      await page.getByRole('button', { name: '完成', exact: true }).click()
      await page.waitForTimeout(100)
      assert.equal(submissions.length, before)
      await page.getByRole('button', { name: '开始搜索', exact: true }).click()
      await page.getByText('Partial result', { exact: true }).waitFor()
      assert.equal(submissions.at(-1).entity_type, type)
      assert.equal(submissions.at(-1).entity_id, 1)
      assert.equal(submissions.at(-1).source, 'missav')
      await page.getByRole('button', { name: '取消搜索', exact: true }).click()
      await page.getByText('搜索已取消，已获取的结果仍可查看。', { exact: true }).waitFor()
      assert.equal(await page.getByText('Partial result', { exact: true }).isVisible(), true)
      await page.screenshot({ path: `/tmp/nassav-f5-${type}.png`, fullPage: true })
    }
    assert.deepEqual(errors, [])
    console.log(
      'PASS: actor/genre adapters, restored page, explicit search, source change, partial results and backend cancellation'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
