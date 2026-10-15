import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRenderer } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { sourceApi } from '../src/api/index.js'
import { personalCredentialApi } from '../src/api/credentials.js'
import { useSessionStore } from '../src/features/auth/stores/session.js'
import { usePersonalCredentials } from '../src/features/cookies/composables/usePersonalCredentials.js'

const renderer = createRenderer({
  createComment: () => ({}),
  createElement: () => ({}),
  insert() {},
  remove() {},
  parentNode() {},
  nextSibling() {},
})
function mount() {
  setActivePinia(createPinia())
  const session = useSessionStore()
  session.status = 'authenticated'
  session.identity = 'login-a'
  session.sourceIdentity = 'source-a'
  let editor
  const app = renderer.createApp({
    setup() {
      editor = usePersonalCredentials()
      return () => null
    },
  })
  app.mount({})
  return { editor, session, unmount: () => app.unmount() }
}
const metadata = {
  id: 'credential-a',
  source_name: 'jable',
  kind: 'account',
  state: 'active',
  version: 2,
}

test('personal credential writes are blind, CAS protected and source-only invalidating', async () => {
  const originals = { ...personalCredentialApi },
    originalList = sourceApi.getList
  sourceApi.getList = async () => ({ data: ['Jable'] })
  personalCredentialApi.list = async () => ({ data: [metadata] })
  const fixture = mount(),
    { editor, session } = fixture
  try {
    await editor.load()
    assert.equal(editor.cookie.value, '')
    editor.cookie.value = 'account_session=test-only-secret'
    await editor.save()
    assert.match(editor.userAgentError.value, /User-Agent/)
    assert.equal(editor.cookieError.value, '')
    editor.userAgent.value = 'test-UA'
    personalCredentialApi.update = async (id, body) => {
      assert.equal(id, metadata.id)
      assert.deepEqual(body, {
        expected_version: 2,
        cookie: 'account_session=test-only-secret',
        user_agent: 'test-UA',
        kind: 'account',
      })
      throw { httpStatus: 409 }
    }
    await editor.save()
    assert.match(editor.error.value, /版本已变化/)
    assert.equal(editor.cookie.value, 'account_session=test-only-secret')
    assert.equal(editor.credential.value.version, 2)
    personalCredentialApi.update = async () => ({
      data: { ...metadata, version: 3, source_cache_identity: 'source-b' },
    })
    await editor.save()
    assert.equal(session.identity, 'login-a')
    assert.equal(session.sourceIdentity, 'source-b')
    assert.equal(editor.cookie.value, '')
    assert.equal(editor.userAgent.value, '')
    personalCredentialApi.revoke = async (id, version) => {
      assert.equal(id, metadata.id)
      assert.equal(version, 3)
      return {
        data: { ...metadata, version: 4, state: 'revoked', source_cache_identity: 'source-c' },
      }
    }
    await editor.save(true)
    assert.equal(editor.credential.value.state, 'revoked')
    assert.equal(session.sourceIdentity, 'source-c')
  } finally {
    fixture.unmount()
    Object.assign(personalCredentialApi, originals)
    sourceApi.getList = originalList
  }
})

test('unmount clears typed secrets and a delayed write cannot update another login', async () => {
  const originals = { ...personalCredentialApi },
    originalList = sourceApi.getList
  sourceApi.getList = async () => ({ data: ['Jable'] })
  personalCredentialApi.list = async () => ({ data: [metadata] })
  let release
  personalCredentialApi.update = () =>
    new Promise((resolve) => {
      release = resolve
    })
  const fixture = mount(),
    { editor, session } = fixture
  try {
    await editor.load()
    editor.cookie.value = 'account_session=temporary-input'
    editor.userAgent.value = 'fixture-UA'
    const writing = editor.save()
    fixture.unmount()
    session.identity = 'login-b'
    session.sourceIdentity = 'source-new-login'
    assert.equal(editor.cookie.value, '')
    release({ data: { ...metadata, version: 3, source_cache_identity: 'stale-source' } })
    await writing
    assert.equal(session.sourceIdentity, 'source-new-login')
    assert.equal(editor.credential.value.version, 2)
    assert.equal(editor.message.value, '')
  } finally {
    Object.assign(personalCredentialApi, originals)
    sourceApi.getList = originalList
  }
})
