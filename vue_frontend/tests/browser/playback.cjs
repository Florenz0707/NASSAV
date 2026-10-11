const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { mkdtempSync, readFileSync, rmSync } = require('node:fs')
const { tmpdir } = require('node:os')
const { join } = require('node:path')
const { spawnSync } = require('node:child_process')
const {
  installMediaDiagnostics,
  readMediaDiagnostics,
} = require('../../scripts/lib/media-diagnostics.cjs')
const { browserHash } = JSON.parse(readFileSync('node_modules/.vite/deps/_metadata.json', 'utf8'))
async function main() {
  const fixture = mkdtempSync(join(tmpdir(), 'nassav-hls-fixture-'))
  let browser, auditPage
  try {
    for (const format of ['mpegts', 'fmp4']) {
      const result = spawnSync(
        'ffmpeg',
        [
          '-hide_banner',
          '-loglevel',
          'error',
          '-f',
          'lavfi',
          '-i',
          'testsrc2=size=320x180:rate=24',
          '-f',
          'lavfi',
          '-i',
          'sine=frequency=440:sample_rate=44100',
          '-t',
          '120',
          '-c:v',
          'libx264',
          '-preset',
          'ultrafast',
          '-pix_fmt',
          'yuv420p',
          '-g',
          '48',
          '-c:a',
          'aac',
          '-b:a',
          '64k',
          '-f',
          'hls',
          '-hls_time',
          '2',
          '-hls_list_size',
          '0',
          '-hls_segment_type',
          format,
          '-hls_segment_filename',
          join(fixture, `${format}-%d.${format === 'fmp4' ? 'm4s' : 'ts'}`),
          '-hls_fmp4_init_filename',
          'init.mp4',
          join(fixture, `${format}.m3u8`),
        ],
        { encoding: 'utf8' }
      )
      assert.equal(result.status, 0, result.stderr)
    }
    const engine = process.env.NASSAV_BROWSER_ENGINE || 'chromium'
    assert.ok(['chromium', 'firefox'].includes(engine))
    browser = await (engine === 'firefox' ? firefox : chromium).launch(
      engine === 'firefox'
        ? {}
        : {
            executablePath: process.env.NASSAV_CHROMIUM_PATH || '/bin/google-chrome',
            args: ['--disable-features=LocalNetworkAccessChecks'],
          }
    )
    const page = await browser.newPage(),
      errors = [],
      closed = [],
      sessions = new Map()
    auditPage = page
    await installMediaDiagnostics(page)
    let serial = 0,
      format = 'mpegts',
      fail = false,
      delayed = false,
      releaseSubmit,
      outage = false,
      refreshes = 0
    await page.addInitScript(() => {
      const original = HTMLMediaElement.prototype.canPlayType
      HTMLMediaElement.prototype.canPlayType = function (type) {
        return type.includes('mpegurl') ? '' : original.call(this, type)
      }
    })
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/nassav/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (/\/media\//.test(path)) {
        if (
          outage &&
          path.includes('/media/g1/') &&
          Number(path.match(/-(\d+)\.ts$/)?.[1] || 0) >= 40
        )
          return route.fulfill({
            status: 410,
            json: { code: 410, message: 'source_access_failed' },
          })
        const name = path.split('/').at(-1)
        const body = readFileSync(join(fixture, name))
        return route.fulfill({
          body,
          contentType: name.endsWith('m3u8')
            ? 'application/vnd.apple.mpegurl'
            : 'application/octet-stream',
        })
      }
      if (route.request().method() === 'POST' && path.endsWith('/playback-sessions')) {
        const id = `fixture-${++serial}`
        sessions.set(id, { session_id: id, state: 'queued', generation: 1, version: 1 })
        if (delayed)
          await new Promise((resolve) => {
            releaseSubmit = resolve
          })
        return route.fulfill({ status: 202, json: { code: 202, data: sessions.get(id) } })
      }
      const id = path.split('/')[4]
      if (path.endsWith('/refresh')) {
        refreshes++
        sessions.set(id, {
          ...sessions.get(id),
          generation: 2,
          refresh_count: 1,
          version: 5,
          state: 'queued',
        })
        return route.fulfill({ status: 202, json: { code: 202, data: sessions.get(id) } })
      }
      if (path.endsWith('/close')) {
        closed.push(id)
        return route.fulfill({
          json: { code: 200, data: { ...sessions.get(id), state: 'closed', version: 4 } },
        })
      }
      return route.fulfill({
        json: {
          code: 200,
          data: {
            ...sessions.get(id),
            state: fail ? 'failed' : 'ready',
            error_code: 'preparation_failed',
            version: sessions.get(id).generation === 2 ? 6 : 3,
            manifest_url: `/nassav/api/playback-sessions/${id}/media/g${sessions.get(id).generation}/${format}.m3u8`,
          },
        },
      })
    })
    await page.route('**/__playback-audit', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<html><head><meta charset="UTF-8"></head><body><div id="app"></div><script type="module">
import {createApp,h,ref} from '/node_modules/.vite/deps/vue.js?v=${browserHash}';
import Player from '/src/features/playback/components/PlaybackPlayer.vue';
import '/src/styles/main.css';
createApp({setup(){const show=ref(false);return()=>h('div',[h('button',{onClick:()=>show.value=true},'打开播放器'),h('button',{onClick:()=>show.value=false},'停止播放'),h(Player,{active:show.value,avid:'DEMO-1'})])}}).mount('#app');
</script></body></html>`,
      })
    )
    const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
    await page.goto(origin + '/__playback-audit')
    await page.waitForTimeout(500)
    assert.deepEqual(errors, [])
    for (const mode of ['mpegts', 'fmp4']) {
      format = mode
      await page.getByRole('button', { name: '打开播放器' }).click()
      await page.locator('video').waitFor()
      await page.waitForFunction(() => !!document.querySelector('video')?.getAttribute('src'))
      await page.locator('video').evaluate((video) => video.play())
      await page.waitForFunction(() => document.querySelector('video')?.currentTime > 0.5)
      await page.locator('video').evaluate((video) => {
        video.currentTime = 7
      })
      await page.waitForFunction(() => document.querySelector('video').currentTime > 7.2)
      await page.locator('video').evaluate((video) => video.pause())
      assert.equal(await page.locator('video').evaluate((video) => video.paused), true)
      await page.getByRole('button', { name: '停止播放', exact: true }).click()
      await page.waitForFunction(() => !document.querySelector('video'))
      assert.equal(await page.evaluate(() => document.body.style.overflow), '')
    }
    format = 'mpegts'
    await page.getByRole('button', { name: '打开播放器' }).click()
    await page.locator('video').waitFor()
    await page.waitForFunction(() => !!document.querySelector('video')?.getAttribute('src'))
    await page.locator('video').evaluate((video) => video.play())
    await page.waitForFunction(() => document.querySelector('video')?.currentTime > 0.5)
    outage = true
    await page.locator('video').evaluate((video) => {
      video.currentTime = 90
    })
    await page.waitForFunction(() => document.querySelector('video')?.currentTime > 90.2, null, {
      timeout: 15000,
    })
    assert.equal(refreshes, 1, 'expired source should refresh exactly once and resume position')
    await page.getByRole('button', { name: '停止播放', exact: true }).click()
    outage = false
    fail = true
    await page.getByRole('button', { name: '打开播放器' }).click()
    await page.getByRole('alert').waitFor()
    fail = false
    await page.getByRole('button', { name: '重试播放' }).click()
    await page.locator('video').waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    assert.ok(
      await page
        .getByRole('region', { name: '视频播放器' })
        .evaluate((el) => el.getBoundingClientRect().width <= innerWidth)
    )
    await page.getByRole('button', { name: '停止播放', exact: true }).click()
    delayed = true
    await page.getByRole('button', { name: '打开播放器' }).click()
    await page.waitForTimeout(150)
    await page.getByRole('button', { name: '停止播放', exact: true }).click()
    releaseSubmit()
    await page.waitForTimeout(300)
    assert.ok(closed.includes(`fixture-${serial}`), 'late submit must be closed')
    assert.deepEqual(errors, [])
    console.log(
      'PASS: real TS/fMP4 H.264/AAC decode, seek, pause, stop, retry, mobile/dark, one-shot expired-source position recovery and late submit fencing'
    )
  } catch (error) {
    console.log(JSON.stringify({ media_diagnostics: await readMediaDiagnostics(auditPage) }))
    throw error
  } finally {
    await browser?.close()
    rmSync(fixture, { recursive: true, force: true })
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
