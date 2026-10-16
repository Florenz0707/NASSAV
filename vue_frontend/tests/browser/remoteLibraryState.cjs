const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { browserHash } = JSON.parse(
  readFileSync(join(__dirname, '../../node_modules/.vite/deps/_metadata.json'), 'utf8')
)

;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4188'
  assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/)
  assert.ok(process.env.NASSAV_LIBRARY_STORAGE_STATE, 'Explicit disposable HTTP login required')
  try {
    const context = await browser.newContext({
      storageState: process.env.NASSAV_LIBRARY_STORAGE_STATE,
      viewport: { width: 1100, height: 1000 },
    })
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    await page.clock.install()
    const batches = [],
      errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (new URL(request.url()).pathname.endsWith('/library/entries/status'))
        batches.push(request.postDataJSON().avids)
    })
    await page.route('**/__remote-library-state', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<!doctype html><html><head><meta charset="utf-8"></head><body><div id="app"></div><script type="module">
import {createApp,h} from '/node_modules/.vite/deps/vue.js?v=${browserHash}';
import {createPinia} from '/node_modules/.vite/deps/pinia.js?v=${browserHash}';
import {createRouter,createMemoryHistory} from '/node_modules/.vite/deps/vue-router.js?v=${browserHash}';
import Actions from '/src/features/library/components/RemoteLibraryActions.vue';
import {useSessionStore} from '/src/features/auth/stores/session.js';
import {useMembershipsStore} from '/src/features/library/stores/memberships.js';
import '/src/styles/main.css';
const pinia=createPinia(),session=useSessionStore(pinia),cache=useMembershipsStore(pinia);
await session.initialize();cache.reset(session.identity);
const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{render:()=>null}}]});
const added=[];const ids=['LOCAL-PLAYBACK','OPERATION-UI','UNKNOWN-1','UNKNOWN-2'];
const app=createApp({render:()=>h('main',{class:'p-6 space-y-4'},ids.map(avid=>h('section',{'data-avid':avid,class:'p-4 bg-secondary border rounded-xl'},[h('h2',avid),h(Actions,{avid,added:true,onAdd:()=>added.push(avid)})])))});
app.use(pinia).use(router).mount('#app');window.audit={app,cache,router,added};
</script></body></html>`,
      })
    )
    await page.goto(origin + '/__remote-library-state')
    const local = page.locator('[data-avid="LOCAL-PLAYBACK"]'),
      pending = page.locator('[data-avid="OPERATION-UI"]'),
      unknown = page.locator('[data-avid="UNKNOWN-1"]')
    await local.getByRole('button', { name: '已添加', exact: true }).waitFor()
    assert.equal(
      await local.getByRole('button', { name: '已添加', exact: true }).isDisabled(),
      true
    )
    await pending.getByRole('button', { name: '准备中', exact: true }).waitFor()
    await pending.getByRole('button', { name: '查看任务', exact: true }).click()
    assert.equal(
      await page.evaluate(() => window.audit.router.currentRoute.value.path),
      '/downloads'
    )
    await unknown.getByRole('button', { name: '加入资源库', exact: true }).click()
    assert.deepEqual(await page.evaluate(() => window.audit.added), ['UNKNOWN-1'])
    assert.equal(batches.length, 1, 'Mounted cards must share one actual HTTP lookup')
    assert.equal(batches[0].length, 4)
    const csrf = (await context.cookies()).find((cookie) => cookie.name === 'csrftoken').value
    const operations = (await (await page.request.get(origin + '/nassav/api/my-operations')).json())
      .data
    const operation = operations.find((item) => item.avid === 'OPERATION-UI')
    const previousRevision = await page.evaluate(() => window.audit.cache.revision)
    const cancelled = await page.request.post(
      `${origin}/nassav/api/my-operations/${operation.operation_id}/cancel`,
      {
        headers: { 'X-CSRFToken': csrf },
        data: {
          expected_version: operation.version,
          request_id: await page.evaluate(() => crypto.randomUUID()),
        },
      }
    )
    assert.equal(cancelled.status(), 200)
    const before = batches.length
    await page.clock.runFor(30000)
    await pending.getByRole('button', { name: '加入资源库', exact: true }).waitFor()
    assert.equal(batches.length, before + 1)
    const changedRevision = await page.evaluate(() => window.audit.cache.revision)
    assert.equal(changedRevision, previousRevision + 1)
    await page.clock.runFor(30000)
    assert.equal(await page.evaluate(() => window.audit.cache.revision), changedRevision)
    assert.equal(
      batches.length,
      before + 2,
      'Unchanged peer refresh must not create invalidation loops'
    )
    let fail = true
    await page.route('**/nassav/api/library/entries/status', (route) => {
      if (fail) {
        fail = false
        return route.abort('failed')
      }
      return route.continue()
    })
    await page.evaluate(() => window.audit.cache.invalidate())
    await unknown.getByRole('button', { name: '重试状态', exact: true }).click()
    await unknown.getByRole('button', { name: '加入资源库', exact: true }).waitFor()
    const count = batches.length
    await page.evaluate(() => window.audit.app.unmount())
    await page.clock.runFor(30000)
    assert.equal(batches.length, count, 'Unmount must stop visible-card refresh')
    assert.deepEqual(errors, [])
    console.log(
      'Native membership controls passed: coalesced query, stale added flag ignored, pending request link, timed own membership refresh, transport retry and timer teardown'
    )
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
