const { readFileSync } = require('node:fs')
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const { browserHash } = JSON.parse(readFileSync('node_modules/.vite/deps/_metadata.json', 'utf8'))
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: process.env.NASSAV_CHROMIUM_PATH } : {}
  )
  try {
    const page = await browser.newPage(),
      errors = [],
      reads = []
    let expired = false
    page.on('pageerror', (e) => errors.push(e.message))
    await page.route('**/nassav/api/**', (route) => {
      const url = new URL(route.request().url()),
        path = url.pathname,
        p = Number(url.searchParams.get('page') || 1)
      let data = {}
      if (path.endsWith('/setting')) data = { default_external_search_source: 'jable' }
      if (path.endsWith('/source/search-capabilities'))
        data = [
          { source: 'jable', label: 'Jable', actor: true, genre: true, orderings: ['-views'] },
        ]
      if (path.includes('/search/jobs')) {
        if (route.request().method() === 'GET') {
          reads.push(p)
          if (expired)
            return route.fulfill({
              status: 410,
              json: { code: 410, message: '结果已过期，请重新搜索', data: null },
            })
        }
        data = {
          task_id: 'job',
          token: 'token',
          version: 1,
          state: 'succeeded',
          result_cache_ttl_seconds: 60,
          result: {
            data: {
              external_results: [
                { avid: `PAGE-${p}`, source_title: `Result ${p}`, source: 'jable' },
              ],
              external_meta: { partial: false },
            },
            pagination: { page: p, pages: 2, total: 30, page_size: 15 },
          },
        }
      }
      return route.fulfill({ json: { code: 200, data } })
    })
    await page.route('**/__discovery-cache-audit', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<html><body><div id="app"></div><script type="module">
import {createApp,h,ref,onMounted} from '/node_modules/.vite/deps/vue.js?v=${browserHash}';
import {createPinia} from '/node_modules/.vite/deps/pinia.js?v=${browserHash}';
import {createRouter,createMemoryHistory} from '/node_modules/.vite/deps/vue-router.js?v=${browserHash}';
import {useSessionStore} from '/src/features/auth/stores/session.js';
import Panel from '/src/features/external-search/components/ExternalSearchPanel.vue';
const pinia=createPinia(),router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{render:()=>null}}]});
const session=useSessionStore(pinia);session.status='authenticated';session.identity='owner';session.sourceIdentity='owner';
const original=Date.now;window.offset=0;Date.now=()=>original()+window.offset;
createApp({setup(){const panel=ref(null);onMounted(()=>panel.value.initialize());return()=>h(Panel,{ref:panel,entityType:'actor',entityId:1})}}).use(pinia).use(router).mount('#app');
</script></body></html>`,
      })
    )
    await page.goto(
      (process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4196') + '/__discovery-cache-audit'
    )
    await page.getByRole('button', { name: '开始搜索', exact: true }).click()
    await page.getByText('PAGE-1', { exact: true }).first().waitFor()
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.getByText('PAGE-2', { exact: true }).first().waitFor()
    await page.getByRole('button', { name: '上一页', exact: true }).click()
    await page.getByText('PAGE-1', { exact: true }).first().waitFor()
    assert.deepEqual(reads, [2])
    const lifetime = await page.evaluate(() => {
      const key = Object.keys(sessionStorage).find((k) => k.startsWith('external_cn_v5_'))
      const entry = JSON.parse(sessionStorage.getItem(key))
      return entry.expiresAt - Date.now()
    })
    assert.ok(lifetime > 0 && lifetime <= 60000)
    expired = true
    await page.evaluate(() => (window.offset = 61000))
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.getByText('搜索失败：结果已过期，请重新搜索', { exact: true }).waitFor()
    assert.deepEqual(reads, [2, 2])
    assert.deepEqual(errors, [])
    console.log(
      'PASS: external result pagination cache follows server TTL; expired page is rechecked and rejects stale job (isolated API)'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
