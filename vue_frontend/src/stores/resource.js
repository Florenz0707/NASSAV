import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { downloadApi, resourceApi, sourceApi } from '../api/index.js'
import { notifyScrapeBatch, notifyScrapeJobTransition } from './scrapeJobNotifications.js'
import { mergeScrapeJob, TERMINAL_JOB_STATES } from './scrapeJobState.js'

export const useResourceStore = defineStore('resource', () => {
  const resources = ref([])
  const sources = ref([])
  const downloads = ref([])
  const downloadStates = ref(new Map())
  const loading = ref(false)
  const error = ref(null)
  const scrapeJobs = ref(new Map())
  const visibleScrapeJobs = computed(() =>
    [...scrapeJobs.value.values()].sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0))
  )
  const pendingJobRequests = new Set()
  const pendingJobEventVersions = new Map()
  let scrapePollTimer = null
  let lastResourceQuery = null
  const SCRAPE_STORAGE_KEY = 'nassav:scrape-jobs:v1'

  function persistScrapeJobs() {
    if (typeof localStorage === 'undefined') return
    const current = [...scrapeJobs.value.values()].filter(
      (job) => !TERMINAL_JOB_STATES.has(job.state) || Date.now() / 1000 - job.updated_at < 86400
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
    if (notify && notifyScrapeJobTransition(previous, merged, isRetry) && lastResourceQuery) {
      fetchResources(lastResourceQuery).catch(() => {})
    }
    return merged
  }

  function syncScrapePolling() {
    const pending = [...scrapeJobs.value.values()].some(
      (job) => !TERMINAL_JOB_STATES.has(job.state)
    )
    if (pending && !scrapePollTimer) {
      scrapePollTimer = setInterval(() => refreshPendingScrapeJobs(), 5000)
    } else if (!pending && scrapePollTimer) {
      clearInterval(scrapePollTimer)
      scrapePollTimer = null
    }
  }

  function restoreScrapeJobs() {
    if (typeof localStorage === 'undefined') return
    try {
      const saved = JSON.parse(localStorage.getItem(SCRAPE_STORAGE_KEY) || '[]')
      if (Array.isArray(saved)) {
        for (const job of saved) {
          if (job?.task_id && job?.status_token) setScrapeJob(job, { notify: false })
        }
      }
    } catch {
      localStorage.removeItem(SCRAPE_STORAGE_KEY)
    }
    refreshPendingScrapeJobs()
  }

  async function refreshScrapeJob(taskId) {
    const current = scrapeJobs.value.get(taskId)
    if (!current?.status_token || pendingJobRequests.has(taskId)) return current
    pendingJobRequests.add(taskId)
    try {
      const response = await resourceApi.getScrapeJob(taskId, current.status_token)
      return setScrapeJob({ ...response.data, status_token: current.status_token })
    } catch (err) {
      if (err.code === 404 || err.code === 403) {
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
      pendingJobRequests.delete(taskId)
      const pendingVersion = pendingJobEventVersions.get(taskId)
      pendingJobEventVersions.delete(taskId)
      const latest = scrapeJobs.value.get(taskId)
      if (
        pendingVersion > (latest?.version || 0) &&
        latest &&
        !TERMINAL_JOB_STATES.has(latest.state)
      ) {
        refreshScrapeJob(taskId)
      }
    }
  }

  async function refreshPendingScrapeJobs() {
    const pending = [...scrapeJobs.value.values()].filter(
      (job) => !TERMINAL_JOB_STATES.has(job.state)
    )
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
    scrapeJobs.value = next
    persistScrapeJobs()
    syncScrapePolling()
  }

  function stopScrapeTracking() {
    if (scrapePollTimer) clearInterval(scrapePollTimer)
    scrapePollTimer = null
  }

  // 获取资源列表
  // 支持分页和排序
  const pagination = ref({ total: 0, page: 1, page_size: 20, pages: 1 })

  async function fetchResources({
    sort_by = 'metadata_create_time',
    order = 'desc',
    page = 1,
    page_size = 20,
    search = '',
    status = 'all',
    actor = undefined,
    genre = undefined,
    watched = undefined,
    is_favorite = undefined,
  } = {}) {
    loading.value = true
    error.value = null
    try {
      console.debug('[resource] fetchResources params:', {
        sort_by,
        order,
        page,
        page_size,
        search,
        status,
        watched,
        is_favorite,
      })
      const params = { sort_by, order, page, page_size }
      lastResourceQuery = {
        sort_by,
        order,
        page,
        page_size,
        search,
        status,
        actor,
        genre,
        watched,
        is_favorite,
      }
      if (search) params.search = search
      if (status && status !== 'all') params.status = status
      if (typeof actor !== 'undefined' && actor !== null && actor !== '') params.actor = actor
      if (typeof genre !== 'undefined' && genre !== null && genre !== '') params.genre = genre
      if (typeof watched !== 'undefined') params.watched = watched
      if (typeof is_favorite !== 'undefined') params.is_favorite = is_favorite
      console.debug('[resource] fetchResources request params:', params)
      const response = await resourceApi.getList(params)
      console.debug('[resource] fetchResources response:', response)

      // 后端可能返回多种格式：
      // 1) envelope with data as an array -> { data: [ ... ], pagination?: {...} }
      // 2) envelope with data.results and data.pagination -> { data: { results: [...], pagination: {...} } }
      // 3) legacy or other -> response.data may already be the array
      let results = []
      let paginationObj = null

      if (response) {
        // case: response.data is array
        if (Array.isArray(response.data)) {
          results = response.data
          paginationObj = response.pagination || null
        }
        // case: response.data.metadata exists (new backend shape)
        else if (response.data && Array.isArray(response.data.metadata)) {
          results = response.data.metadata
          // map backend pagination fields to our pagination shape
          paginationObj = {
            total:
              response.data.total_num ||
              (response.data.pagination && response.data.pagination.total) ||
              (response.pagination && response.pagination.total) ||
              0,
            pages:
              response.data.total_pages ||
              (response.data.pagination && response.data.pagination.pages) ||
              (response.pagination && response.pagination.pages) ||
              1,
            page: page,
            page_size: page_size,
          }
        }
        // case: response.data.results exists
        else if (response.data && Array.isArray(response.data.results)) {
          results = response.data.results
          paginationObj = response.data.pagination || response.pagination || null
        }
        // case: response itself is an array (unlikely)
        else if (Array.isArray(response)) {
          results = response
        } else {
          results = response.data || []
          paginationObj = response.pagination || (response.data && response.data.pagination) || null
        }
      }

      resources.value = results || []
      if (paginationObj) {
        pagination.value = Object.assign({}, pagination.value, paginationObj)
      } else {
        // ensure pagination.page at least matches request
        pagination.value.page = page
        pagination.value.page_size = page_size
      }
    } catch (err) {
      error.value = err.message || '获取资源列表失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  // 获取下载源列表
  async function fetchSources() {
    try {
      const response = await sourceApi.getList()
      sources.value = response.data || []
    } catch (err) {
      console.error('获取下载源失败:', err)
    }
  }

  // 添加新资源
  async function addResource(avid, source = 'any') {
    loading.value = true
    error.value = null
    try {
      const response = await resourceApi.addNew(avid, source)
      registerScrapeSubmission(response.data)
      return response
    } catch (err) {
      error.value = err.message || '添加资源失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  // 刷新资源
  async function refreshResource(avid, params = null) {
    const response = await resourceApi.refresh(avid, params)
    registerScrapeSubmission(response.data)
    return response
  }

  // 批量刷新/删除等，使用后端批量接口
  async function batchRefresh(avids = []) {
    if (!Array.isArray(avids) || avids.length === 0) return
    const payload = {
      actions: avids.map((avid) => ({ action: 'refresh', avid })),
    }
    const resp = await resourceApi.submitScrapeBatch(payload.actions)
    registerScrapeBatch(resp.data?.results || [])
    return resp
  }

  async function batchDelete(avids = [], action = 'delete-all') {
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

  // 提交下载
  async function submitDownload(avid) {
    if (!avid) return null
    setDownloadState(avid, 'submitting')
    try {
      const response = await downloadApi.submitDownload(avid)
      setDownloadState(avid, 'downloading')
      return response
    } catch (err) {
      if (err && err.code === 409) {
        updateResourceDownloadStatus(avid, true)
      } else {
        clearDownloadState(avid)
      }
      throw err
    }
  }

  async function batchSubmitDownload(avids = []) {
    if (!Array.isArray(avids) || avids.length === 0) return
    for (const avid of avids) {
      setDownloadState(avid, 'submitting')
    }
    try {
      const resp = await downloadApi.batchSubmit(avids)
      for (const avid of avids) {
        setDownloadState(avid, 'downloading')
      }
      return resp
    } catch (err) {
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
      console.debug('[resource] 更新资源下载状态:', avid, hasVideo)
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
    getScrapeJobForAvid,
    dismissScrapeJob,
    stopScrapeTracking,
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
