const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join, dirname } = require('node:path')
const { execFileSync } = require('node:child_process')
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
  const fixturePath = process.env.NASSAV_DISCOVERY_IMAGE_FIXTURE
  assert.match(
    fixturePath || '',
    /^\/tmp\/nassav-local-playback-http-[^/]+\/discovery-image-fixture\.json$/
  )
  const fixture = JSON.parse(readFileSync(fixturePath, 'utf8'))
  try {
    const context = await browser.newContext({
      storageState: join(dirname(fixturePath), 'storage-state.json'),
      viewport: { width: 1100, height: 950 },
    })
    const page = await context.newPage(),
      errors = [],
      images = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (new URL(request.url()).pathname.endsWith('/recommendations/cover'))
        images.push(new URL(request.url()))
    })
    await page.route('**/__discovery-image-test', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<!doctype html><html><head><meta charset="utf-8"></head><body><div id="app"></div><script type="module">
import {createApp,h,ref} from '/node_modules/.vite/deps/vue.js?v=${browserHash}';
import {createPinia} from '/node_modules/.vite/deps/pinia.js?v=${browserHash}';
import {createRouter,createMemoryHistory} from '/node_modules/.vite/deps/vue-router.js?v=${browserHash}';
import RecommendationCard from '/src/features/recommendations/components/RecommendationCard.vue';
import ExternalCard from '/src/features/external-search/components/ExternalSearchCard.vue';
import {useSessionStore} from '/src/features/auth/stores/session.js';
import {useMembershipsStore} from '/src/features/library/stores/memberships.js';
import {recommendationApi,externalSearchApi} from '/src/api/index.js';
import '/src/styles/main.css';
const pinia=createPinia(),session=useSessionStore(pinia);await session.initialize();useMembershipsStore(pinia).reset(session.identity);
const recommendation=await recommendationApi.getJob('${fixture.job_id}');
const response=await externalSearchApi.getJob('${fixture.task_id}','${fixture.token}');
const rec=ref(recommendation.data.result.items[0]),raw=response.data.result.data.external_results[0],search=ref({...raw,title:raw.source_title,cover_url:raw.thumbnail_url});
window.imageAudit={rec,search};
const app=createApp({render:()=>h('main',{class:'p-6 grid grid-cols-1 md:grid-cols-2 gap-6'},[h(RecommendationCard,{item:rec.value}),h(ExternalCard,{item:search.value})])});
app.use(pinia).use(createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{render:()=>null}}]})).mount('#app');
</script></body></html>`,
      })
    )
    await page.goto(origin + '/__discovery-image-test')
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll('img')].filter(
          (img) => img.complete && img.naturalWidth === 320
        ).length === 2
    )
    assert.equal(images.length, 2)
    assert.ok(images.every((url) => url.searchParams.has('handle') && !url.searchParams.has('url')))
    const recUrl = new URL(
      await page.locator('.recommendation-card img').getAttribute('src'),
      origin
    )
    const searchUrl = new URL(
      await page.locator('.external-search-card img').getAttribute('src'),
      origin
    )
    const csrf = (await context.cookies()).find((cookie) => cookie.name === 'csrftoken').value
    const bad = await page.request.get(
      origin +
        '/nassav/api/recommendations/cover?url=https%3A%2F%2Fassets-cdn.jable.tv%2Fother.png&source=jable'
    )
    assert.equal(bad.status(), 400)
    for (const url of images) {
      const response = await page.request.get(url.href)
      assert.equal(response.status(), 200)
      assert.equal(response.headers()['cache-control'], 'private, no-store')
      assert.match(response.headers()['content-type'], /image\/png/)
    }
    await page.evaluate(() => {
      window.imageAudit.rec.value = { ...window.imageAudit.rec.value, cover_handle: undefined }
      window.imageAudit.search.value = {
        ...window.imageAudit.search.value,
        cover_handle: undefined,
      }
    })
    await page.waitForFunction(() => document.querySelectorAll('img').length === 0)
    assert.equal(images.length, 2, 'Missing handles must not fall back to URL requests')
    execFileSync('redis-cli', [
      '-s',
      join(dirname(fixturePath), 'redis.sock'),
      'DEL',
      'nassav:search:job:' + fixture.task_id,
    ])
    assert.equal((await page.request.get(searchUrl.href)).status(), 404)
    const reset = await page.request.post(origin + '/nassav/api/recommendations/reset', {
      headers: { 'X-CSRFToken': csrf },
      data: { preserve_blocklist: true },
    })
    assert.equal(reset.status(), 200)
    assert.equal((await page.request.get(recUrl.href)).status(), 404)
    assert.deepEqual(errors, [])
    console.log(
      'Native owned recommendation/search image HTTP, production cards, expiry/reset and no URL fallback checks passed'
    )
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
