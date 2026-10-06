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
    const request = guard.begin()
    loading.value = true
    error.value = ''
    try {
      const response = await recommendationApi.getList(params)
      if (!guard.current(request)) return null
      const payload = response.data || {}
      items.value = append ? mergeItems(items.value, payload.items) : payload.items || []
      seeds.value = [...(payload.seeds || [])]
      meta.value = payload.meta || null
      return payload
    } catch (err) {
      if (!guard.current(request)) return null
      error.value = err.message || '获取推荐失败'
      if (!append) {
        items.value = []
        seeds.value = []
      }
      throw err
    } finally {
      if (guard.current(request)) loading.value = false
    }
  }
  function cancelQuery() {
    guard.invalidate()
    metricsGuard.invalidate()
    loading.value = false
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
