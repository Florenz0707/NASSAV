import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createNoteDialog } from '../src/features/resources/lib/noteDialog.js'
function setup(save) {
  const state = { notes: '', savedNotes: '保存过的备注', error: '', busy: '' },
    ui = {}
  const dialog = createNoteDialog({
    state,
    ui,
    save:
      save ||
      (async ({ notes }) => {
        state.savedNotes = notes
        return { success: true }
      }),
  })
  return { state, ui, dialog }
}
test('opening copies saved text; close never discards dirty notes without explicit decision', async () => {
  const { state, ui, dialog } = setup()
  dialog.open()
  assert.equal(state.notes, state.savedNotes)
  state.notes = '未保存'
  const leaving = dialog.close()
  assert.equal(ui.confirm, true)
  assert.equal(ui.open, true)
  dialog.keep()
  assert.equal(await leaving, false)
  assert.equal(state.notes, '未保存')
  const confirmed = dialog.close()
  dialog.discard()
  assert.equal(await confirmed, true)
  assert.equal(ui.open, false)
  assert.equal(state.notes, state.savedNotes)
})
test('save failure/conflict retains dialog and draft; clear requires saving', async () => {
  const { state, ui, dialog } = setup(async () => ({ success: false }))
  dialog.open()
  state.notes = ''
  await dialog.persist()
  assert.equal(ui.open, true)
  assert.equal(state.savedNotes, '保存过的备注')
  const fresh = setup()
  fresh.dialog.open()
  fresh.state.notes = ''
  await fresh.dialog.persist()
  assert.equal(fresh.ui.open, false)
  assert.equal(fresh.state.savedNotes, '')
})
test('busy save prevents close; account/resource reset invalidates pending navigation and late save', async () => {
  let resolve
  const { state, ui, dialog } = setup(
    () =>
      new Promise((yes) => {
        resolve = yes
      })
  )
  dialog.open()
  state.notes = '草稿'
  const leave = dialog.close()
  dialog.reset()
  assert.equal(await leave, false)
  dialog.open()
  state.notes = '第二稿'
  const saving = dialog.persist()
  dialog.reset()
  dialog.open()
  resolve({ success: true })
  await saving
  assert.equal(ui.open, true)
  state.busy = 'notes'
  assert.equal(await dialog.close(), false)
})

test('background favorite save does not block navigation when notes are closed', async () => {
  const { state, dialog } = setup()
  state.busy = 'favorite'
  assert.equal(await dialog.close(), true)
})
