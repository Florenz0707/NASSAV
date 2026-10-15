// Real loopback HTTP/SQLite + dedicated disposable keyring, no source-site requests.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const storageState = process.env.NASSAV_CREDENTIAL_STORAGE_STATE
  const secondState = process.env.NASSAV_CREDENTIAL_SECOND_STATE
  if (!storageState || !secondState) {
    console.log('SKIP: disposable scoped-credential sessions required')
    return
  }
  for (const path of [storageState, secondState])
    assert.ok(path.startsWith('/tmp/nassav-local-playback-http-'))
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4186'
  assert.equal(new URL(origin).hostname, '127.0.0.1')
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium
      ? { executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome' }
      : {}
  )
  const timeout = setTimeout(() => {
    console.error('Credential UI acceptance timed out')
    process.exitCode = 1
    void browser.close()
  }, 120000)
  try {
    for (const theme of ['dark', 'light']) {
      const context = await browser.newContext({ storageState })
      const other = await browser.newContext({ storageState: secondState })
      const api = origin + '/nassav/api'
      const headers = async (target = context) => ({
        'X-CSRFToken': (await target.cookies(origin)).find((c) => c.name === 'csrftoken').value,
      })
      try {
        const initial = (await (await context.request.get(api + '/auth/session')).json()).data
        assert.equal(initial.capabilities.personal_source_credentials, true)
        assert.equal(
          (
            await context.request.put(api + '/setting', {
              data: { color_mode: theme },
              headers: await headers(),
            })
          ).status(),
          200
        )
        const page = await context.newPage(),
          errors = [],
          legacy = []
        page.setDefaultTimeout(15000)
        page.on('pageerror', (error) => errors.push(error.message))
        page.on('request', (request) => {
          if (new URL(request.url()).pathname.endsWith('/source/cookie')) legacy.push(request.url())
        })
        await page.goto(origin + '/add', { waitUntil: 'domcontentloaded' })
        const avid = page.getByLabel('视频编号 (AVID)', { exact: false })
        await avid.fill('P7-COOKIE')
        await page.getByRole('button', { name: 'Cookie 设置', exact: true }).click()
        const dialog = page.getByRole('dialog', { name: '个人来源凭证', exact: true })
        await dialog.waitFor()
        await dialog.locator('#credential-source').click()
        await page.getByRole('option', { name: 'Jable', exact: true }).click()
        const cookie = dialog.getByLabel('新的 Cookie', { exact: true })
        await dialog.getByRole('button', { name: '保存', exact: true }).click()
        assert.equal(await cookie.getAttribute('aria-invalid'), 'true')
        await cookie.fill(`account_session=ui-${theme}-first; cf_clearance=ui-test`)
        await dialog.getByRole('button', { name: '保存', exact: true }).click()
        assert.equal(
          await dialog.getByLabel('配套 User-Agent', { exact: true }).getAttribute('aria-invalid'),
          'true'
        )
        assert.equal(await cookie.getAttribute('aria-invalid'), null)
        const userAgent = await page.evaluate(() => navigator.userAgent)
        await dialog.getByLabel('配套 User-Agent', { exact: true }).fill(userAgent)
        await dialog.getByRole('button', { name: '保存', exact: true }).click()
        await dialog.getByRole('status').filter({ hasText: '个人凭证已保存' }).waitFor()
        assert.equal(await cookie.inputValue(), '')
        assert.equal(await avid.inputValue(), 'P7-COOKIE')
        const saved = (
          await (await context.request.get(api + '/me/source-credentials')).json()
        ).data.find((row) => row.source_name === 'jable')
        assert.ok(saved && !JSON.stringify(saved).includes('ui-test'))
        const changed = (await (await context.request.get(api + '/auth/session')).json()).data
        assert.equal(changed.cache_identity, initial.cache_identity)
        assert.notEqual(changed.source_cache_identity, initial.source_cache_identity)
        const conflict = await other.request.put(`${api}/me/source-credentials/${saved.id}`, {
          data: {
            expected_version: saved.version,
            cookie: 'account_session=ui-second-device',
            user_agent: userAgent,
            kind: 'account',
          },
          headers: await headers(other),
        })
        assert.equal(conflict.status(), 200)
        const draft = 'account_session=ui-preserved-draft'
        await cookie.fill(draft)
        await dialog.getByLabel('配套 User-Agent', { exact: true }).fill(userAgent)
        await dialog.getByRole('button', { name: '保存', exact: true }).click()
        await dialog.getByText('凭证版本已变化，请重新加载并确认后保存', { exact: true }).waitFor()
        assert.equal(await cookie.inputValue(), draft)
        await dialog.getByRole('button', { name: '重新加载', exact: true }).click()
        await dialog
          .locator('dl dd')
          .nth(2)
          .filter({ hasText: String(saved.version + 1) })
          .waitFor()
        assert.equal(await cookie.inputValue(), draft)
        await dialog.getByRole('button', { name: '保存', exact: true }).click()
        await dialog.getByRole('status').filter({ hasText: '个人凭证已保存' }).waitFor()
        assert.equal(await cookie.inputValue(), '')
        await cookie.fill('account_session=unsaved-demo')
        await page.keyboard.press('Escape')
        const discard = page.getByRole('dialog', { name: '尚未保存', exact: true })
        await discard.waitFor()
        await discard.getByRole('button', { name: '取消', exact: true }).click()
        assert.equal(await cookie.inputValue(), 'account_session=unsaved-demo')
        await page.keyboard.press('Escape')
        await discard.getByRole('button', { name: '放弃并关闭', exact: true }).click()
        await dialog.waitFor({ state: 'hidden' })
        assert.equal(await avid.inputValue(), 'P7-COOKIE')
        await page.setViewportSize({ width: 390, height: 844 })
        await page.getByRole('button', { name: 'Cookie 设置', exact: true }).click()
        await dialog.waitFor()
        await dialog.locator('#credential-source').click()
        await page.getByRole('option', { name: 'Jable', exact: true }).click()
        await cookie.waitFor()
        assert.equal(await cookie.inputValue(), '')
        await dialog.getByRole('button', { name: '撤销', exact: true }).click()
        const revoke = page.getByRole('dialog', { name: '撤销个人凭证', exact: true })
        await revoke.getByRole('button', { name: '撤销', exact: true }).click()
        await dialog.getByRole('status').filter({ hasText: '个人凭证已撤销' }).waitFor()
        assert.equal(
          await dialog.getByRole('button', { name: '撤销', exact: true }).isDisabled(),
          true
        )
        const rectangle = await dialog.boundingBox()
        assert.ok(rectangle.y >= 0 && rectangle.y + rectangle.height <= 844)
        await dialog.getByRole('button', { name: '关闭', exact: true }).click()
        assert.deepEqual(legacy, [])
        assert.deepEqual(errors, [])
        const stored = await page.evaluate(() =>
          JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)])
        )
        assert.ok(!stored.includes('account_session='))
        console.log(
          `PASS: ${theme} real blind write/CAS/revoke, nested dialogs, mobile and form preservation`
        )
      } finally {
        await context.close()
        await other.close()
      }
    }
  } finally {
    clearTimeout(timeout)
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
