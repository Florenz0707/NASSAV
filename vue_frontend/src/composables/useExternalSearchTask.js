import { ref } from 'vue'
import { externalSearchApi } from '../api/index.js'

export function waitForSearchPoll(signal, milliseconds = 1500) {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve()
    const finish = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    const timer = setTimeout(finish, milliseconds)
    signal.addEventListener('abort', finish, { once: true })
  })
}

export async function pollExternalSearch(
  query,
  { signal, current, onStatus, api = externalSearchApi, wait = waitForSearchPoll }
) {
  const submission = await api.submit(query, signal)
  if (signal.aborted || !current()) return null
  let snapshot = submission.data
  const { task_id: taskId, token } = snapshot
  const deadline = Date.now() + 1850 * 1000
  let failures = 0
  while (!signal.aborted && current()) {
    onStatus(snapshot.state)
    if (snapshot.state === 'succeeded') return snapshot.result
    if (snapshot.state === 'failed') throw new Error(snapshot.message || '搜索失败，请重试')
    if (Date.now() > deadline) throw new Error('搜索等待超时，请重试')
    await wait(signal)
    if (signal.aborted || !current()) return null
    try {
      const response = await api.getJob(taskId, token, signal)
      snapshot = response.data
      failures = 0
    } catch (error) {
      if (signal.aborted || !current()) return null
      failures += 1
      if (failures >= 3 || [401, 403, 404].includes(error.httpStatus)) throw error
    }
  }
  return null
}

export function useExternalSearchTask() {
  const status = ref('')
  let controller
  function cancel() {
    controller?.abort()
    status.value = ''
  }
  async function search(query, current) {
    cancel()
    controller = new AbortController()
    return pollExternalSearch(query, {
      signal: controller.signal,
      current,
      onStatus: (value) => {
        status.value = value
      },
    })
  }
  return { status, search, cancel }
}
