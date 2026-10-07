import { runRecommendationJob } from '../lib/recommendationJob.js'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import { actorApi, genreApi, recommendationApi } from '../../../api/index.js'

function mergeItems(existingItems, nextItems) {
  const merged = []
  const seen = new Set()
  for (const item of [...(existingItems || []), ...(nextItems || [])]) {
    if (!item?.avid || seen.has(item.avid)) continue
    seen.add(item.avid)
    merged.push(item)
  }
  return merged
}

export const useRecommendationsStore = defineStore('recommendations', () => {
  const activeJobId = ref('')
  const jobState = ref('')
  let controller = null
  const guard = createRequestGuard()
  const metricsGuard = createRequestGuard()
  const loading = ref(false),
    error = ref('')
  const items = ref([])
  const seeds = ref([])
  const meta = ref(null)
  const metrics = ref(null)
  const feedbackByAvid = ref({})
  const blockedAvids = ref(new Set())

  async function fetchRecommendations(params, { append = false } = {}) {
    cancelQuery()
    const request = guard.begin()
    const currentController = new AbortController()
    controller = currentController
    jobState.value = 'queued'
    loading.value = true
    error.value = ''
    try {
      const response = await runRecommendationJob(recommendationApi, params, {
        signal: currentController.signal,
        onJob: (id) => {
          if (guard.current(request)) activeJobId.value = id
        },
        onSnapshot: (snapshot) => {
          if (guard.current(request)) jobState.value = snapshot.state
        },
      })
      if (!guard.current(request) || !response) return null
      const payload = response.data || {}
      items.value = append ? mergeItems(items.value, payload.items) : payload.items || []
      seeds.value = [...(payload.seeds || [])]
      meta.value = payload.meta || null
      return payload
    } catch (err) {
      if (!guard.current(request)) return null
      if (activeJobId.value) recommendationApi.cancelJob(activeJobId.value).catch(() => {})
      error.value = err.message || '获取推荐失败'
      if (!append) {
        items.value = []
        seeds.value = []
      }
      throw err
    } finally {
      if (guard.current(request)) {
        loading.value = false
        activeJobId.value = ''
        controller = null
      }
    }
  }
  function cancelQuery() {
    const id = activeJobId.value
    activeJobId.value = ''
    controller?.abort()
    controller = null
    if (id) recommendationApi.cancelJob(id).catch(() => {})
    guard.invalidate()
    metricsGuard.invalidate()
    loading.value = false
  }
  async function cancelRecommendation() {
    const id = activeJobId.value
    if (!id) {
      cancelQuery()
      return
    }
    // Keep polling and allow retry when server cancellation could not be confirmed.
    await recommendationApi.cancelJob(id)
    if (activeJobId.value === id) cancelQuery()
  }
  async function loadMetrics() {
    const request = metricsGuard.begin()
    const response = await recommendationApi.getMetrics()
    if (!metricsGuard.current(request)) return null
    metrics.value = response.data || null
    return metrics.value
  }

  async function loadBlacklist(type, params, blockedOnly) {
    const response =
      type === 'actor'
        ? await actorApi.getList(params)
        : type === 'genre'
          ? await genreApi.getList(params)
          : await recommendationApi.getAvidBlocklist(params)
    const items = Array.isArray(response.data) ? response.data : []
    return {
      items: blockedOnly && type !== 'resource' ? items.filter((item) => item.is_blocked) : items,
      pagination: response.pagination || null,
    }
  }

  async function setSeedBlocked(type, id, blocked) {
    const payload = { seed_type: type, id }
    if (blocked) return recommendationApi.blockSeed({ ...payload, reason: 'manual' })
    return recommendationApi.unblockSeed(payload)
  }

  async function setAvidBlocked(avid, blocked) {
    if (blocked) await recommendationApi.blockAvid({ avid, reason: 'manual' })
    else await recommendationApi.unblockAvid({ avid })
    const next = new Set(blockedAvids.value)
    if (blocked) next.add(avid)
    else next.delete(avid)
    blockedAvids.value = next
  }

  async function submitFeedback(item, feedbackType) {
    const response = await recommendationApi.submitFeedback({
      snapshot_id: item.snapshot_id,
      avid: item.avid,
      feedback: feedbackType,
    })
    const savedFeedback = response.data?.feedback || ''
    const next = { ...feedbackByAvid.value }
    if (feedbackType === 'clear') delete next[item.avid]
    else if (savedFeedback) next[item.avid] = savedFeedback
    feedbackByAvid.value = next
    return savedFeedback
  }

  async function resetHistory() {
    await recommendationApi.resetState({ preserve_blocklist: true })
  }

  function clearResults() {
    cancelQuery()
    items.value = []
    seeds.value = []
    meta.value = null
    feedbackByAvid.value = {}
    blockedAvids.value = new Set()
  }

  return {
    loading,
    activeJobId,
    jobState,
    cancelRecommendation,
    error,
    cancelQuery,
    items,
    seeds,
    meta,
    metrics,
    feedbackByAvid,
    blockedAvids,
    fetchRecommendations,
    loadMetrics,
    loadBlacklist,
    setSeedBlocked,
    setAvidBlocked,
    submitFeedback,
    resetHistory,
    clearResults,
  }
})
