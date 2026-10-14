// Layout-only regression with simulated APIs; does not use deployed services.
const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
async function main() {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium
      ? { executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome' }
      : {}
  )
  const page = await browser.newPage(),
    errors = []
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4180'
  assert.equal(new URL(origin).hostname, '127.0.0.1')
  await page.routeWebSocket('**/nassav/ws/**', () => {})
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/nassav/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    let data = []
    if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'layout-audit' }
    if (path.endsWith('/setting')) data = { color_mode: 'dark', playback_volume: 0.8 }
    return route.fulfill({
      json: { code: 200, data, pagination: { page: 1, pages: 1, page_size: 15, total: 0 } },
    })
  })
  const navigation = page.getByRole('navigation', { name: '个人中心功能' })
  const boxes = () =>
    navigation.evaluate((node) =>
      [...node.querySelectorAll('button')].map((button) => {
        const { x, y, width, height } = button.getBoundingClientRect()
        return { x, y, width, height }
      })
    )
  function same(before, after, label) {
    assert.equal(before.length, after.length)
    for (let i = 0; i < before.length; i++)
      for (const key of ['x', 'y', 'width', 'height'])
        assert.ok(
          Math.abs(before[i][key] - after[i][key]) < 1,
          `${label}: button ${i} ${key}: ${before[i][key]} -> ${after[i][key]}`
        )
  }
  try {
    await page.bringToFront()
    for (const width of [1440, 1024, 390, 320]) {
      await page.setViewportSize({ width, height: 800 })
      await page.goto(`${origin}/personal/history`, { waitUntil: 'domcontentloaded' })
      await page.getByText('暂无观看历史', { exact: true }).waitFor()
      await page.evaluate(() => document.fonts.ready)
      await page.waitForTimeout(350)
      const baseline = await boxes()
      assert.equal(
        await page.evaluate(() => getComputedStyle(document.documentElement).scrollbarGutter),
        'stable'
      )
      for (const section of ['通用设置', '观看历史', '播放设置']) {
        const sample = navigation.evaluate(async (node) => {
          const frames = [],
            end = performance.now() + 450
          while (performance.now() < end) {
            frames.push(
              [...node.querySelectorAll('button')].map((button) => {
                const { x, y, width, height } = button.getBoundingClientRect()
                return { x, y, width, height }
              })
            )
            await new Promise(requestAnimationFrame)
          }
          return frames
        })
        const [frames] = await Promise.all([
          sample,
          navigation.getByRole('button', { name: section, exact: true }).click(),
        ])
        await page.getByRole('heading', { name: section, exact: true }).waitFor()
        for (const frame of frames) same(baseline, frame, `${width}px ${section} transition`)
        same(baseline, await boxes(), `${width}px ${section}`)
        if (section === '通用设置') {
          await navigation.getByRole('button', { name: '退出登录', exact: true }).click()
          const dialog = page.getByRole('dialog', { name: '退出登录', exact: true })
          await dialog.waitFor()
          same(baseline, await boxes(), `${width}px modal scroll lock`)
          await dialog.getByRole('button', { name: '取消', exact: true }).click()
          await dialog.waitFor({ state: 'hidden' })
          same(baseline, await boxes(), `${width}px modal closed`)
        }
      }
      const slider = page.getByLabel('默认音量', { exact: true })
      const fixed = await slider.boundingBox()
      for (const value of [0, 0.09, 0.1, 0.99, 1]) {
        await slider.evaluate((node, value) => {
          node.value = String(value)
          node.dispatchEvent(new Event('input', { bubbles: true }))
        }, value)
        const percent = `${Math.round(value * 100)}%`
        await page.waitForFunction(
          (text) =>
            document.querySelector('#playback-volume').getAttribute('aria-valuetext') === text,
          percent
        )
        const box = await slider.boundingBox()
        same([fixed], [box], `${width}px volume ${percent}`)
        assert.equal(
          (await page.locator('output[for="playback-volume"]').innerText()).replace(/\s/g, ''),
          percent
        )
      }
      assert.ok(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `${width}px overflow`
      )
      if (width === 1440 || width === 390) {
        await page.screenshot({
          path: `/tmp/nassav-layout-${engine.name()}-${width}.png`,
          fullPage: true,
          animations: 'disabled',
        })
      }
    }
    assert.deepEqual(errors, [])
    console.log(
      'PASS simulated API: stable navigation during panel transitions and 0/9/10/99/100% slider at 1440/1024/390/320px'
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
