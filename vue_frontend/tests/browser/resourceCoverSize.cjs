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
      requests = [],
      errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/nassav/api/**', (route) => {
      const url = new URL(route.request().url())
      if (!url.pathname.endsWith('/resource/cover'))
        return route.fulfill({ json: { code: 200, data: {} } })
      requests.push(url)
      const width = { small: 200, medium: 600, large: 1200 }[url.searchParams.get('size')] || 1600
      return route.fulfill({
        contentType: 'image/svg+xml',
        body: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${width / 2}"><rect width="100%" height="100%"/></svg>`,
      })
    })
    await page.route('**/__cover-size-audit', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<html><body><div id="app"></div><script type="module">
import {createApp,h,ref} from '/node_modules/.vite/deps/vue.js?v=${browserHash}';
import {createPinia} from '/node_modules/.vite/deps/pinia.js?v=${browserHash}';
import {createRouter,createMemoryHistory} from '/node_modules/.vite/deps/vue-router.js?v=${browserHash}';
import Card from '/src/features/resources/components/ResourceCard.vue';
import {setBrowserContext} from '/src/api/client.js';
setBrowserContext('size-login');
const size=ref(undefined);
const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{render:()=>null}}]});
createApp({setup:()=>()=>h('main',[
  ...['small','large','original'].map(value=>h('button',{onClick:()=>size.value=value==='original'?null:value},value)),
  h('div',{style:'width:400px'},[h(Card,{resource:{avid:'YUJ-036',source_title:'Cover size audit',thumbnail_url:'/nassav/api/resource/cover?avid=YUJ-036&size=small&v=version-one'},coverSize:size.value})])
])}).use(createPinia()).use(router).mount('#app');
</script></body></html>`,
      })
    )
    await page.goto(
      (process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4196') + '/__cover-size-audit'
    )
    const image = page.locator('img').first()
    await image.waitFor()
    await image.evaluate((element) => element.decode())
    assert.equal(
      await image.evaluate((element) => element.naturalWidth),
      600,
      'default medium must override backend small'
    )
    for (const [label, expected, width] of [
      ['small', 'small', 200],
      ['large', 'large', 1200],
      ['original', null, 1600],
    ]) {
      await page.getByRole('button', { name: label, exact: true }).click()
      await page.waitForFunction(
        (width) => document.querySelector('img')?.naturalWidth === width,
        width
      )
      assert.equal(requests.at(-1).searchParams.get('size'), expected)
      assert.deepEqual(requests.at(-1).searchParams.getAll('_context'), ['size-login'])
      assert.equal(requests.at(-1).searchParams.get('v'), 'version-one')
    }
    assert.deepEqual(errors, [])
    console.log(
      'PASS: default medium overrides server small; reactive small/large/original update actual image dimensions, retaining context/version'
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
