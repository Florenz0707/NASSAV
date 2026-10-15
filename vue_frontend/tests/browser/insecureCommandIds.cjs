const { chromium, firefox } = require('playwright')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const assert = require('node:assert/strict')
;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  try {
    const page = await browser.newPage()
    const source = readFileSync(join(__dirname, '../../src/shared/lib/requestId.js'), 'utf8')
    await page.route('http://nassav-insecure.test/**', (route) =>
      route.fulfill(
        new URL(route.request().url()).pathname === '/requestId.js'
          ? { contentType: 'text/javascript', body: source }
          : {
              contentType: 'text/html',
              body: `<!doctype html><html><body><script type="module">import {createRequestId} from '/requestId.js';window.commandIds={secure:isSecureContext,native:typeof crypto.randomUUID,ids:Array.from({length:200},()=>createRequestId())};</script></body></html>`,
            }
      )
    )
    await page.goto('http://nassav-insecure.test/')
    await page.waitForFunction(() => Boolean(window.commandIds))
    const result = await page.evaluate(() => window.commandIds)
    assert.equal(result.secure, false)
    assert.equal(result.native, 'undefined')
    assert.equal(new Set(result.ids).size, 200)
    assert.ok(
      result.ids.every((id) =>
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)
      )
    )
    console.log('Native insecure HTTP WebCrypto command UUID fallback passed; no external requests')
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
