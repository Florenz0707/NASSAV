const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { browserHash } = JSON.parse(readFileSync('node_modules/.vite/deps/_metadata.json', 'utf8'))
async function main() {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage(),
      errors = [],
      deletes = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/nassav/api/**', (route) => {
      if (route.request().method() === 'DELETE') deletes.push(route.request().url())
      return route.fulfill({ json: { code: 200, data: {} } })
    })
    await page.route('**/__actions-audit', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<html><body><div id="app"></div><script type="module">
import {createApp,h} from '/node_modules/.vite/deps/vue.js?v=${browserHash}';
import {createPinia} from '/node_modules/.vite/deps/pinia.js?v=${browserHash}';
import {createRouter,createWebHistory} from '/node_modules/.vite/deps/vue-router.js?v=${browserHash}';
import Card from '/src/features/resources/components/ResourceCard.vue';
import '/src/styles/main.css';
const router=createRouter({history:createWebHistory(),routes:[{path:'/:pathMatch(.*)*',component:{render:()=>null}}]});
createApp({render:()=>h('div',{style:'padding:240px 40px;display:flex;gap:24px'},[1,2].map(i=>h('div',{'data-card':i,style:'width:400px'},[h(Card,{resource:{avid:'SAME-1',has_video:true,original_title:'Same resource'}})])))}).use(createPinia()).use(router).mount('#app');
</script></body></html>`,
      })
    )
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    await page.goto(origin + '/__actions-audit')
    const first = page.locator('[data-card="1"]'),
      second = page.locator('[data-card="2"]')
    await second.getByRole('button', { name: '刷新资源', exact: true }).click()
    await second.getByRole('menuitem', { name: '全部刷新', exact: true }).waitFor()
    assert.equal(await first.getByRole('menu').count(), 0)
    await page.keyboard.press('ArrowDown')
    assert.equal(
      await second
        .getByRole('menuitem', { name: '仅M3U8', exact: true })
        .evaluate((el) => el === document.activeElement),
      true
    )
    await page.keyboard.press('Escape')
    assert.equal(
      await second
        .getByRole('button', { name: '刷新资源', exact: true })
        .evaluate((el) => el === document.activeElement),
      true
    )
    await first.getByRole('button', { name: '删除', exact: true }).click()
    await first.getByRole('menuitem', { name: '删除视频', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: '确认删除', exact: true }).click()
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'))
    assert.equal(deletes.length, 1)
    assert.deepEqual(errors, [])
    console.log(
      'PASS: same-AVID menus are instance scoped, keyboard focus returns and deletion makes one request'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
