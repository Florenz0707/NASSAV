// Requires Playwright on NODE_PATH and a local Vite server; no backend is used.
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
const executablePath = process.env.NASSAV_CHROMIUM_PATH

async function main() {
  const browser = await chromium.launch({ executablePath, headless: true })
  try {
    const page = await browser.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/__component-audit', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<html><body style="overflow:scroll"><div id="app"></div><script type="module">
import {createApp,h,ref} from '/node_modules/.vite/deps/vue.js';
import Select from '/src/components/CustomSelect.vue';
import Confirm from '/src/components/ConfirmDialog.vue';
import Modal from '/src/components/settings/SettingsModal.vue';
import '/src/styles/main.css';
const show=ref(true),mount=ref(true),modal=ref(false),value=ref('a');
window.audit={show,mount,modal,value};
createApp({setup:()=>()=>h('div',[
 h('button',{id:'opener',onClick:()=>show.value=true},'Open'),
 h(Select,{'aria-label':'Audit selector',id:'audit-select',options:[{value:'disabled',label:'Disabled',disabled:true},{value:'a',label:'Alpha'},{value:'b',label:'Beta'},{value:'blocked',label:'Blocked',disabled:true},{value:'c',label:'Gamma'}],modelValue:value.value,'onUpdate:modelValue':v=>value.value=v}),
 mount.value?h(Confirm,{show:show.value,title:'Confirm audit',message:'Example','onUpdate:show':v=>show.value=v}):null,
 h(Modal,{show:modal.value,title:'Modal audit',onClose:()=>modal.value=false},{default:()=>h('input',{'aria-label':'Modal input'})})
])}).mount('#app');
</script></body></html>`,
      })
    )
    await page.goto(`${origin}/__component-audit`)
    await page.getByRole('dialog', { name: 'Confirm audit' }).waitFor()
    assert.equal(await page.evaluate(() => document.body.style.overflow), 'hidden')
    await page.keyboard.press('Escape')
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    assert.equal(await page.evaluate(() => document.body.style.overflow), 'scroll')
    await page.locator('#opener').click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: '确认', exact: true }).focus()
    await page.keyboard.press('Tab')
    assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), '取消')
    await page.keyboard.press('Shift+Tab')
    assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), '确认')
    await page.evaluate(() => {
      window.audit.modal.value = true
    })
    await page.getByRole('dialog', { name: 'Modal audit' }).waitFor()
    const ids = await page
      .getByRole('dialog')
      .evaluateAll((dialogs) => dialogs.map((d) => d.getAttribute('aria-labelledby')))
    assert.equal(new Set(ids).size, 2)
    await page.keyboard.press('Escape')
    await page.getByRole('dialog', { name: 'Modal audit' }).waitFor({ state: 'hidden' })
    assert.equal(await page.evaluate(() => document.body.style.overflow), 'hidden')
    await page.keyboard.press('Escape')
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    assert.equal(await page.evaluate(() => document.activeElement.id), 'opener')
    await page.locator('#opener').click()
    await page.evaluate(() => {
      window.audit.mount.value = false
    })
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    assert.equal(await page.evaluate(() => document.body.style.overflow), 'scroll')
    const select = page.getByRole('button', { name: 'Audit selector' })
    assert.equal(await select.getAttribute('id'), 'audit-select')
    await select.focus()
    await page.keyboard.press('ArrowDown')
    assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), 'Alpha')
    await page.keyboard.press('ArrowDown')
    assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), 'Beta')
    await page.keyboard.press('ArrowDown')
    assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), 'Gamma')
    await page.keyboard.press('Home')
    await page.keyboard.press('Enter')
    assert.equal(await page.evaluate(() => window.audit.value.value), 'a')
    assert.equal(await select.getAttribute('aria-expanded'), 'false')
    assert.deepEqual(errors, [])
    console.log(
      'PASS: dialog initial open, focus trap/return, nested locks, unmount, disabled select navigation and ARIA'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
