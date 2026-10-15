<script setup>
import { useRecommendationAdds } from '../features/recommendations/composables/useRecommendationAdds.js'
import InfoDialog from '../shared/ui/InfoDialog.vue'
import { useRecommendationElapsed } from '../features/recommendations/composables/useRecommendationElapsed.js'
import RecommendationContext from '../features/recommendations/components/RecommendationContext.vue'
import RecommendationInformation from '../features/recommendations/components/RecommendationInformation.vue'
import AppButton from '../shared/ui/AppButton.vue'
import PageLoad from '../shared/ui/PageLoad.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useSessionStore } from '../features/auth/stores/session.js'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import RecommendationPreferences from '../features/recommendations/components/RecommendationPreferences.vue'
import RecommendationCard from '../features/recommendations/components/RecommendationCard.vue'
import EmptyState from '../shared/ui/EmptyState.vue'
import RecommendationBlacklist from '../features/recommendations/components/RecommendationBlacklist.vue'
import { useRecommendationsStore } from '../features/recommendations/stores/recommendations.js'
import {
  saveRecommendationViewState,
  restoreRecommendationViewState,
  clearRecommendationViewState,
} from '../features/recommendations/stores/recommendationViewState.js'
import { useResourceStore } from '../features/resources/stores/resource.js'
import { useSettingsStore } from '../features/settings/stores/settings.js'
import { useToastStore } from '../shared/stores/toast.js'

const sessionStore = useSessionStore()
const pageOwner = sessionStore.sourceIdentity
const preferencesSaving = ref(false)
const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
const recommendationStore = useRecommendationsStore()
const { items, seeds, meta, metrics, blockedAvids, feedbackByAvid, loading, error, progress } =
  storeToRefs(recommendationStore)
const elapsedSeconds = useRecommendationElapsed(loading)
const resultElapsedSeconds = ref(null)
const settingsStore = useSettingsStore()
const toastStore = useToastStore()

const metricsLoading = ref(false)
const typePreference = ref(route.query.type_preference || 'balanced')
const actorPreference = ref(route.query.actor_preference || 'balanced')
const genrePreference = ref(route.query.genre_preference || 'balanced')
const limit = ref(Number.parseInt(route.query.limit, 10) || 12)
const addedAvids = ref(new Set())
const feedbackSubmittingAvids = ref(new Set())
const initialized = ref(false)
const hasRequested = ref(false)
const showScrollTop = ref(false)
const lastLoadedConfigKey = ref('')
const activeReasonAvid = ref('')
const showPersonalizationModal = ref(false)
const blacklistRef = ref(null)
function invalidateBlacklistCache(type = '') {
  blacklistRef.value?.invalidate(type)
}

const seedGroups = computed(() => {
  const groups = { actor: [], genre: [] }
  for (const seed of seeds.value || []) {
    if (seed.seed_type === 'actor') groups.actor.push(seed)
    else if (seed.seed_type === 'genre') groups.genre.push(seed)
  }
  return groups
})

const visibleItems = computed(() => items.value || [])
const resultDisplayStyle = computed(() =>
  settingsStore.searchResultDisplayStyle === 'masonry' ? 'masonry' : 'grid'
)
const showInitialLoading = computed(() => loading.value && !visibleItems.value.length)

const metricCards = computed(() => {
  const data = metrics.value || {}
  return [
    {
      key: 'snapshots',
      label: '推荐批次',
      value: formatMetricNumber(data.snapshot_count),
    },
    {
      key: 'repeat',
      label: '重复率',
      value: formatPercent(data.repeat_rate),
    },
    {
      key: 'like',
      label: '喜欢',
      value: formatMetricNumber(data.feedback_counts?.like),
    },
    {
      key: 'dislike',
      label: '不喜欢',
      value: formatMetricNumber(data.feedback_counts?.dislike),
    },
    {
      key: 'blocked',
      label: '黑名单',
      value: formatMetricNumber(data.avid_blocklist_count),
    },
  ]
})

const recommendationActionLabel = computed(() => {
  if (visibleItems.value.length && lastLoadedConfigKey.value !== buildConfigKey()) {
    return '重新推荐'
  }
  return hasRequested.value ? '继续推荐' : '开始推荐'
})

function buildConfigKey() {
  return JSON.stringify({
    type_preference: typePreference.value || 'balanced',
    actor_preference: actorPreference.value || 'balanced',
    genre_preference: genrePreference.value || 'balanced',
    limit: limit.value || 24,
  })
}

