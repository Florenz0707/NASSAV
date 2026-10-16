import { personalDataChanged } from '../../../shared/lib/personalDataEvents.js'
import { ref } from 'vue'
import { defineStore } from 'pinia'
import { libraryApi } from '../../../api/library.js'
import { useMembershipsStore } from './memberships.js'
import { useUserOperationsStore } from '../../tasks/stores/userOperations.js'
import { createLibraryCommands } from '../lib/libraryCommands.js'

export const useLibraryCommandsStore = defineStore('libraryCommands', () => {
  const memberships = useMembershipsStore(),
    operations = useUserOperationsStore()
  const intent = ref(null),
    busy = ref(false),
    error = ref('')
  let complete = null,
    reject = null,
    generation = 0
  const core = createLibraryCommands(libraryApi, {
    memberships,
    acceptOperation: (item) => operations.apply(item, { submitted: true }),
    changed: () => {
      memberships.invalidate()
      personalDataChanged(null, [
        'library',
        'resource-state',
        'resource-detail',
        'history',
        'watch-later',
      ])
    },
  })
  const cancelled = () => Object.assign(new Error('已取消操作'), { code: 'user_cancelled' })
  function reset(identity = '') {
    generation++
    core.reset(identity)
    reject?.(cancelled())
    complete = reject = null
    intent.value = null
    busy.value = false
    error.value = ''
  }
  function close() {
    if (busy.value) return
    reject?.(cancelled())
    complete = reject = null
    intent.value = null
    error.value = ''
  }
  function request(action, avids, source = '') {
    if (intent.value) return Promise.reject(new Error('请先完成当前资源操作'))
    intent.value = {
      action,
      avids: Array.isArray(avids) ? avids : [avids],
      source,
      batch: Array.isArray(avids),
    }
    error.value = ''
    return new Promise((resolve, fail) => {
      complete = resolve
      reject = fail
    })
  }
  async function confirm(options) {
    if (!intent.value || busy.value) return
    const current = generation,
      submitted = intent.value
    busy.value = true
    error.value = ''
    try {
      const response = !submitted.batch
        ? await core.execute(submitted.action, submitted.avids[0], options)
        : { data: { results: await core.batch(submitted.action, submitted.avids, options) } }
      if (current !== generation) return
      complete?.(response)
      complete = reject = null
      intent.value = null
    } catch (reason) {
      if (current === generation) error.value = reason.message || '提交失败，请重试'
    } finally {
      if (current === generation) busy.value = false
    }
  }
  return {
    intent,
    busy,
    error,
    reset,
    close,
    request,
    confirm,
    execute: core.execute,
    batch: core.batch,
  }
})
