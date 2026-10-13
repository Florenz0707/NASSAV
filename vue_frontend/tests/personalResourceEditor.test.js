import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPersonalResourceEditor } from '../src/features/resources/lib/personalResourceEditor.js'

const snapshot = (avid = 'TEST-001', version = 0, notes = '') => ({
  avid,
  state_version: version,
  notes,
  watched: false,
  is_favorite: false,
})
function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

test('personal edits persist partial state, prevent duplicate clicks, preserve a notes draft while toggling', async () => {
  const state = {},
    requests = [],
    updated = []
  const editor = createPersonalResourceEditor({
    state,
    onUpdated: (row) => updated.push(row),
    updateStatus: (avid, payload) => {
      const next = deferred()
      requests.push({ ...next, avid, payload })
      return next.promise
    },
  })
  editor.sync(snapshot(), 'first')
  state.notes = '尚未保存的备注'
  const pending = editor.save({ is_favorite: true }, 'favorite')
  assert.equal(state.busy, 'favorite')
  await editor.save({ watched: true }, 'watched')
  assert.equal(requests.length, 1)
  assert.deepEqual(requests[0].payload, { is_favorite: true, expected_version: 0 })
  requests[0].resolve({ data: { ...snapshot('TEST-001', 1), is_favorite: true } })
  await pending
  assert.equal(state.isFavorite, true)
  assert.equal(state.notes, '尚未保存的备注')
  const saving = editor.save({ notes: state.notes }, 'notes')
  requests[1].resolve({ data: { ...snapshot('TEST-001', 2, state.notes), is_favorite: true } })
  await saving
  assert.equal(state.savedNotes, state.notes)
  assert.equal(updated.length, 2)
})

test('conflicts preserve the draft and use the server version only after explicit retry', async () => {
  const state = {},
    calls = []
  const editor = createPersonalResourceEditor({
    state,
    updateStatus: async (_avid, body) => {
      calls.push(body)
      if (calls.length === 1) throw { code: 409, data: snapshot('TEST-001', 4, '其他页面的备注') }
      return { data: snapshot('TEST-001', 5, body.notes) }
    },
  })
  editor.sync(snapshot('TEST-001', 3, '旧备注'), 'first')
  state.notes = '我的草稿'
  await editor.save({ notes: state.notes }, 'notes')
  assert.equal(state.notes, '我的草稿')
  assert.equal(state.savedNotes, '其他页面的备注')
  assert.match(state.error, /草稿已保留/)
  assert.equal(calls.length, 1)
  await editor.save({ notes: state.notes }, 'notes')
  assert.equal(calls[1].expected_version, 4)
  assert.equal(state.savedNotes, '我的草稿')
})

for (const transition of ['resource', 'user', 'logout']) {
  test(`late responses cannot cross ${transition} boundaries`, async () => {
    const state = {},
      next = deferred(),
      published = []
    const editor = createPersonalResourceEditor({
      state,
      updateStatus: () => next.promise,
      onUpdated: (row) => published.push(row),
    })
    editor.sync(snapshot(), 'first')
    const saving = editor.save({ notes: 'old private note' }, 'notes')
    if (transition === 'logout') editor.reset()
    else
      editor.sync(
        snapshot(transition === 'resource' ? 'TEST-002' : 'TEST-001'),
        transition === 'user' ? 'second' : 'first'
      )
    next.resolve({ data: snapshot('TEST-001', 1, 'old private note') })
    assert.equal((await saving).ignored, true)
    assert.equal(state.notes, '')
    assert.equal(state.busy, '')
    assert.equal(published.length, 0)
  })
}

test('failed save keeps notes, clear is saved explicitly, stale metadata does not roll back state', async () => {
  const state = {}
  let fails = true
  const editor = createPersonalResourceEditor({
    state,
    updateStatus: async (_avid, body) => {
      if (fails) throw { message: '暂时不可用' }
      return { data: snapshot('TEST-001', 3, body.notes) }
    },
  })
  editor.sync(snapshot('TEST-001', 2, 'existing'), 'first')
  state.notes = 'new'
  await editor.save({ notes: state.notes }, 'notes')
  assert.equal(state.notes, 'new')
  assert.equal(state.error, '暂时不可用')
  editor.sync(snapshot('TEST-001', 1, 'stale'), 'first')
  assert.equal(state.savedNotes, 'existing')
  fails = false
  state.notes = ''
  await editor.save({ notes: '' }, 'notes')
  assert.equal(state.savedNotes, '')
  assert.equal(state.error, '')
})