function formatMetricNumber(value) {
  const parsed = Number(value || 0)
  if (!Number.isFinite(parsed) || parsed <= 0) return '0'
  return parsed.toLocaleString('zh-CN')
}

function formatPercent(value) {
  const parsed = Number(value || 0)
  if (!Number.isFinite(parsed) || parsed <= 0) return '0%'
  return `${(parsed * 100).toFixed(1)}%`
}

function serializeSet(value) {
  return Array.from(value || [])
}

function saveViewState() {
  if (
    !initialized.value ||
    sessionStore.status !== 'authenticated' ||
    sessionStore.sourceIdentity !== pageOwner
  )
    return
  const state = {
    typePreference: typePreference.value,
    actorPreference: actorPreference.value,
    genrePreference: genrePreference.value,
    limit: limit.value,
    items: items.value || [],
    seeds: seeds.value || [],
    meta: meta.value || null,
    metrics: metrics.value || null,
    hasRequested: hasRequested.value,
    lastLoadedConfigKey: lastLoadedConfigKey.value,
    addedAvids: serializeSet(addedAvids.value),
    blockedAvids: serializeSet(blockedAvids.value),
    feedbackByAvid: feedbackByAvid.value || {},
    scrollY: window.scrollY || 0,
    elapsedSeconds: resultElapsedSeconds.value,
  }
  saveRecommendationViewState(state, window.sessionStorage, pageOwner)
}

function restoreViewState() {
  const state = restoreRecommendationViewState(window.sessionStorage, pageOwner)
  if (!state) return null

  items.value = Array.isArray(state.items) ? state.items : []
  seeds.value = Array.isArray(state.seeds) ? state.seeds : []
  resultElapsedSeconds.value = Number.isFinite(state.elapsedSeconds) ? state.elapsedSeconds : null
  meta.value = state.meta || null
  metrics.value = state.metrics || null
  hasRequested.value = Boolean(state.hasRequested)
  lastLoadedConfigKey.value = state.lastLoadedConfigKey || ''
  addedAvids.value = new Set(Array.isArray(state.addedAvids) ? state.addedAvids : [])
  blockedAvids.value = new Set(Array.isArray(state.blockedAvids) ? state.blockedAvids : [])
  feedbackByAvid.value =
    state.feedbackByAvid && typeof state.feedbackByAvid === 'object' ? state.feedbackByAvid : {}
  return state
}

function updateScrollState() {
  showScrollTop.value = window.scrollY > 360
}

