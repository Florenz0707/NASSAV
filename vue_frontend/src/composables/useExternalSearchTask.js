import { ref } from 'vue'
import { externalSearchApi } from '../api/index.js'
import { subscribeSearchJobUpdates } from './searchJobEvents.js'

export function waitForSearchPoll(signal, milliseconds = 1500, listen = () => () => {}) {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve()
    let cleanup = () => {}
    const finish = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      cleanup()
      resolve()
    }
    const timer = setTimeout(finish, milliseconds)
    signal.addEventListener('abort', finish, { once: true })
    cleanup = listen(finish)
  })
}

export async function pollExternalSearch(
  query,
  {
    signal,
    current,
    onStatus,
    onResult = () => {},
    onSubmitted = () => {},
    getPagination = () => undefined,
    api = externalSearchApi,
    wait = (signal, listen) => waitForSearchPoll(signal, 1500, listen),
    subscribe = subscribeSearchJobUpdates,
  }
) {
  const submission = await api.submit(query, signal)
  onSubmitted(submission.data)
  if (signal.aborted || !current()) return null
  let snapshot = submission.data
  const { task_id: taskId, token } = snapshot
  const deadline = Date.now() + 1850 * 1000
  let failures = 0
  let wake = null
  let notified = false
  let notifiedVersion = -1
  let displayedVersion = -1
  let displayedResult = null
  const unsubscribe = subscribe((event) => {
    if (!event || event.task_id !== taskId || signal.aborted || !current()) return
    if (
      Number.isFinite(event.version) &&
      event.version <= Math.max(snapshot.version || 0, notifiedVersion)
    )
      return
    notifiedVersion = event.version || notifiedVersion
    notified = true
    wake?.()
  })
  try {
    while (!signal.aborted && current()) {
      onStatus(snapshot.state)
      if (
        snapshot.result &&
        (Number.isFinite(snapshot.version)
          ? snapshot.version > displayedVersion
          : snapshot.result !== displayedResult)
      ) {
        onResult(snapshot.result, snapshot)
        displayedVersion = snapshot.version ?? displayedVersion
        displayedResult = snapshot.result
      }
      if (snapshot.state === 'succeeded') {
        const desired = getPagination()
        if (
          !desired ||
          !snapshot.result?.pagination ||
          snapshot.result.pagination.page === desired.page
        )
          return snapshot.result
      }
      if (snapshot.state === 'cancelled') return null
      if (snapshot.state === 'failed') throw new Error(snapshot.message || '搜索失败，请重试')
      if (Date.now() > deadline) throw new Error('搜索等待超时，请重试')
      if (!notified)
        await wait(signal, (finish) => {
          wake = finish
          return () => {
            wake = null
          }
        })
      notified = false
      if (signal.aborted || !current()) return null
      try {
        const requested = getPagination()
        const response = await api.getJob(taskId, token, signal, requested)
        if (requested && requested.page !== getPagination()?.page) continue
        if (
          !Number.isFinite(snapshot.version) ||
          !Number.isFinite(response.data.version) ||
          response.data.version >= snapshot.version
        ) {
          snapshot = response.data
        }
        failures = 0
      } catch (error) {
        if (signal.aborted || !current()) return null
        failures += 1
        if (failures >= 3 || [401, 403, 404].includes(error.httpStatus)) throw error
      }
    }
    return null
  } finally {
    unsubscribe()
  }
}

export function useExternalSearchTask() {
  const status = ref('')
  const progress = ref(null)
  let controller
  let active
  let submittedJob
  function cancel() {
    controller?.abort()
    active?.resolveSubmitted(null)
    active = null
    submittedJob = null
    status.value = ''
    progress.value = null
  }
  async function cancelJob() {
    const job = active
    if (!job) return false
    const submitted = await job.submitted
    if (!submitted || active !== job) return false
    const response = await externalSearchApi.cancelJob(submitted.task_id, submitted.token)
    if (response.data.state !== 'cancelled') return false
    if (active === job) {
      job.controller.abort()
      active = null
      status.value = 'cancelled'
    }
    return true
  }
  async function search(query, current, onResult = () => {}, getPagination = () => undefined) {
    cancel()
    controller = new AbortController()
    let resolveSubmitted
    const submitted = new Promise((resolve) => {
      resolveSubmitted = resolve
    })
    const job = { controller, submitted, resolveSubmitted }
    active = job
    try {
      return await pollExternalSearch(query, {
        signal: controller.signal,
        current,
        getPagination,
        onSubmitted: (snapshot) => {
          if (active === job) submittedJob = snapshot
          resolveSubmitted(snapshot)
        },
        onStatus: (value) => {
          status.value = value
        },
        onResult: (result, snapshot) => {
          progress.value = {
            pagesCompleted: snapshot.pages_completed || 0,
            fetchPages: result.data?.external_meta?.fetch_pages || 0,
          }
          onResult(result, snapshot)
        },
      })
    } finally {
      resolveSubmitted(null)
      if (active === job) active = null
    }
  }
  async function readPage(page, pageSize) {
    const job = submittedJob
    if (!job) return null
    const response = await externalSearchApi.getJob(job.task_id, job.token, undefined, {
      page,
      page_size: pageSize,
    })
    return submittedJob === job ? response.data.result : null
  }
  function getJobHandle() {
    return submittedJob ? { task_id: submittedJob.task_id, token: submittedJob.token } : null
  }
  function restoreJob(handle) {
    if (handle?.task_id && handle?.token) submittedJob = handle
  }
  return { status, progress, search, cancel, cancelJob, readPage, getJobHandle, restoreJob }
}
