const { chromium } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    const page = await browser.newPage()
    await page.route('**/__ux-controls', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<html><head><meta charset="utf-8"></head><body><div id="app"></div><script type="module">
import '/src/styles/main.css';
import {createApp,h,ref} from '/node_modules/.vite/deps/vue.js';
import Button from '/src/shared/ui/AppButton.vue';
import Input from '/src/shared/ui/AppInput.vue';

const busy=ref(false),value=ref(''),error=ref('');window.audit={busy,value,error};
createApp({setup:()=>()=>h('div',[
...['warm-primary','warm-neutral'].map(id=>h(Button,{id,variant:id.slice(5),tone:'warm',loading:busy.value},()=>id)),
...['primary','neutral','danger'].map(variant=>h(Button,{id:variant,variant,loading:busy.value},()=>variant)),
h(Button,{disabled:true},()=> 'disabled'),
h(Input,{label:'视频编号',placeholder:'例如 SNOS-317',class:'audit-field',modelValue:value.value,error:error.value,'onUpdate:modelValue':v=>value.value=v})
])}).mount('#app');</script></body></html>`,
      })
    )
    await page.goto(
      (process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178') + '/__ux-controls'
    )
    await page.locator('#primary').waitFor()
    for (const mode of ['dark', 'light']) {
      await page.evaluate((mode) => {
        document.body.className = mode + '-mode'
      }, mode)
      for (const variant of ['primary', 'neutral', 'danger', 'warm-primary', 'warm-neutral']) {
        const button = page.locator('#' + variant)
        for (const state of ['default', 'hover', 'pressed']) {
          if (state === 'default') await page.mouse.move(900, 700)
          else await button.hover()
          if (state === 'pressed') await page.mouse.down()
          await page.waitForTimeout(180)

          const contrast = await button.evaluate((el) => {
            const s = getComputedStyle(el),
              rgb = (v) =>
                v
                  .match(/[\d.]+/g)
                  .slice(0, 3)
                  .map(Number)
            const lum = (c) =>
              c
                .map((v) => v / 255)
                .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
                .reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0)
            const a = lum(rgb(s.color)),
              b = lum(rgb(s.backgroundColor))
            return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
          })
          assert.ok(contrast >= 4.5, `${mode}/${variant}/${state}: ${contrast}`)
          if (state === 'pressed') await page.mouse.up()
        }
      }
    }
    const before = await page.locator('#primary').boundingBox()
    await page.evaluate(() => {
      window.audit.busy.value = true
    })
    await page.locator('#primary[aria-busy="true"]').waitFor()
    const after = await page.locator('#primary').boundingBox()
    assert.equal(after.width, before.width)
    assert.equal(after.height, before.height)
    assert.equal(await page.locator('#primary').isDisabled(), true)
    assert.equal(
      await page
        .locator('#primary .spinner')
        .evaluate((el) => getComputedStyle(el).animationDuration),
      '1.5s'
    )
    const input = page.getByRole('textbox', { name: '视频编号', exact: true })
    await input.fill('SNOS-317')
    await page.getByRole('button', { name: '清空视频编号' }).click()
    assert.equal(await input.inputValue(), '')
    assert.equal(await input.evaluate((el) => el === document.activeElement), true)
    assert.equal(await page.locator('.audit-field > .ui-field__control').count(), 1)
    await page.evaluate(() => {
      window.audit.error.value = '请输入有效编号'
    })
    await page.getByRole('alert').waitFor()
    assert.equal(await input.getAttribute('aria-invalid'), 'true')
    assert.ok(await input.getAttribute('aria-describedby'))
    await page.emulateMedia({ reducedMotion: 'reduce' })
    assert.equal(
      await page.locator('#primary .spinner').evaluate((el) => getComputedStyle(el).animationName),
      'none'
    )
    console.log(
      'PASS: button contrast in both themes/states, stable loading geometry, input clear/focus/error, reduced motion'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
