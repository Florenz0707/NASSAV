const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { chromium, firefox } = require('playwright')
;(async () => {
  const { browserHash } = JSON.parse(readFileSync('node_modules/.vite/deps/_metadata.json', 'utf8'))
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: process.env.NASSAV_CHROMIUM_PATH } : {}
  )
  try {
    const page = await browser.newPage(),
      calls = [],
      errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/nassav/api/**', (route) => {
      const url = new URL(route.request().url()),
        number = Number(url.searchParams.get('page') || 1)
      calls.push(`${url.pathname}:${number}`)
      return route.fulfill({
        json: {
          code: 200,
          data: [{ avid: `PAGE-${number}`, name: `PAGE-${number}`, id: number }],
          pagination: { page: number, pages: 2, total: 30 },
        },
      })
    })
    await page.route('**/__read-cache-audit', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<html><body><div id="app"></div><script type="module">
import {createApp,h,ref} from '/node_modules/.vite/deps/vue.js?v=${browserHash}';
import {createPinia} from '/node_modules/.vite/deps/pinia.js?v=${browserHash}';
import {useResourceStore} from '/src/features/resources/stores/resource.js';
import {useActorGroupsStore} from '/src/features/catalog/stores/actorGroups.js';
createApp({setup(){const resources=useResourceStore(),actors=useActorGroupsStore(),kind=ref('resources');
const load=p=>kind.value==='resources'?resources.fetchResources({page:p}):actors.load({page:p});
load(1);return()=>h('main',[
h('button',{onClick:()=>load(1)},'page1'),h('button',{onClick:()=>load(2)},'page2'),
h('button',{onClick:()=>{resources.invalidateResourceQueries();actors.invalidate();load(1)}},'refresh'),
h('button',{onClick:()=>{kind.value='actors';load(1)}},'actors'),
h('button',{onClick:()=>{resources.beginSession('next-owner');actors.reset();load(1)}},'owner'),
h('output',(kind.value==='resources'?resources.resources:actors.groups).map(item=>item.avid).join(','))]);}}).use(createPinia()).mount('#app');
</script></body></html>`,
      })
    )
    await page.goto(
      (process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4196') + '/__read-cache-audit'
    )
    const result = page.locator('output')
    await result.getByText('PAGE-1', { exact: true }).waitFor()
    for (const kind of ['resources', 'actors']) {
      if (kind === 'actors') {
        await Promise.all([
          page.waitForResponse((r) => r.url().includes('/actors')),
          page.getByRole('button', { name: 'actors', exact: true }).click(),
        ])
      }
      const start = calls.length
      await page.getByRole('button', { name: 'page2', exact: true }).click()
      await result.getByText('PAGE-2', { exact: true }).waitFor()
      await page.getByRole('button', { name: 'page1', exact: true }).click()
      await result.getByText('PAGE-1', { exact: true }).waitFor()
      assert.equal(calls.length, start + 1, `${kind}: returning to page1 uses cached list`)
      await Promise.all([
        page.waitForResponse((r) =>
          r.url().includes(kind === 'resources' ? '/resources' : '/actors')
        ),
        page.getByRole('button', { name: 'refresh', exact: true }).click(),
      ])
      assert.equal(calls.length, start + 2)
    }
    const beforeOwner = calls.length
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/actors')),
      page.getByRole('button', { name: 'owner', exact: true }).click(),
    ])
    assert.equal(calls.length, beforeOwner + 1)
    assert.deepEqual(errors, [])
    console.log(
      'PASS: resource/directory page1-page2-page1 caching, manual refresh and owner reset; isolated API'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
