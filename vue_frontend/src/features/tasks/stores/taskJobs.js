import { createRequestId } from '../../../shared/lib/requestId.js'
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { taskApi } from '../../../api/index.js'

const ended = new Set(['succeeded', 'failed', 'cancelled'])
// DB snapshots own task state; local storage contains only hidden IDs.
export const useTaskJobsStore = defineStore('taskJobs', () => {
  const jobs = ref(new Map()),
    hidden = ref(new Set()),
    busy = ref(new Set())
  const ordering = ref('-created_at')
  let listRevision = 0
  const error = ref(''),
    listError = ref(''),
    total = ref(0),
    hasMore = ref(false),
    loading = ref(false)
  const visible = computed(() =>
    [...jobs.value.values()].filter((j) => !hidden.value.has(j.job_id))
  )
  let epoch = 0,
    timer = null,
    page = 0,
    storageKey = ''
  const pending = new Map(),
    commands = new Map()
  function apply(job) {
    if (!job?.job_id || !Number.isInteger(job.version)) return null
    const previous = jobs.value.get(job.job_id)
    if (previous && job.version <= previous.version) return previous
    jobs.value = new Map(jobs.value).set(job.job_id, job)
    return job
  }
  async function load(more = false) {
    if (loading.value) return
    const revision = listRevision
    const current = epoch,
      target = more ? page + 1 : 1
    loading.value = true
    try {
      const response = await taskApi.listJobs({ page: target, ordering: ordering.value })
      if (current !== epoch || revision !== listRevision) return
      if (!Array.isArray(response.data?.jobs)) throw new Error('任务列表格式无效')
      response.data.jobs.forEach(apply)
      page = more ? target : Math.max(page, target)
      total.value = response.data.pagination.total
      hasMore.value =
        more || page <= 1
          ? response.data.pagination.has_more
          : page * response.data.pagination.page_size < total.value
      listError.value = ''
    } catch (e) {
      if (current === epoch && revision === listRevision)
        listError.value = e.message || '无法读取任务列表'
    } finally {
      if (current === epoch && revision === listRevision) loading.value = false
    }
  }
  function setOrdering(value) {
    if (!['-created_at', '-updated_at'].includes(value) || ordering.value === value) return
    ordering.value = value
    listRevision++
    page = 0
    jobs.value = new Map()
    hasMore.value = false
    loading.value = false
    return load()
  }
  async function refresh(id, quiet = false) {
    if (pending.has(id)) return pending.get(id)
    const current = epoch
    const operation = (async () => {
      try {
        const response = await taskApi.getJob(id)
        if (current === epoch) return apply(response.data)
      } catch (e) {
        if (current === epoch && !quiet) listError.value = e.message || '任务状态更新失败'
      } finally {
        if (current === epoch) pending.delete(id)
      }
    })()
    pending.set(id, operation)
    return operation
  }
  async function poll(all = false) {
    await Promise.allSettled(
      [...jobs.value.values()]
        .filter(
          (j) =>
            !hidden.value.has(j.job_id) &&
            (all ||
              (!ended.has(j.state) && j.state !== 'paused') ||
              ['pending', 'running'].includes(j.cleanup_state))
        )
        .map((j) => refresh(j.job_id))
    )
  }
  function hint(event) {
    if (!event?.job_id || hidden.value.has(event.job_id)) return
    if ((event.version || 0) > (jobs.value.get(event.job_id)?.version || 0)) {
      // Even a hint received while GET is pending must trigger a later read.
      const current = epoch
      refresh(event.job_id, true).then(() => {
        if (current === epoch && event.version > (jobs.value.get(event.job_id)?.version || 0))
          refresh(event.job_id, true)
      })
    }
  }
  function hide(ids) {
    hidden.value = new Set([...hidden.value, ...ids])
    if (storageKey && typeof localStorage !== 'undefined')
      localStorage.setItem(storageKey, JSON.stringify([...hidden.value]))
  }
  async function control(action, ids) {
    const items = ids
      .filter((id) => !busy.value.has(id))
      .map((id) => jobs.value.get(id))
      .filter((j) => j?.allowed_actions?.includes(action))
      .map((j) => ({ job_id: j.job_id, expected_version: j.version }))
    if (!items.length) return []
    const current = epoch,
      key = JSON.stringify([action, items])
    const requestId = commands.get(key) || createRequestId()
    commands.set(key, requestId)
    busy.value = new Set([...busy.value, ...items.map((j) => j.job_id)])
    try {
      const response = await taskApi.controlJobs({ action, items, request_id: requestId })
      if (current !== epoch) return []
      const results = response.data.results
      results.forEach((r) => {
        if (r.job) apply(r.job)
      })
      if (!results.some((r) => r.code >= 500)) commands.delete(key)
      const failures = results.filter((r) => r.code >= 400)
      error.value = failures
        .map((r) => `${jobs.value.get(r.job_id)?.avid || r.job_id}：${r.message}`)
        .join('；')
      return results
    } catch (e) {
      if (current === epoch) error.value = e.message || '操作未确认，请重试'
      return []
    } finally {
      if (current === epoch)
        busy.value = new Set([...busy.value].filter((id) => !items.some((j) => j.job_id === id)))
    }
  }
  function reset() {
    epoch++
    listRevision++
    ordering.value = '-created_at'
    if (timer) clearInterval(timer)
    timer = null
    page = 0
    storageKey = ''
    pending.clear()
    commands.clear()
    jobs.value = new Map()
    hidden.value = new Set()
    busy.value = new Set()
    error.value = ''
    listError.value = ''
    total.value = 0
    hasMore.value = false
    loading.value = false
  }
  function start(username) {
    reset()
    storageKey = `nassav:hidden-task-jobs:v1:${username || ''}`
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || '[]')
      if (Array.isArray(saved)) hidden.value = new Set(saved.filter((id) => typeof id === 'string'))
    } catch {
      /* Invalid local preferences must not block server task tracking. */
    }
    load()
    let ticks = 0
    timer = setInterval(() => {
      ticks++
      poll(ticks % 15 === 0)
      if (ticks % 15 === 0) load()
    }, 2000)
  }
  return {
    ordering,
    setOrdering,
    jobs,
    visible,
    busy,
    error,
    listError,
    total,
    hasMore,
    loading,
    apply,
    load,
    refresh,
    poll,
    hint,
    hide,
    control,
    start,
    reset,
  }
})
