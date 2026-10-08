// Render production components with isolated sample data; never use a real backend.
const { chromium } = require('playwright')
const { mkdirSync } = require('node:fs')
const { join } = require('node:path')
const assert = require('node:assert/strict')

const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4178'
assert(
  ['localhost', '127.0.0.1', '[::1]'].includes(new URL(origin).hostname),
  'Use a loopback Vite server'
)
const output = join(__dirname, '../public/preview')
const titles = [
  '雨后森林的清晨',
  '山间来信',
  '暮色中的海岸',
  '城市夜行',
  '海边的一日',
  '沿着溪流走向远方',
]
const actors = [
  '青山 凛',
  '水野 遥',
  '小林 花',
  '森川 澪',
  '白石 葵',
  '星野 凪',
  '浅野 杏',
  '桐谷 光',
  '松本 泉',
  '高桥 诗',
  '夏目 月',
  '铃木 樱',
  '中村 雪',
  '藤原 岚',
  '秋山 叶',
].map((name, i) => ({ id: i + 1, name, is_blocked: i === 8 || i === 10, resource_count: 24 - i }))
const genres = [
  '剧情',
  '旅行',
  '日常',
  '自然',
  '城市',
  '纪实',
  '海岸',
  '音乐',
  '运动',
  '艺术',
  '四季',
  '美食',
  '建筑',
  '生活',
  '风景',
].map((name, i) => ({ id: i + 1, name, resource_count: 38 - i * 2 }))
const resources = titles.map((title, i) => ({
  avid: `DEMO-${String(i + 1).padStart(3, '0')}`,
  source_title: title,
  original_title: title,
  source: i % 2 ? 'MissAV' : 'Jable',
  date: `2026-09-${String(18 + i).padStart(2, '0')}`,
  duration: '01:48:00',
  release_date: '2026-09-18',
  actors: actors.slice(0, 2).map((item) => item.name),
  genres: genres.slice(0, 3).map((item) => item.name),
  has_video: i === 4,
  downloaded: i === 4,
  file_exists: i === 4,
  is_favorite: i === 0,
  watched: i === 4,
  studio: '示例制作团队',
  label: '旅行影像',
  director: '示例导演',
  series: '四季日记',
}))
const remoteItems = resources.map((item, i) => ({
  ...item,
  avid: `DEMO-${String(i + 21).padStart(3, '0')}`,
  title: item.source_title,
  cover_url: `https://preview.invalid/cover/${i}`,
  thumbnail_url: `https://preview.invalid/cover/${i}`,
  url: `https://preview.invalid/video/${i}`,
  in_library: i === 2,
  detail_cached: i < 3,
  score: 86.4 - i * 2,
  reasons: ['来自偏好的演员与类别', '尚未加入资源库'],
  raw_metrics: { duration: '01:48:00', views: 18200 + i * 1200, likes: 430 + i * 25 },
}))
const baseTime = 1791441000
const tasks = ['running', 'running', 'paused', 'succeeded', 'failed', 'queued'].map((state, i) => ({
  job_id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`,
  task_id: `preview-attempt-${i}`,
  job_type: i % 2 ? 'scrape' : 'download',
  avid: resources[i].avid,
  action: 'add',
  version: 3,
  state,
  stage: i === 1 ? 'translation_translating' : state === 'running' ? 'video_download' : state,
  created_at: baseTime - i * 120,
  updated_at: baseTime - i * 60,
  resource: resources[i],
  resource_saved: i !== 5,
  resource_avid: i !== 5 ? resources[i].avid : null,
  allowed_actions:
    state === 'running' || state === 'queued'
      ? ['pause', 'cancel']
      : state === 'paused'
        ? ['resume', 'cancel']
        : [],
  cleanup_state: state === 'failed' ? 'completed' : 'not_required',
  message: state === 'failed' ? '来源请求超时，已有资源未覆盖' : '',
  progress:
    i === 0 ? { percent: 45, speed: '5.2 MB/s', downloaded: '452 MB', total: '1 GB' } : null,
  translation:
    i === 1
      ? { state: 'translating' }
      : i === 3
        ? { state: 'completed', completed_at: baseTime - 180 }
        : {},
  timeline: [
    { stage: 'queued', at: baseTime - 300 - i * 60 },
    { stage: 'running', at: baseTime - 240 - i * 60 },
    { stage: i === 1 ? 'resource_saved' : 'video_download', at: baseTime - 180 - i * 60 },
  ],
}))

function artwork(index = 0, avatar = false) {
  const palettes = [
    ['#203b43', '#589d97', '#eba8a0'],
    ['#2d3950', '#7285a2', '#db9b91'],
    ['#453347', '#a77b98', '#dfb4bd'],
  ]
  const [bg, mid, accent] = palettes[index % palettes.length]
  if (avatar)
    return `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240"><rect width="240" height="240" rx="120" fill="${bg}"/><circle cx="120" cy="90" r="38" fill="${accent}"/><path d="M44 230c0-102 152-102 152 0" fill="${mid}"/></svg>`
  return `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450"><defs><linearGradient id="sky" x2="1" y2="1"><stop stop-color="${bg}"/><stop offset="1" stop-color="${mid}"/></linearGradient></defs><rect width="800" height="450" fill="url(#sky)"/><circle cx="605" cy="118" r="58" fill="${accent}"/><path d="M0 335 190 137 395 370 590 214 800 335V450H0Z" fill="${bg}" opacity=".65"/><path d="M0 410Q240 295 430 385T800 370V450H0Z" fill="${mid}" opacity=".7"/><text x="40" y="58" font-family="sans-serif" font-size="18" fill="white" opacity=".7">NASSAV · PREVIEW</text><text x="40" y="410" font-family="sans-serif" font-size="24" fill="white" letter-spacing="5">${['FOREST / 01', 'MOUNTAIN / 02', 'COAST / 03'][index % 3]}</text></svg>`
}

async function configure(page, theme) {
  await page.routeWebSocket('**/nassav/ws/**', () => {})
  await page.route('**/*', async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname
    if (url.origin !== new URL(origin).origin) return route.abort()
    if (!path.startsWith('/nassav/api/')) return route.continue()
    let data = [],
      pagination
    if (path.endsWith('/cover') || /\/actors\/\d+\/avatar$/.test(path)) {
      const avid = url.searchParams.get('avid') || url.searchParams.get('url') || ''
      const index = Number(avid.match(/\d+$/)?.[0] || 0)
      return route.fulfill({
        contentType: 'image/svg+xml',
        body: artwork(index, path.endsWith('/avatar')),
      })
    }
    if (path.endsWith('/auth/session')) data = { authenticated: true, username: 'preview' }
    else if (path.endsWith('/setting'))
      data = {
        color_mode: theme,
        enable_avatar: 'true',
        display_title: 'source_title',
        font_family: 'Mplus2',
        search_result_display_style: 'grid',
        default_external_search_source: 'jable',
      }
    else if (path.endsWith('/source/list')) data = ['Jable', 'MissAV']
    else if (path.endsWith('/source/search-capabilities'))
      data = ['jable', 'missav'].map((source) => ({
        source,
        label: source === 'jable' ? 'Jable' : 'MissAV',
        actor: true,
        genre: true,
        orderings: ['-views', 'views', '-likes', 'likes', '-latest', 'latest'],
      }))
    else if (path.endsWith('/actors') || path.endsWith('/genres')) {
      data = path.endsWith('/actors') ? actors : genres
      pagination = { page: 1, pages: 2, total: 30, page_size: 15 }
    } else if (/\/(actors|genres)\/\d+\/detail$/.test(path)) {
      data = { detail: actors[0], resources, external_results: [] }
      pagination = { page: 1, pages: 1, total: 6, page_size: 15 }
    } else if (path.endsWith('/resources')) {
      data = resources
      pagination = { page: 1, pages: 1, total: 6, page_size: 15 }
    } else if (path.endsWith('/resource/metadata') || /\/resource\/[^/]+\/preview$/.test(path))
      data =
        resources.find(
          (item) => item.avid === (url.searchParams.get('avid') || path.split('/').at(-2))
        ) || resources[0]
    else if (path.endsWith('/tasks/queue/status'))
      data = { active_tasks: [], pending_tasks: [], active_count: 0, pending_count: 0 }
    else if (path.endsWith('/tasks/jobs'))
      data = { jobs: tasks, pagination: { total: 6, has_more: false, page_size: 50 } }
    else if (/\/tasks\/jobs\/[^/]+$/.test(path))
      data = tasks.find((item) => path.endsWith(item.job_id))
    else if (path.endsWith('/recommendations/metrics'))
      data = {
        snapshot_count: 8,
        repeat_rate: 0.06,
        feedback_counts: { like: 12, dislike: 2 },
        avid_blocklist_count: 3,
      }
    else if (path.endsWith('/recommendations/jobs') || /\/recommendations\/jobs\/[^/]+$/.test(path))
      data = {
        job_id: 'preview-recommendation',
        version: 2,
        state: 'succeeded',
        allowed_actions: [],
        result: {
          items: remoteItems,
          seeds: [
            { seed_type: 'actor', value: actors[0].name, resource_count: 24 },
            { seed_type: 'actor', value: actors[1].name, resource_count: 18 },
            { seed_type: 'genre', value: '剧情', resource_count: 38 },
            { seed_type: 'genre', value: '旅行', resource_count: 22 },
          ],
          meta: {
            returned_count: 6,
            requested_count: 12,
            elapsed_seconds: 18.6,
            verification_context: {
              recalled_count: 24,
              detail_success_count: 10,
              blacklist_excluded_count: 2,
              unverified_count: 14,
              qualified_count: 6,
              detail_attempt_count: 10,
              detail_cache_hit_count: 4,
            },
          },
        },
      }
    else if (path.endsWith('/search/jobs') || /\/search\/jobs\/[^/]+$/.test(path))
      data = {
        task_id: 'preview-search',
        token: 'sample-token',
        state: 'succeeded',
        version: 2,
        pages_completed: 2,
        result: {
          data: {
            detail: actors[0],
            external_results: remoteItems,
            external_meta: {
              partial: false,
              fetch_pages: 2,
              source: 'jable',
              pages_completed: 2,
              detail_cache_hit_count: 3,
            },
          },
          pagination: { page: 1, pages: 1, total: 6, page_size: 15 },
        },
      }
    // All mutation endpoints except simulated job submission are forbidden.
    if (
      request.method() !== 'GET' &&
      !['/nassav/api/search/jobs', '/nassav/api/recommendations/jobs'].includes(path)
    )
      throw new Error(`Unexpected preview write: ${request.method()} ${path}`)
    await route.fulfill({
      json: { code: 200, message: 'success', data, ...(pagination ? { pagination } : {}) },
    })
  })
}

async function main() {
  mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.NASSAV_CHROMIUM_PATH })
  try {
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({
        viewport: { width: 1440, height: 1080 },
        deviceScaleFactor: 1,
        reducedMotion: 'reduce',
        timezoneId: 'Asia/Shanghai',
      })
      page.setDefaultTimeout(10000)
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      await configure(page, theme)
      async function capture(file) {
        await page.mouse.move(0, 0)
        await page.evaluate(async () => {
          await document.fonts.ready
          await Promise.all([...document.images].map((img) => img.decode().catch(() => {})))
        })
        assert(
          !(await page.locator('body').innerText()).includes('\"resource_count\"'),
          'Fixture objects must not appear as raw JSON'
        )
        await page.screenshot({
          path: join(output, `${file}.jpg`),
          type: 'jpeg',
          quality: 92,
          animations: 'disabled',
          fullPage: (await page.getByRole('dialog').count()) === 0,
        })
        console.log(`Captured ${file}.jpg`)
      }
      const pages =
        theme === 'light'
          ? [
              ['/', 'home', 'h1'],
              ['/resources', 'resource', '.library-grid > *'],
              ['/resources/actors', 'actors', '.actor-name'],
              ['/resources/genres', 'genres', '.genre-name'],
              ['/resource/DEMO-001', 'resourceDetail', 'h1'],
              ['/add', 'addResource', 'h1'],
              ['/downloads', 'downloads', 'tbody tr'],
              ['/settings', 'settings', 'h1'],
            ]
          : [['/downloads', 'tasksDark', 'tbody tr']]
      for (const [path, name, selector] of pages) {
        await page.goto(origin + path)
        await page.locator(selector).first().waitFor()
        if (name === 'addResource')
          await page.getByRole('textbox', { name: /视频编号/ }).fill('DEMO-001\nDEMO-002')
        await page.waitForTimeout(400)
        if (name === 'downloads' || name === 'tasksDark')
          await page
            .getByRole('button', { name: /查看任务明细/ })
            .first()
            .click()
        await capture(name)
        if (name === 'addResource') {
          await page.getByRole('button', { name: 'Cookie 设置', exact: true }).click()
          await page.getByRole('dialog').waitFor()
          await capture('cookies')
        }
      }
      if (theme === 'light') {
        await page.goto(origin + '/actors/1?tab=external')
        await page.getByRole('button', { name: '开始搜索', exact: true }).click()
        await page.locator('.external-search-card').first().waitFor()
        await capture('externalSearch')
        await page.goto(origin + '/recommendations')
        await page.getByRole('button', { name: '开始推荐', exact: true }).click()
        await page.locator('.recommendation-card').first().waitFor()
        await capture('recommendations')
        await page.getByRole('button', { name: '个性化', exact: true }).click()
        await page.getByRole('dialog').waitFor()
        await page.getByText('当前没有已屏蔽项。').waitFor({ state: 'hidden' })
        await page.getByRole('button', { name: '取消', exact: true }).first().waitFor()
        await capture('personalization')
      }
      assert.deepEqual(errors, [], 'Preview pages must render without JavaScript errors')
      await page.close()
    }
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
