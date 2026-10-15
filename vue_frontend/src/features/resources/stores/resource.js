import { useSessionStore } from '../../auth/stores/session.js'
import { useMembershipsStore } from '../../library/stores/memberships.js'
import { useLibraryCommandsStore } from '../../library/stores/commands.js'
import { useUserOperationsStore } from '../../tasks/stores/userOperations.js'
import { logger } from '../../../shared/lib/logger.js'
import { useTaskJobsStore } from '../../tasks/stores/taskJobs.js'
import { createResourceList } from './resourceList.js'
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { downloadApi, resourceApi, sourceApi } from '../../../api/index.js'
import {
  notifyScrapeBatch,
  notifyScrapeJobTransition,
} from '../../tasks/stores/scrapeJobFeedback.js'
import {
  mergeScrapeJob,
  scrapeJobNeedsPolling,
  TERMINAL_JOB_STATES,
} from '../../tasks/stores/scrapeJobState.js'

export const useResourceStore = defineStore('resource', () => {
  const taskJobs = useTaskJobsStore()
  const session = useSessionStore(),
    libraryCommands = useLibraryCommandsStore(),
    operations = useUserOperationsStore()
  const shared = () => Boolean(session.capabilities.shared_library)
  const list = createResourceList(resourceApi)
  watch(
    () => useMembershipsStore().revision,
    () => {
      if (shared()) list.refresh().catch(() => {})
    }
  )
  watch(
    () => taskJobs.visible,
    (jobs, previous = []) => {
      for (const job of jobs.filter((j) => j.job_type === 'scrape')) {
        const old = previous.find((j) => j.job_id === job.job_id)
        if (old && notifyScrapeJobTransition(old, job, false)) list.refresh().catch(() => {})
        else if (old && !old.resource_saved && job.resource_saved) list.refresh().catch(() => {})
      }
    }
  )
  const {
    resources,
    loading,
    error,
    pagination,
    fetchResources,
    cancelResourceQuery,
    resetResourceList,
  } = list
  const sources = ref([])
  const downloads = ref([])
  const downloadStates = ref(new Map())
  const scrapeJobs = ref(new Map())
  const visibleScrapeJobs = computed(() =>
    shared()
      ? operations.visible
          .filter((item) => item.kind === 'scrape')
          .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
      : [
          ...scrapeJobs.value.values(),
          ...taskJobs.visible.filter((j) => j.job_type === 'scrape'),
        ].sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0))
  )
  watch(
    () => operations.operations,
    (items, previous = new Map()) => {
      if (!shared()) return
      for (const item of items.values()) {
        const old = previous.get(item.operation_id)
        if (
          old &&
          old.stage !== item.stage &&
          ['resource_committed', 'succeeded', 'failed', 'cancelled'].includes(item.stage)
        ) {
          list.refresh().catch(() => {})
          break
        }
      }
    }
  )
  const pendingJobRequests = new Set()
  const pendingJobEventVersions = new Map()
  let scrapePollTimer = null
  let trackingGeneration = 0
  let SCRAPE_STORAGE_KEY = 'nassav:scrape-jobs:v1'

  function persistScrapeJobs() {
    if (!SCRAPE_STORAGE_KEY || typeof localStorage === 'undefined') return
    const current = [...scrapeJobs.value.values()].filter(
      (job) => scrapeJobNeedsPolling(job) || Date.now() / 1000 - job.updated_at < 86400
    )
    localStorage.setItem(SCRAPE_STORAGE_KEY, JSON.stringify(current.slice(0, 100)))
  }

  function setScrapeJob(job, { notify = true } = {}) {
    const previous = scrapeJobs.value.get(job.task_id)
    const latestForResource = visibleScrapeJobs.value.find(
      (existing) => existing.avid === job.avid && existing.action === job.action
    )
    const isRetry = !previous && job.state === 'queued' && latestForResource?.state === 'failed'
    const merged = mergeScrapeJob(previous, job)
    if (merged === previous) return previous
    scrapeJobs.value = new Map(scrapeJobs.value).set(job.task_id, merged)
    persistScrapeJobs()
    syncScrapePolling()
    if (notify && notifyScrapeJobTransition(previous, merged, isRetry)) {
      list.refresh().catch(() => {})
    }
    return merged
  }

  function syncScrapePolling() {
    const pending = [...scrapeJobs.value.values()].some((job) => scrapeJobNeedsPolling(job))
    if (pending && !scrapePollTimer) {
      scrapePollTimer = setInterval(() => refreshPendingScrapeJobs(), 5000)
    } else if (!pending && scrapePollTimer) {
      clearInterval(scrapePollTimer)
      scrapePollTimer = null
    }
  }

  function restoreScrapeJobs() {
    if (!SCRAPE_STORAGE_KEY || typeof localStorage === 'undefined') return
    try {
      const saved = JSON.parse(localStorage.getItem(SCRAPE_STORAGE_KEY) || '[]')
      if (Array.isArray(saved)) {
        for (const job of saved) {
          if (job?.job_id) {
            taskJobs.refresh(job.job_id)
            continue
          }
          if (job?.task_id && job?.status_token) setScrapeJob(job, { notify: false })
        }
      }
    } catch {
      localStorage.removeItem(SCRAPE_STORAGE_KEY)
    }
    return Promise.allSettled(
      [...scrapeJobs.value.keys()].map((taskId) => refreshScrapeJob(taskId))
    )
  }

  async function refreshScrapeJob(taskId) {
    const current = scrapeJobs.value.get(taskId)
    if (!current?.status_token || pendingJobRequests.has(taskId)) return current
    const generation = trackingGeneration
    pendingJobRequests.add(taskId)
    try {
      const response = await resourceApi.getScrapeJob(taskId, current.status_token)
      if (generation !== trackingGeneration || !scrapeJobs.value.has(taskId)) return null
      return setScrapeJob({ ...response.data, status_token: current.status_token })
    } catch (err) {
      if (generation !== trackingGeneration || !scrapeJobs.value.has(taskId)) return null
      if (err.code === 404 || err.code === 403) {
        if (current.state === 'failed') return current
        if (
          current.state === 'succeeded' &&
          ['completed', 'failed', 'skipped'].includes(current.translation?.state)
        )
          return current
        if (current.state === 'succeeded')
          return setScrapeJob({
            ...current,
            translation: { state: 'unavailable', message: '翻译跟踪已过期' },
          })
        return setScrapeJob({
          ...current,
          state: 'failed',
          stage: null,
          message: '任务状态已过期，请重新提交',
          version: (current.version || 0) + 1,
          updated_at: Date.now() / 1000,
        })
      }
      return current
    } finally {
      if (generation === trackingGeneration) {
        pendingJobRequests.delete(taskId)
        const pendingVersion = pendingJobEventVersions.get(taskId)
        pendingJobEventVersions.delete(taskId)
        const latest = scrapeJobs.value.get(taskId)
        if (
          generation === trackingGeneration &&
          pendingVersion > (latest?.version || 0) &&
          latest &&
          !TERMINAL_JOB_STATES.has(latest.state)
        ) {
          refreshScrapeJob(taskId)
        }
      }
    }
  }

  async function refreshPendingScrapeJobs() {
    const pending = [...scrapeJobs.value.values()].filter((job) => scrapeJobNeedsPolling(job))
    await Promise.allSettled(pending.map((job) => refreshScrapeJob(job.task_id)))
  }

  function handleScrapeJobEvent(event) {
    if (event?.job_type !== 'scrape' || !scrapeJobs.value.has(event.task_id)) return
    const current = scrapeJobs.value.get(event.task_id)
    if ((event.version || 0) <= (current.version || 0) || event.state === current.state) return
    if (pendingJobRequests.has(event.task_id)) {
      pendingJobEventVersions.set(
        event.task_id,
        Math.max(pendingJobEventVersions.get(event.task_id) || 0, event.version)
      )
      return
    }
    return refreshScrapeJob(event.task_id)
  }

  function registerScrapeSubmission(data, { notify = true } = {}) {
    const id = data.job_id || data.job?.job_id
    if (id) {
      if (data.job?.job_id) taskJobs.apply(data.job)
      taskJobs.refresh(id)
      return data.job
    }
    const job = setScrapeJob({ ...data.job, status_token: data.status_token }, { notify })
    refreshScrapeJob(job.task_id)
    return job
  }

  function registerScrapeBatch(results) {
    let queued = 0
    let failed = 0
    for (const item of results) {
      if (item.code === 202 && item.task_id) {
        queued += 1
        registerScrapeSubmission(
          {
            job: {
              task_id: item.task_id,
              job_id: item.job_id,
              job_type: 'scrape',
              action: item.action,
              avid: item.avid,
              state: 'queued',
              stage: null,
              version: 0,
              updated_at: Date.now() / 1000,
            },
            status_token: item.status_token,
          },
          { notify: false }
        )
      } else if (item.code >= 400 && item.code !== 409) {
        failed += 1
      }
    }
    notifyScrapeBatch(queued, failed)
  }

  function getScrapeJobForAvid(avid) {
    return visibleScrapeJobs.value.find((job) => job.avid === String(avid || '').toUpperCase())
  }

  function dismissScrapeJob(taskId) {
    const next = new Map(scrapeJobs.value)
    next.delete(taskId)
    pendingJobEventVersions.delete(taskId)
    scrapeJobs.value = next
    persistScrapeJobs()
    syncScrapePolling()
  }

  function stopScrapeTracking() {
    trackingGeneration++
    pendingJobEventVersions.clear()
    if (scrapePollTimer) clearInterval(scrapePollTimer)
    scrapePollTimer = null
  }

  function invalidateSourceRequests() {
    trackingGeneration++
    pendingJobRequests.clear()
    pendingJobEventVersions.clear()
    loading.value = false
    error.value = null
    downloadStates.value = new Map(
      [...downloadStates.value].filter(([, state]) => state !== 'submitting')
    )
  }

  function beginSession(identity) {
    stopScrapeTracking()
    pendingJobRequests.clear()
    scrapeJobs.value = new Map()
    downloads.value = []
    downloadStates.value = new Map()
    sources.value = []
    resetResourceList()
    SCRAPE_STORAGE_KEY = identity ? `nassav:scrape-jobs:v2:${encodeURIComponent(identity)}` : ''
  }

  // 获取下载源列表
  async function fetchSources() {
    const generation = trackingGeneration
    try {
      const response = await sourceApi.getList()
      if (generation === trackingGeneration) sources.value = response.data || []
    } catch (err) {
      if (generation === trackingGeneration) console.error('获取下载源失败:', err)
    }
  }

  // 添加新资源
  async function addResource(avid, source = 'any', options = null) {
    if (shared())
      return options
        ? libraryCommands.execute('add', avid, { source, ...options })
        : libraryCommands.request('add', avid, source)
    const generation = trackingGeneration
    loading.value = true
    error.value = null
    try {
      const response = await resourceApi.addNew(avid, source)
      if (generation === trackingGeneration) registerScrapeSubmission(response.data)
      return response
    } catch (err) {
      if (generation === trackingGeneration) error.value = err.message || '添加资源失败'
      throw err
    } finally {
      if (generation === trackingGeneration) loading.value = false
    }
  }

  // 刷新资源
  async function refreshResource(avid, params = null) {
    if (shared())
      return libraryCommands.request(
        'refresh',
        avid,
        params?.source || resources.value.find((item) => item.avid === avid)?.source
      )
    const generation = trackingGeneration
    const response = await resourceApi.refresh(avid, params)
    if (generation === trackingGeneration) registerScrapeSubmission(response.data)
    return response
  }

  // 批量刷新/删除等，使用后端批量接口
  async function batchRefresh(avids = []) {
    if (shared()) return libraryCommands.request('refresh', avids)
    if (!Array.isArray(avids) || avids.length === 0) return
    const payload = {
      actions: avids.map((avid) => ({ action: 'refresh', avid })),
    }
    const resp = await resourceApi.submitScrapeBatch(payload.actions)
    registerScrapeBatch(resp.data?.results || [])
    return resp
  }

  async function batchDelete(avids = [], action = 'delete-all', evidence = null) {
    if (shared()) {
      if (action !== 'delete-all') throw new Error('共享资源仅支持移出本人的资源库')
      const results = await libraryCommands.batch('release', avids, {
        memberships:
          evidence ||
          Object.fromEntries(
            resources.value
              .filter((item) => avids.includes(item.avid))
              .map((item) => [item.avid, item])
          ),
      })
      const succeeded = results.filter((item) => item.code >= 200 && item.code < 300)
      const failed = results.filter((item) => !succeeded.includes(item))
      const removed = new Set(succeeded.map((item) => item.avid))
      resources.value = resources.value.filter((item) => !removed.has(item.avid))
      return { succeeded, failed }
    }
    if (!Array.isArray(avids) || avids.length === 0) return { succeeded: [], failed: [] }
    const payload = { actions: avids.map((avid) => ({ action, avid })) }
    const resp = await resourceApi.batch(payload)
    const results = Array.isArray(resp?.data?.results) ? resp.data.results : []
    const succeeded = []
    const failed = []
    for (const [index, avid] of avids.entries()) {
      const item = results[index]
      if (item?.code === 200 && item.avid === avid && item.action === action) {
        succeeded.push(item)
      } else {
        failed.push(
          item?.avid === avid && item.action === action
            ? item
            : { action, avid, code: 500, message: '删除结果缺失或不匹配' }
        )
      }
    }
    for (const item of succeeded) {
      if ((item.action === 'delete' || item.action === 'delete-all') && item.avid) {
        _removeResourceByAvid(item.avid)
      } else if (item.action === 'delete-video' && item.avid) {
        const resource = _resourcesArray().find((entry) => entry.avid === item.avid)
        if (resource) resource.has_video = false
      }
    }
    return { succeeded, failed }
  }

  async function removeAsset(avid, action, membership = null) {
    if (shared()) {
      if (action !== 'delete') throw new Error('共享资源仅支持移出本人的资源库')
      const response = await libraryCommands.execute('release', avid, { membership })
      resources.value = resources.value.filter((item) => item.avid !== avid)
      return response
    }
    if (action === 'deleteFile') return downloadApi.deleteFile(avid)
    if (action === 'delete') return resourceApi.delete(avid)
    throw new Error('不支持的资源删除操作')
  }

  // 提交下载
  async function submitDownload(avid, preferredSource = '') {
    if (shared())
      return libraryCommands.request(
        'download',
        avid,
        preferredSource || resources.value.find((item) => item.avid === avid)?.source
      )
    const generation = trackingGeneration
    if (!avid) return null
    setDownloadState(avid, 'submitting')
    try {
      const response = await downloadApi.submitDownload(avid)
      if (generation === trackingGeneration) setDownloadState(avid, 'downloading')
      return response
    } catch (err) {
      if (generation !== trackingGeneration) throw err
      if (err && err.code === 409) {
        updateResourceDownloadStatus(avid, true)
      } else {
        clearDownloadState(avid)
      }
      throw err
    }
  }

  async function batchSubmitDownload(avids = []) {
    if (shared()) return libraryCommands.request('download', avids)
    const generation = trackingGeneration
    if (!Array.isArray(avids) || avids.length === 0) return
    for (const avid of avids) {
      setDownloadState(avid, 'submitting')
    }
    try {
      const resp = await downloadApi.batchSubmit(avids)
      if (generation !== trackingGeneration) return resp
      for (const avid of avids) {
        setDownloadState(avid, 'downloading')
      }
      return resp
    } catch (err) {
      if (generation !== trackingGeneration) throw err
      for (const avid of avids) {
        clearDownloadState(avid)
      }
      throw err
    }
  }

  function setDownloadState(avid, state) {
    if (!avid || !state) return
    const next = new Map(downloadStates.value)
    next.set(avid, state)
    downloadStates.value = next
  }

  function clearDownloadState(avid) {
    if (!avid || !downloadStates.value.has(avid)) return
    const next = new Map(downloadStates.value)
    next.delete(avid)
    downloadStates.value = next
  }

  function getDownloadState(avid) {
    if (shared()) {
      if (
        libraryCommands.intent?.action === 'download' &&
        libraryCommands.intent.avids.includes(avid)
      )
        return 'submitting'
      const latest = [...operations.operations.values()]
        .filter((item) => item.kind === 'download' && item.avid === avid)
        .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0]
      return latest && !['succeeded', 'failed', 'cancelled'].includes(latest.state)
        ? 'downloading'
        : null
    }
    if (!avid) return null
    return downloadStates.value.get(avid) || null
  }

  function syncDownloadingAvids(avids = []) {
    const activeAvids = new Set((Array.isArray(avids) ? avids : []).filter(Boolean))
    const next = new Map(downloadStates.value)

    for (const [avid, state] of next.entries()) {
      if (state === 'downloading' && !activeAvids.has(avid)) {
        next.delete(avid)
      }
    }

    for (const avid of activeAvids) {
      if (!_resourceHasVideo(avid)) {
        next.set(avid, 'downloading')
      } else {
        next.delete(avid)
      }
    }

    downloadStates.value = next
  }

  // helper: normalize resources to an array
  function _resourcesArray() {
    const raw = resources.value
    if (Array.isArray(raw)) return raw
    if (raw && Array.isArray(raw.results)) return raw.results
    if (raw && Array.isArray(raw.data)) return raw.data
    return []
  }

  // helper: merge or upsert a single resource object into current list
  function _mergeOrUpsertResource(resObj) {
    if (!resObj || !resObj.avid) return
    const arr = _resourcesArray()
    const idx = arr.findIndex((r) => r.avid === resObj.avid)
    if (idx !== -1) {
      // merge fields
      arr[idx] = Object.assign({}, arr[idx], resObj)
    } else {
      // if current view is page 1, insert at top, otherwise ignore
      if (pagination.value && pagination.value.page === 1) {
        arr.unshift(resObj)
        // respect page_size
        const max = pagination.value && pagination.value.page_size ? pagination.value.page_size : 20
        if (arr.length > max) arr.splice(max)
      }
    }
    // write back depending on original resources shape
    if (Array.isArray(resources.value)) resources.value = arr
    else if (resources.value && Array.isArray(resources.value.results))
      resources.value.results = arr
    else if (resources.value && Array.isArray(resources.value.data)) resources.value.data = arr
    else resources.value = arr
  }

  function _removeResourceByAvid(avid) {
    if (!avid) return
    const arr = _resourcesArray()
    const idx = arr.findIndex((r) => r.avid === avid)
    if (idx !== -1) {
      arr.splice(idx, 1)
    }
    if (Array.isArray(resources.value)) resources.value = arr
    else if (resources.value && Array.isArray(resources.value.results))
      resources.value.results = arr
    else if (resources.value && Array.isArray(resources.value.data)) resources.value.data = arr
    else resources.value = arr
    // adjust pagination total if present
    if (pagination.value && typeof pagination.value.total === 'number') {
      pagination.value.total = Math.max(0, pagination.value.total - 1)
    }
  }

  // 更新资源的下载状态（用于 WebSocket 实时更新）
  function updateResourceDownloadStatus(avid, hasVideo) {
    if (!avid) return
    const arr = _resourcesArray()
    const resource = arr.find((r) => r.avid === avid)
    if (resource) {
      resource.has_video = hasVideo
      logger.debug('[resource] 更新资源下载状态:', avid, hasVideo)
    }
    if (hasVideo) {
      clearDownloadState(avid)
    }
  }

  function _resourceHasVideo(avid) {
    if (!avid) return false
    const arr = _resourcesArray()
    return arr.some((resource) => resource.avid === avid && resource.has_video)
  }

  // 统计信息
  const stats = computed(() => {
    const arr = _resourcesArray()
    const total = (pagination.value && pagination.value.total) || arr.length
    const downloadedCount = Array.isArray(downloads.value)
      ? downloads.value.length
      : arr.filter((r) => r.has_video).length
    const pendingCount = Math.max(total - downloadedCount, arr.filter((r) => !r.has_video).length)
    return {
      total,
      downloaded: downloadedCount,
      pending: pendingCount,
    }
  })

  return {
    resources,
    sources,
    downloads,
    downloadStates,
    loading,
    error,
    pagination,
    stats,
    fetchResources,
    cancelResourceQuery,
    resetResourceList,
    fetchSources,
    addResource,
    refreshResource,
    scrapeJobs,
    visibleScrapeJobs,
    restoreScrapeJobs,
    refreshScrapeJob,
    refreshPendingScrapeJobs,
    handleScrapeJobEvent,
    registerScrapeBatch,
    removeAsset,
    getScrapeJobForAvid,
    dismissScrapeJob,
    stopScrapeTracking,
    beginSession,
    invalidateSourceRequests,
    submitDownload,
    batchRefresh,
    batchDelete,
    batchSubmitDownload,
    getDownloadState,
    setDownloadState,
    clearDownloadState,
    syncDownloadingAvids,
    updateResourceDownloadStatus,
  }
})