function syncActiveReasonItem() {
  if (!activeReasonAvid.value) return
  const exists = visibleItems.value.some((item) => item.avid === activeReasonAvid.value)
  if (!exists) {
    activeReasonAvid.value = ''
  }
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function clearPageRecommendations() {
  recommendationStore.clearResults()
  error.value = ''
  hasRequested.value = false
  lastLoadedConfigKey.value = ''
  resultElapsedSeconds.value = null
  closeReasonPanel()
}

async function loadRecommendationMetrics() {
  metricsLoading.value = true
  try {
    await recommendationStore.loadMetrics()
  } catch (err) {
    toastStore.error(err.message || '加载推荐指标失败')
  } finally {
    metricsLoading.value = false
  }
}

function openPersonalizationModal() {
  showPersonalizationModal.value = true
}

function closePersonalizationModal() {
  showPersonalizationModal.value = false
}

function closeReasonPanel() {
  activeReasonAvid.value = ''
}

function toggleReasonPanel(item) {
  if (!item?.avid || !item.reasons?.length) return
  if (activeReasonAvid.value === item.avid) {
    closeReasonPanel()
    return
  }

  activeReasonAvid.value = item.avid
}

function syncQuery() {
  const query = {}
  if (typePreference.value && typePreference.value !== 'balanced') {
    query.type_preference = typePreference.value
  }
  if (actorPreference.value && actorPreference.value !== 'balanced') {
    query.actor_preference = actorPreference.value
  }
  if (genrePreference.value && genrePreference.value !== 'balanced') {
    query.genre_preference = genrePreference.value
  }
  if (limit.value !== 12) query.limit = limit.value
  router.replace({ query })
}

async function loadRecommendations(options = {}) {
  const forceRefreshExternal = Boolean(options.forceRefreshExternal)
  const append = Boolean(options.append)
  hasRequested.value = true
  const requestConfigKey = buildConfigKey()
  const shouldMerge = append && !forceRefreshExternal && items.value.length > 0
  try {
    const payload = await recommendationStore.fetchRecommendations(
      {
        type_preference: typePreference.value,
        actor_preference: actorPreference.value,
        genre_preference: genrePreference.value,
        limit: limit.value,
        exclude_existing: true,
        force_refresh_external: forceRefreshExternal,
      },
      { append: shouldMerge }
    )
    if (!payload) return
    resultElapsedSeconds.value = elapsedSeconds.value
    lastLoadedConfigKey.value = requestConfigKey
    loadRecommendationMetrics()
    syncActiveReasonItem()
  } catch {
    /* Store owns current query errors and results. */
  }
}

function runPrimaryRecommendationAction() {
  const requestConfigKey = buildConfigKey()
  const canAppend =
    requestConfigKey === lastLoadedConfigKey.value && hasRequested.value && items.value.length > 0
  loadRecommendations({ append: canAppend })
}

function continueRecommendations() {
  loadRecommendations({ append: true })
}

const { adding: addingAvids, add: handleAdd } = useRecommendationAdds({
  added: addedAvids,
  jobs: () => resourceStore.visibleScrapeJobs,
  submit: (avid) => resourceStore.addResource(avid, 'any'),
  onAdded: (item) => persistRecommendationFeedback(item, 'like'),
  onExisting: (item) => toastStore.info(`${item.avid} 已存在于资源库`),
  onError: (error) => toastStore.error(error.message || '添加资源失败'),
})

async function persistRecommendationFeedback(item, feedbackType) {
  if (!item?.avid || !item?.snapshot_id || !['like', 'dislike', 'clear'].includes(feedbackType)) {
    return ''
  }

  const savedFeedback = await recommendationStore.submitFeedback(item, feedbackType)
  loadRecommendationMetrics()
  return savedFeedback
}

async function handleFeedback(item, feedbackType) {
  if (!item?.avid || !item?.snapshot_id || feedbackSubmittingAvids.value.has(item.avid)) return
  if (!['like', 'dislike'].includes(feedbackType)) return

  const nextSubmitting = new Set(feedbackSubmittingAvids.value)
  nextSubmitting.add(item.avid)
  feedbackSubmittingAvids.value = nextSubmitting

  try {
    const currentFeedback = feedbackByAvid.value[item.avid] || ''
    const nextFeedback = currentFeedback === feedbackType ? 'clear' : feedbackType
    const savedFeedback = await persistRecommendationFeedback(item, nextFeedback)
    if (nextFeedback === 'clear') {
      toastStore.success(`${item.avid} 已取消反馈`)
    } else {
      toastStore.success(
        savedFeedback === 'like' ? `${item.avid} 已标记喜欢` : `${item.avid} 已标记不喜欢`
      )
    }
  } catch (err) {
    toastStore.error(err.message || '提交推荐反馈失败')
  } finally {
    const done = new Set(feedbackSubmittingAvids.value)
    done.delete(item.avid)
    feedbackSubmittingAvids.value = done
  }
}

async function handleBlockRecommendation(item) {
  if (!item?.avid || feedbackSubmittingAvids.value.has(item.avid)) return

  const nextSubmitting = new Set(feedbackSubmittingAvids.value)
  nextSubmitting.add(item.avid)
  feedbackSubmittingAvids.value = nextSubmitting

  try {
    if (blockedAvids.value.has(item.avid)) {
      await recommendationStore.setAvidBlocked(item.avid, false)
      invalidateBlacklistCache('resource')
      loadRecommendationMetrics()
      toastStore.success(`${item.avid} 已移出黑名单`)
      return
    }

    try {
      await persistRecommendationFeedback(item, 'dislike')
    } catch (_feedbackError) {
      // 黑名单是更强的显式操作，反馈失败时仍继续屏蔽 AVID。
    }
    await recommendationStore.setAvidBlocked(item.avid, true)
    feedbackByAvid.value = {
      ...feedbackByAvid.value,
      [item.avid]: 'dislike',
    }
    invalidateBlacklistCache('resource')
    loadRecommendationMetrics()
    toastStore.success(`${item.avid} 已加入黑名单`)
  } catch (err) {
    toastStore.error(err.message || '加入黑名单失败')
  } finally {
    const done = new Set(feedbackSubmittingAvids.value)
    done.delete(item.avid)
    feedbackSubmittingAvids.value = done
  }
}

function handleResetRecommendations() {
  error.value = ''
  clearPageRecommendations()
  invalidateBlacklistCache()
  clearRecommendationViewState(window.sessionStorage, pageOwner)
  toastStore.success('当前推荐列表已清空')
}

async function cancelRecommendation() {
  try {
    await recommendationStore.cancelRecommendation()
  } catch (err) {
    toastStore.error(err.message || '取消推荐失败，请重试')
  }
}

async function handleResetRecommendationHistory() {
  if (loading.value || metricsLoading.value) return
  try {
    await recommendationStore.resetHistory()
    clearPageRecommendations()
    invalidateBlacklistCache()
    clearRecommendationViewState(window.sessionStorage, pageOwner)
    await loadRecommendationMetrics()
    toastStore.success('推荐历史已重置，黑名单已保留')
  } catch (err) {
    toastStore.error(err.message || '重置推荐历史失败')
  }
}

function handleOpen(item) {
  if (!item?.detail_url) return
  window.open(item.detail_url, '_blank', 'noopener,noreferrer')
}

function handleView(item) {
  if (!item?.avid) return
  router.push(`/resource/${item.avid}`)
}

function handleGlobalKeydown(event) {
  if (event.key === 'Escape') {
    if (showPersonalizationModal.value) {
      closePersonalizationModal()
      return
    }
    closeReasonPanel()
  }
}

async function savePreferences() {
  preferencesSaving.value = true
  settingsStore.recommendationPreferences = {
    type_preference: typePreference.value,
    actor_preference: actorPreference.value,
    genre_preference: genrePreference.value,
    limit: limit.value,
  }
  try {
    const result = await settingsStore.saveSettings()
    if (pageActive && result.success) toastStore.success('推荐偏好已保存')
  } catch {
    if (pageActive) toastStore.error('推荐偏好保存失败，请重试')
  } finally {
    if (pageActive) preferencesSaving.value = false
  }
}

function handleViewportResize() {
  updateScrollState()
}

watch([typePreference, actorPreference, genrePreference, limit], () => {
  if (!initialized.value) return
  syncQuery()
})

// A hard reload does not reliably unmount Vue; persist each settled batch and view change.
watch(
  [
    initialized,
    loading,
    items,
    seeds,
    meta,
    metrics,
    addedAvids,
    blockedAvids,
    feedbackByAvid,
    typePreference,
    actorPreference,
    genrePreference,
    limit,
    hasRequested,
    lastLoadedConfigKey,
    resultElapsedSeconds,
  ],
  () => {
    if (initialized.value && !loading.value) saveViewState()
  },
  { deep: true, flush: 'post' }
)
let pageActive = true
onMounted(async () => {
  await settingsStore.loadSettings()
  if (!pageActive) return
  typePreference.value =
    route.query.type_preference || settingsStore.recommendationPreferences.type_preference
  actorPreference.value =
    route.query.actor_preference || settingsStore.recommendationPreferences.actor_preference
  genrePreference.value =
    route.query.genre_preference || settingsStore.recommendationPreferences.genre_preference
  limit.value =
    Number.parseInt(route.query.limit, 10) || settingsStore.recommendationPreferences.limit
  const restoredState = restoreViewState()
  loadRecommendationMetrics()
  initialized.value = true
  syncQuery()
  if (restoredState?.scrollY) {
    await nextTick()
    window.scrollTo({ top: restoredState.scrollY, left: 0, behavior: 'auto' })
  }
  if (!pageActive) return
  updateScrollState()
  window.addEventListener('pagehide', saveViewState)
  window.addEventListener('scroll', updateScrollState, { passive: true })
  window.addEventListener('resize', handleViewportResize)
  window.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  recommendationStore.cancelQuery()
  saveViewState()
  pageActive = false
  window.removeEventListener('pagehide', saveViewState)
  window.removeEventListener('scroll', updateScrollState)
  window.removeEventListener('resize', handleViewportResize)
  window.removeEventListener('keydown', handleGlobalKeydown)
})
</script>

<template>
  <div class="recommendations-view">
    <section class="page-header">
      <div>
        <h1 class="text-3xl font-bold text-primary">推荐发现</h1>
        <div class="flex items-center gap-2 mt-2">
          <p class="text-secondary">发现符合偏好的资源</p>
          <InfoDialog title="推荐信息" label="查看推荐信息">
            <RecommendationInformation
              :cards="metricCards"
              :metrics-loading="metricsLoading"
              :loading="loading"
              @refresh-metrics="loadRecommendationMetrics"
              @reset-history="handleResetRecommendationHistory"
            />
          </InfoDialog>
        </div>
      </div>

      <div class="header-actions">
        <AppButton
          class="rec-action-btn"
          :loading="loading"
          :disabled="!initialized"
          @click="runPrimaryRecommendationAction"
        >
          {{ recommendationActionLabel }}
        </AppButton>
        <AppButton
          v-if="loading"
          variant="danger"
          class="rec-action-btn"
          @click="cancelRecommendation"
        >
          取消推荐
        </AppButton>
        <AppButton
          variant="neutral"
          class="rec-action-btn"
          :disabled="!initialized || loading"
          @click="handleResetRecommendations"
          >清空页面</AppButton
        >
        <AppButton
          variant="neutral"
          class="rec-action-btn"
          aria-label="个性化"
          :disabled="!initialized"
          @click="openPersonalizationModal"
          >个性化</AppButton
        >
      </div>
    </section>

    <RecommendationContext
      :statistics="
        loading ? progress || { verified_count: 0, candidate_count: 0 } : meta?.verification_context
      "
      :elapsed-seconds="loading ? elapsedSeconds : resultElapsedSeconds"
      :groups="seedGroups"
    />
    <section class="content-shell">
      <PageLoad v-if="showInitialLoading" text="正在加载推荐" />

      <EmptyState
        v-if="!showInitialLoading && !hasRequested && !visibleItems.length"
        icon="star"
        title="尚未开始推荐"
        description="设置偏好，开始推荐"
      />

      <EmptyState
        v-else-if="!loading && !visibleItems.length"
        icon="star"
        title="暂未获得推荐结果"
        description="调整偏好，或点击下方按钮继续推荐。"
      />

      <div v-else class="results-stack">
        <div
          class="recommendation-grid"
          :class="{
            'standard-layout': resultDisplayStyle === 'grid',
            'masonry-layout': resultDisplayStyle === 'masonry',
          }"
        >
          <div v-for="item in visibleItems" :key="item.avid" class="recommendation-slot">
            <RecommendationCard
              :item="item"
              :adding="addingAvids.has(item.avid)"
              :added="addedAvids.has(item.avid)"
              :blocked="blockedAvids.has(item.avid)"
              :feedback="feedbackByAvid[item.avid] || ''"
              :feedback-submitting="feedbackSubmittingAvids.has(item.avid)"
              :layout-style="resultDisplayStyle"
              :reasons-open="activeReasonAvid === item.avid"
              @add="handleAdd(item)"
              @block="handleBlockRecommendation(item)"
              @feedback="handleFeedback(item, $event)"
              @open="handleOpen(item)"
              @view="handleView(item)"
              @reasons="toggleReasonPanel(item)"
            />
            <transition name="reason-panel-fade">
              <aside v-if="activeReasonAvid === item.avid" class="reason-floating-panel">
                <div class="reason-panel-header">
                  <div>
                    <div class="reason-panel-eyebrow">Recommendation Notes</div>
                  </div>
                  <AppButton
                    variant="neutral"
                    class="reason-panel-close"
                    type="button"
                    @click="closeReasonPanel"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="2"
                        d="M6 18L18 6M6 6l12 12"
                      ></path>
                    </svg>
                  </AppButton>
                </div>
                <div class="reason-panel-score">
                  推荐评分 {{ Number(item.score || 0).toFixed(1) }}
                </div>

                <div class="reason-panel-list">
                  <div v-for="reason in item.reasons || []" :key="reason" class="reason-panel-item">
                    {{ reason }}
                  </div>
                </div>
              </aside>
            </transition>
          </div>
        </div>
      </div>
      <div v-if="hasRequested" class="results-footer">
        <AppButton
          variant="neutral"
          class="rec-footer-btn min-w-[10rem]"
          :loading="loading"
          @click="continueRecommendations"
          >继续推荐</AppButton
        >
        <p
          v-if="error && !loading"
          role="status"
          class="text-muted text-xs text-center max-w-full break-words"
        >
          {{ error }}
        </p>
      </div>
    </section>

    <AppButton
      variant="primary"
      v-if="showScrollTop"
      class="scroll-top-btn"
      type="button"
      aria-label="回到顶部"
      @click="scrollToTop"
    >
      <svg
        class="w-5 h-5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        aria-hidden="true"
      >
        <path d="m6 12 6-6 6 6M12 6v12" />
      </svg>
    </AppButton>

    <RecommendationBlacklist
      ref="blacklistRef"
      :show="showPersonalizationModal"
      title="个性化"
      @close="closePersonalizationModal"
    >
      <template #preferences>
        <RecommendationPreferences
          v-model:type-preference="typePreference"
          v-model:actor-preference="actorPreference"
          v-model:genre-preference="genrePreference"
          v-model:limit="limit"
        />
        <AppButton class="mt-3" :loading="preferencesSaving" @click="savePreferences"
          >保存推荐偏好</AppButton
        >
      </template>
    </RecommendationBlacklist>
  </div>
</template>

<style src="../features/recommendations/styles/recommendationPage.css"></style>
