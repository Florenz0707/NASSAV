const { chromium, firefox } = require('playwright')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { dirname, join } = require('node:path')
const { randomUUID } = require('node:crypto')
;(async () => {
  const engine = process.env.NASSAV_BROWSER_ENGINE === 'firefox' ? firefox : chromium
  const browser = await engine.launch(
    engine === chromium ? { executablePath: '/bin/google-chrome' } : {}
  )
  const origin = process.env.NASSAV_BROWSER_ORIGIN || 'http://127.0.0.1:4188'
  assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/)
  const backendOrigin = process.env.NASSAV_BROWSER_BACKEND_ORIGIN || 'http://127.0.0.1:9794'
  assert.match(backendOrigin, /^http:\/\/127\.0\.0\.1:\d+$/)
  const fixturePath = process.env.NASSAV_MULTI_USER_FIXTURE
  assert.match(
    fixturePath || '',
    /^\/tmp\/nassav-local-playback-http-[^/]+\/multi-user-fixture\.json$/
  )
  const fixture = JSON.parse(readFileSync(fixturePath, 'utf8'))
  const secretA = 'account_session=fixture-a-' + randomUUID(),
    secretB = 'account_session=fixture-b-' + randomUUID()
  try {
    const a = await browser.newContext({
      storageState: join(dirname(fixturePath), 'storage-state.json'),
    })
    const b = await browser.newContext()
    async function request(context, identity, path, method = 'get', body, expected = 200) {
      const csrf = (await context.cookies()).find((cookie) => cookie.name === 'csrftoken')?.value
      const response = await context.request[method](origin + '/nassav/api' + path, {
        headers: {
          ...(identity ? { 'X-NASSAV-Context': identity.cache_identity } : {}),
          ...(csrf ? { 'X-CSRFToken': csrf } : {}),
        },
        ...(body ? { data: body } : {}),
      })
      assert.equal(response.status(), expected, `${method} ${path}`)
      return (await response.json()).data
    }
    async function login(context, username, password) {
      await request(context, null, '/auth/session')
      return request(context, null, '/auth/login', 'post', { username, password })
    }
    const admin = await request(a, null, '/auth/session')
    const member = await login(b, fixture.member_username, fixture.member_password)
    assert.equal(admin.capabilities.ordinary_login, true)
    assert.equal(admin.capabilities.app_admin, true)
    assert.equal(member.capabilities.app_admin, false)
    const pageA = await a.newPage(),
      pageB = await b.newPage()
    const errors = []
    for (const page of [pageA, pageB]) {
      page.setDefaultTimeout(20000)
      page.on('pageerror', (error) => errors.push(error.message))
    }
    await Promise.all([
      pageA.goto(origin + '/personal/general'),
      pageB.goto(origin + '/personal/general'),
    ])
    await pageA.getByRole('button', { name: '管理中心', exact: true }).waitFor()
    await pageB.getByRole('heading', { name: '个人中心', exact: true }).waitFor()
    assert.equal(await pageB.getByRole('button', { name: '管理中心', exact: true }).count(), 0)
    await request(a, admin, '/setting', 'put', { display_title: 'original_title' })
    await request(b, member, '/setting', 'put', { display_title: 'translated_title' })
    for (const [context, identity, cookie] of [
      [a, admin, secretA],
      [b, member, secretB],
    ]) {
      await request(context, identity, '/me/source-credentials', 'post', {
        source_name: 'jable',
        expected_version: 0,
        kind: 'account',
        cookie,
        user_agent: 'Nassav-isolated-user/1.0',
      })
    }
    const credentialsA = await request(a, admin, '/me/source-credentials'),
      credentialsB = await request(b, member, '/me/source-credentials')
    assert.equal(credentialsA.length, 1)
    assert.equal(credentialsB.length, 1)
    assert.notEqual(credentialsA[0].id, credentialsB[0].id)
    assert.ok(!JSON.stringify([credentialsA, credentialsB]).includes('account_session'))
    await request(
      b,
      member,
      '/me/source-credentials/' + credentialsA[0].id,
      'put',
      { expected_version: 1, kind: 'account', cookie: secretB, user_agent: 'fixture' },
      404
    )
    for (const path of [
      '/admin/users',
      '/admin/source-credentials',
      '/tasks/queue/status',
      '/source/cookie',
    ])
      await request(b, member, path, 'get', null, 403)
    assert.equal((await b.request.get(backendOrigin + '/admin/login/')).status(), 404)
    async function add(context, identity, avid, credential_mode, expected = 202) {
      return request(
        context,
        identity,
        '/library/entries',
        'post',
        {
          avid,
          action: 'add',
          kind: 'scrape',
          source: 'jable',
          credential_mode,
          request_id: randomUUID(),
        },
        expected
      )
    }
    const [publicA, publicB] = await Promise.all([
      add(a, admin, 'MULTI-UI', 'public'),
      add(b, member, 'MULTI-UI', 'public'),
    ])
    assert.notEqual(publicA.operation.operation_id, publicB.operation.operation_id)
    let jobs = (await request(a, admin, '/tasks/jobs')).jobs
    assert.equal(
      jobs.filter((row) => row.avid === 'MULTI-UI').length,
      1,
      'Public preparation must coalesce despite distinct personal cookies'
    )
    await add(b, member, 'MULTI-OVERLIMIT', 'public', 403)
    const ownB = await request(b, member, '/my-operations')
    const initialB = ownB.find((row) => row.avid === 'OPERATION-UI')
    async function cancel(context, identity, operation) {
      const current = await request(context, identity, '/my-operations/' + operation.operation_id)
      return request(
        context,
        identity,
        '/my-operations/' + operation.operation_id + '/cancel',
        'post',
        { expected_version: current.version, request_id: randomUUID() }
      )
    }
    await cancel(b, member, initialB)
    jobs = (await request(a, admin, '/tasks/jobs')).jobs
    assert.equal(
      jobs.find((row) => row.avid === 'OPERATION-UI').state,
      'queued',
      'Cancelling B must retain A demand'
    )
    const [privateA, privateB] = await Promise.all([
      add(a, admin, 'PRIVATE-UI', 'personal'),
      add(b, member, 'PRIVATE-UI', 'personal'),
    ])
    jobs = (await request(a, admin, '/tasks/jobs')).jobs
    assert.equal(
      jobs.filter((row) => row.avid === 'PRIVATE-UI').length,
      2,
      'Personal scopes must not share preparation'
    )
    await request(a, admin, '/my-operations/' + privateB.operation.operation_id, 'get', null, 404)
    await request(b, member, '/my-operations/' + privateA.operation.operation_id, 'get', null, 404)
    await cancel(a, admin, publicA.operation)
    jobs = (await request(a, admin, '/tasks/jobs')).jobs
    assert.equal(jobs.find((row) => row.avid === 'MULTI-UI').state, 'queued')
    await cancel(b, member, publicB.operation)
    jobs = (await request(a, admin, '/tasks/jobs')).jobs
    assert.equal(jobs.find((row) => row.avid === 'MULTI-UI').state, 'cancelled')
    // Freeze old-tab activity; only the next production client call triggers recheck.
    await pageA.evaluate(async () => {
      ;(await import('/src/app/stores/websocket.js')).useWebSocketStore().disconnect()
      ;(await import('/src/features/tasks/stores/userOperations.js'))
        .useUserOperationsStore()
        .reset()
    })
    const switched = await login(a, fixture.member_username, fixture.member_password)
    const count = { writes: 0 }
    pageA.on('request', (req) => {
      if (req.method() === 'PUT' && new URL(req.url()).pathname.endsWith('/setting')) count.writes++
    })
    const failed = await pageA.evaluate(async () => {
      const { default: api } = await import('/src/api/client.js')
      try {
        await api.put('/setting', { display_title: 'source_title' })
        return null
      } catch (error) {
        return error.code
      }
    })
    assert.equal(failed, 409)
    await pageA.waitForFunction(
      async (username) =>
        (await import('/src/features/auth/stores/session.js')).useSessionStore().username ===
        username,
      fixture.member_username
    )
    assert.equal(count.writes, 1, 'Context failure must not automatically replay the old mutation')
    assert.equal((await request(a, switched, '/setting')).display_title, 'translated_title')
    await request(a, admin, '/setting', 'get', null, 409)
    await request(a, admin, '/auth/logout', 'post', {}, 409)
    assert.equal((await request(a, null, '/auth/session')).authenticated, true)
    const wrongImage = await a.request.get(
      origin + '/nassav/api/resource/cover?avid=LOCAL-PLAYBACK&_context=' + admin.cache_identity
    )
    assert.equal(wrongImage.status(), 409)
    const deniedSocket = await pageA.evaluate(
      async (identity) =>
        new Promise((resolve) => {
          const ws = new WebSocket(`ws://${location.host}/nassav/ws/tasks/`, [
            'nassav.tasks.v1',
            'nassav.context.' + identity,
          ])
          ws.onopen = () => {
            ws.close()
            resolve(false)
          }
          ws.onclose = () => resolve(true)
        }),
      admin.cache_identity
    )
    assert.equal(deniedSocket, true)
    await pageB.evaluate(
      (identity) =>
        new Promise((resolve, reject) => {
          const ws = new WebSocket(`ws://${location.host}/nassav/ws/tasks/`, [
            'nassav.tasks.v1',
            'nassav.context.' + identity,
          ])
          window.revocationProbe = { ws, closed: null }
          ws.onopen = () => resolve(true)
          ws.onclose = (event) => {
            window.revocationProbe.closed = event.code
          }
          ws.onerror = () => reject(new Error('Probe handshake failed'))
        }),
      member.cache_identity
    )
    const maintenance = await browser.newContext()
    const maintenanceLogin = await login(
      maintenance,
      fixture.admin_username,
      fixture.admin_password
    )
    const accounts = await request(maintenance, maintenanceLogin, '/admin/users')
    const target = accounts.find((row) => row.username === fixture.member_username)
    await request(maintenance, maintenanceLogin, '/admin/users/' + target.user_id, 'patch', {
      expected_version: target.version,
      request_id: randomUUID(),
      reason: 'security',
      is_active: false,
    })
    await pageB.evaluate(() => {
      if (window.revocationProbe.ws.readyState === WebSocket.OPEN)
        window.revocationProbe.ws.send(JSON.stringify({ action: 'get_queue_status' }))
    })
    await pageB.waitForFunction(() => window.revocationProbe.closed !== null)
    assert.equal(await pageB.evaluate(() => window.revocationProbe.closed), 4401)
    for (const context of [a, b]) {
      assert.equal((await request(context, null, '/auth/session')).authenticated, false)
      await request(context, member, '/setting', 'get', null, 401)
    }
    jobs = (await request(maintenance, maintenanceLogin, '/tasks/jobs')).jobs
    assert.equal(
      jobs.filter((row) => row.avid === 'PRIVATE-UI' && row.state === 'queued').length,
      1
    )
    assert.equal(jobs.find((row) => row.avid === 'OPERATION-UI').state, 'queued')
    assert.equal(
      (await request(maintenance, maintenanceLogin, '/setting')).display_title,
      'original_title'
    )
    assert.ok(!JSON.stringify(await maintenance.storageState()).includes(secretA))
    assert.ok(!JSON.stringify(await b.storageState()).includes(secretB))
    assert.deepEqual(errors, [])
    console.log(
      'Native two-user credential/public-private work/quota/cancellation/context/logout/image/WS/revocation checks passed; no source worker started'
    )
    await Promise.all([a.close(), b.close(), maintenance.close()])
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
