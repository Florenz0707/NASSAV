<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import CustomSelect from '../components/CustomSelect.vue'
import RecommendationCard from '../components/RecommendationCard.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import RecommendationBlacklist from '../components/RecommendationBlacklist.vue'
import { useRecommendationsStore } from '../stores/recommendations'
import {
  saveRecommendationViewState,
  restoreRecommendationViewState,
  clearRecommendationViewState,
} from '../stores/recommendationViewState'
import { useResourceStore } from '../stores/resource'
import { useSettingsStore } from '../stores/settings'
import { useToastStore } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
const recommendationStore = useRecommendationsStore()
const { items, seeds, meta, metrics, blockedAvids, feedbackByAvid, loading, error } =
  storeToRefs(recommendationStore)
const settingsStore = useSettingsStore()
const toastStore = useToastStore()

const metricsLoading = ref(false)
const typePreference = ref(route.query.type_preference || 'balanced')
const actorPreference = ref(route.query.actor_preference || 'balanced')
const genrePreference = ref(route.query.genre_preference || 'balanced')
const limit = ref(Number.parseInt(route.query.limit, 10) || 12)
const addingAvids = ref(new Set())
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
const typePreferenceOptions = [
  { value: 'actor_heavy', label: '演员' },
  { value: 'balanced', label: '平衡' },
  { value: 'genre_heavy', label: '类别' },
]
const actorPreferenceOptions = [
  { value: 'familiar', label: '熟悉' },
  { value: 'balanced', label: '平衡' },
  { value: 'rare', label: '少见' },
]
const genrePreferenceOptions = [
  { value: 'familiar', label: '熟悉' },
  { value: 'balanced', label: '平衡' },
  { value: 'rare', label: '少见' },
]
const limitOptions = [
  { value: 12, label: '12' },
  { value: 24, label: '24' },
  { value: 36, label: '36' },
]

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
  }
  saveRecommendationViewState(state)
}

function restoreViewState() {
  const state = restoreRecommendationViewState()
  if (!state) return null

  typePreference.value = state.typePreference || typePreference.value
  actorPreference.value = state.actorPreference || actorPreference.value
  genrePreference.value = state.genrePreference || genrePreference.value
  limit.value = Number.parseInt(state.limit, 10) || 24
  items.value = Array.isArray(state.items) ? state.items : []
  seeds.value = Array.isArray(state.seeds) ? state.seeds : []
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

function refreshExternalRecommendations() {
  loadRecommendations({ forceRefreshExternal: true })
}

const pendingRecommendationAdds = new Map()
watch(
  () => resourceStore.visibleScrapeJobs,
  (jobs) => {
    for (const job of jobs) {
      const item = pendingRecommendationAdds.get(job.avid)
      if (!item || job.action !== 'add' || (job.state !== 'succeeded' && job.state !== 'failed'))
        continue
      pendingRecommendationAdds.delete(job.avid)
      if (job.state === 'succeeded') {
        const added = new Set(addedAvids.value)
        added.add(job.avid)
        addedAvids.value = added
        persistRecommendationFeedback(item, 'like').catch(() => {})
      }
    }
  }
)

async function handleAdd(item) {
  if (!item?.avid || addingAvids.value.has(item.avid)) return

  const next = new Set(addingAvids.value)
  next.add(item.avid)
  addingAvids.value = next

  try {
    await resourceStore.addResource(item.avid, 'any')

    pendingRecommendationAdds.set(item.avid, item)
  } catch (err) {
    if (err.code === 409) {
      toastStore.info(`${item.avid} 已存在于资源库`)
      const added = new Set(addedAvids.value)
      added.add(item.avid)
      addedAvids.value = added
      persistRecommendationFeedback(item, 'like').catch(() => {})
      return
    }
    toastStore.error(err.message || '添加资源失败')
  } finally {
    const done = new Set(addingAvids.value)
    done.delete(item.avid)
    addingAvids.value = done
  }
}

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
  clearRecommendationViewState()
  toastStore.success('当前推荐列表已清空')
}

async function handleResetRecommendationHistory() {
  if (loading.value || metricsLoading.value) return
  try {
    await recommendationStore.resetHistory()
    clearPageRecommendations()
    invalidateBlacklistCache()
    clearRecommendationViewState()
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

function handleViewportResize() {
  updateScrollState()
}

watch([typePreference, actorPreference, genrePreference, limit], () => {
  if (!initialized.value) return
  syncQuery()
})

onMounted(async () => {
  await settingsStore.loadSettings()
  const restoredState = restoreViewState()
  loadRecommendationMetrics()
  initialized.value = true
  syncQuery()
  if (restoredState?.scrollY) {
    await nextTick()
    window.scrollTo({ top: restoredState.scrollY, left: 0, behavior: 'auto' })
  }
  updateScrollState()
  window.addEventListener('scroll', updateScrollState, { passive: true })
  window.addEventListener('resize', handleViewportResize)
  window.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  recommendationStore.cancelQuery()
  saveViewState()
  window.removeEventListener('scroll', updateScrollState)
  window.removeEventListener('resize', handleViewportResize)
  window.removeEventListener('keydown', handleGlobalKeydown)
})
</script>

<template>
  <div class="recommendations-view">
    <section class="page-header">
      <div>
        <div class="eyebrow">Discover</div>
        <h1 class="page-title">推荐发现</h1>
      </div>

      <div class="header-actions">
        <button
          class="rec-action-btn rec-action-btn-primary"
          :disabled="loading"
          @click="runPrimaryRecommendationAction"
        >
          <LoadingSpinner v-if="loading" size="small" />
          <template v-else>{{ recommendationActionLabel }}</template>
        </button>
        <button class="rec-action-btn rec-action-btn-secondary" @click="openPersonalizationModal">
          个性化
        </button>
        <button
          class="rec-action-btn rec-action-btn-secondary"
          :disabled="loading"
          @click="refreshExternalRecommendations"
        >
          刷新外部结果
        </button>
        <button
          class="rec-action-btn rec-action-btn-muted"
          :disabled="loading"
          @click="handleResetRecommendations"
        >
          清空页面
        </button>
        <button
          class="rec-action-btn rec-action-btn-muted"
          :disabled="loading || metricsLoading"
          @click="handleResetRecommendationHistory"
        >
          重置历史
        </button>
      </div>
    </section>

    <section class="meta-strip">
      <div class="meta-card">
        <label for="recommendation-type" class="meta-label">种子偏好</label>
        <div class="meta-control">
          <CustomSelect
            id="recommendation-type"
            aria-label="种子偏好"
            v-model="typePreference"
            :options="typePreferenceOptions"
            class="meta-select"
            full-width
          />
        </div>
        <p class="meta-desc">控制演员种子与类别种子的整体权重倾向。</p>
      </div>
      <div class="meta-card strategy-card">
        <label for="recommendation-actor" class="meta-label">演员偏好</label>
        <div class="meta-control">
          <CustomSelect
            id="recommendation-actor"
            aria-label="演员偏好"
            v-model="actorPreference"
            :options="actorPreferenceOptions"
            class="meta-select"
            full-width
          />
        </div>
        <p class="meta-desc">控制演员种子“熟悉/平衡/少见”偏好，叠加种子轮换抑制。</p>
      </div>
      <div class="meta-card strategy-card">
        <label for="recommendation-genre" class="meta-label">类别偏好</label>
        <div class="meta-control">
          <CustomSelect
            id="recommendation-genre"
            aria-label="类别偏好"
            v-model="genrePreference"
            :options="genrePreferenceOptions"
            class="meta-select"
            full-width
          />
        </div>
        <p class="meta-desc">控制类别种子“熟悉/平衡/少见”偏好，叠加种子轮换抑制。</p>
      </div>
      <div class="meta-card">
        <label for="recommendation-limit" class="meta-label">返回数量</label>
        <div class="meta-control">
          <CustomSelect
            id="recommendation-limit"
            aria-label="返回数量"
            v-model="limit"
            :options="limitOptions"
            class="meta-select"
            full-width
          />
        </div>
        <p class="meta-desc">默认返回 24 条推荐结果。</p>
      </div>
    </section>

    <section class="metrics-panel">
      <div v-for="card in metricCards" :key="card.key" class="metrics-card">
        <span class="metrics-label">{{ card.label }}</span>
        <span class="metrics-value">{{ metricsLoading ? '...' : card.value }}</span>
      </div>
      <button
        class="metrics-refresh-btn"
        type="button"
        :disabled="metricsLoading"
        aria-label="刷新推荐指标"
        @click="loadRecommendationMetrics"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M4 4v6h6M20 20v-6h-6M5.64 18.36A9 9 0 0 0 18.36 5.64M18.36 5.64H14M5.64 18.36H10"
          ></path>
        </svg>
      </button>
    </section>

    <section v-if="seeds.length" class="seed-panel">
      <div class="seed-section">
        <h2 class="seed-title">高频演员</h2>
        <div class="seed-list">
          <span
            v-for="seed in seedGroups.actor"
            :key="`${seed.seed_type}-${seed.value}`"
            class="seed-pill"
          >
            {{ seed.value }} · {{ seed.resource_count }}
          </span>
        </div>
      </div>

      <div class="seed-section">
        <h2 class="seed-title">高频类别</h2>
        <div class="seed-list">
          <span
            v-for="seed in seedGroups.genre"
            :key="`${seed.seed_type}-${seed.value}`"
            class="seed-pill secondary"
          >
            {{ seed.value }} · {{ seed.resource_count }}
          </span>
        </div>
      </div>
    </section>

    <section class="content-shell">
      <div v-if="showInitialLoading" class="loading-shell">
        <LoadingSpinner size="large" text="正在和妈妈桑交涉..." />
      </div>

      <EmptyState
        v-else-if="!hasRequested && !visibleItems.length"
        icon="star"
        title="尚未开始推荐"
        description="设置偏好，开始推荐"
      />

      <EmptyState
        v-else-if="error && !visibleItems.length"
        icon="warning"
        title="推荐加载失败"
        :description="error"
      >
        <template #action>
          <button class="tw-btn-accent rec-primary-btn" @click="loadRecommendations">
            重新加载
          </button>
        </template>
      </EmptyState>

      <EmptyState
        v-else-if="!visibleItems.length"
        icon="star"
        title="暂时没有推荐结果"
        description="尝试添加本地资源，或者稍后重试。"
      >
        <template #action>
          <button class="tw-btn-accent rec-primary-btn" @click="loadRecommendations">
            再试一次
          </button>
        </template>
      </EmptyState>

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
                  <button class="reason-panel-close" type="button" @click="closeReasonPanel">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="2"
                        d="M6 18L18 6M6 6l12 12"
                      ></path>
                    </svg>
                  </button>
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

        <div class="results-footer">
          <button
            class="tw-btn-footer rec-footer-btn"
            :disabled="loading"
            @click="continueRecommendations"
          >
            <LoadingSpinner v-if="loading" size="small" />
            <template v-else> 继续推荐 </template>
          </button>
        </div>
      </div>
    </section>

    <button
      v-if="showScrollTop"
      class="scroll-top-btn"
      type="button"
      aria-label="回到顶部"
      @click="scrollToTop"
    >
      ⩟
    </button>

    <RecommendationBlacklist
      ref="blacklistRef"
      :show="showPersonalizationModal"
      @close="closePersonalizationModal"
    />
  </div>
</template>

<style scoped>
.recommendations-view {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.5rem 1.75rem;
  border-radius: 1.5rem;
  background:
    radial-gradient(
      circle at top right,
      color-mix(in srgb, var(--accent-primary) 18%, transparent),
      transparent 34%
    ),
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--neutral-color) 5%, transparent),
      color-mix(in srgb, var(--neutral-color) 2%, transparent)
    );
  border: 1px solid color-mix(in srgb, var(--neutral-color) 8%, transparent);
  box-shadow: 0 18px 40px color-mix(in srgb, var(--shadow-color) 18%, transparent);
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  min-height: 1.85rem;
  padding: 0.2rem 0.7rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent-primary) 12%, transparent);
  color: var(--accent-primary);
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.page-title {
  margin: 0.8rem 0 0.35rem;
  color: var(--text-primary);
  font-size: clamp(2rem, 3vw, 2.8rem);
  font-weight: 700;
  letter-spacing: -0.03em;
}

.page-subtitle {
  margin: 0;
  max-width: 52rem;
  color: var(--text-muted);
  font-size: 1rem;
  line-height: 1.65;
}

.header-actions {
  display: inline-flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.rec-primary-btn {
  border-radius: 0.95rem;
}

.rec-action-btn {
  display: inline-flex;
  min-height: 2.9rem;
  min-width: 7.8rem;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  border-radius: 0.95rem;
  border: 1px solid transparent;
  padding: 0 1rem;
  font-weight: 700;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    background 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;
}

.rec-action-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.rec-action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.rec-action-btn-primary {
  color: var(--text-inverse);
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-primary));
  color: var(--on-accent);
  box-shadow: 0 10px 22px color-mix(in srgb, var(--accent-primary) 22%, transparent);
}

.rec-action-btn-secondary {
  color: var(--text-inverse);
  background: var(--accent-danger);
  box-shadow: 0 10px 22px color-mix(in srgb, var(--accent-secondary) 20%, transparent);
}

.rec-action-btn-muted {
  color: var(--text-secondary);
  border-color: color-mix(in srgb, var(--neutral-color) 16%, transparent);
  background: color-mix(in srgb, var(--neutral-color) 4%, transparent);
}

.meta-strip,
.metrics-panel,
.strategy-params-panel,
.seed-panel,
.content-shell {
  border-radius: 1.35rem;
  background: color-mix(in srgb, var(--neutral-color) 3%, transparent);
  border: 1px solid color-mix(in srgb, var(--neutral-color) 8%, transparent);
  box-shadow: 0 18px 38px color-mix(in srgb, var(--shadow-color) 14%, transparent);
}

.meta-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  padding: 1.1rem;
}

.meta-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  padding: 0.95rem 1rem;
  border-radius: 1rem;
  background: color-mix(in srgb, var(--neutral-color) 3%, transparent);
  border: 1px solid color-mix(in srgb, var(--neutral-color) 6%, transparent);
}

.meta-label {
  color: var(--text-muted);
  font-size: 0.8rem;
  margin-bottom: 0;
}

.meta-value {
  color: var(--text-primary);
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.4;
  min-height: 2.8rem;
  display: flex;
  align-items: flex-start;
}

.meta-desc {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.55;
  min-height: 3.9rem;
}

.meta-control {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-top: auto;
  width: 100%;
}

.meta-control-label {
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 600;
}

.meta-select {
  width: 100%;
  min-height: 2.6rem;
  font-size: 0.85rem;
  font-weight: 600;
  padding-left: 0.85rem;
}

.meta-select:focus {
  outline: none;
}

.strategy-card .meta-select:focus {
  border-color: color-mix(in srgb, var(--accent-tertiary) 35%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-tertiary) 12%, transparent);
}

.metrics-panel {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr)) auto;
  gap: 0.75rem;
  align-items: stretch;
  padding: 0.85rem;
}

.metrics-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.2rem;
  min-height: 4.4rem;
  padding: 0.75rem 0.85rem;
  border-radius: 0.95rem;
  background: color-mix(in srgb, var(--neutral-color) 3%, transparent);
  border: 1px solid color-mix(in srgb, var(--neutral-color) 6%, transparent);
}

.metrics-label {
  color: var(--text-muted);
  font-size: 0.76rem;
}

.metrics-value {
  color: var(--text-primary);
  font-size: 1.25rem;
  font-weight: 800;
  line-height: 1.2;
}

.metrics-refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  min-height: 4.4rem;
  border-radius: 0.95rem;
  border: 1px solid color-mix(in srgb, var(--neutral-color) 12%, transparent);
  background: color-mix(in srgb, var(--neutral-color) 4%, transparent);
  color: var(--text-secondary);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    color 0.2s ease,
    background 0.2s ease;
}

.metrics-refresh-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  color: var(--text-primary);
  background: color-mix(in srgb, var(--neutral-color) 7%, transparent);
}

.metrics-refresh-btn:disabled {
  cursor: progress;
  opacity: 0.7;
}

.seed-panel {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  padding: 1.15rem;
}

.strategy-params-panel {
  display: flex;
  flex-direction: column;
  gap: 0.95rem;
  padding: 1.1rem;
}

.strategy-params-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.strategy-params-header-main {
  display: flex;
  align-items: baseline;
  gap: 0.7rem;
  flex-wrap: wrap;
}

.strategy-params-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.04rem;
  font-weight: 700;
}

.strategy-params-subtitle {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.strategy-params-toggle {
  min-height: 2.1rem;
  padding: 0.3rem 0.75rem;
  border-radius: 0.85rem;
  border: 1px solid color-mix(in srgb, var(--neutral-color) 12%, transparent);
  background: color-mix(in srgb, var(--neutral-color) 4%, transparent);
  color: var(--text-primary);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
}

.strategy-params-toggle:hover {
  border-color: color-mix(in srgb, var(--neutral-color) 20%, transparent);
  background: color-mix(in srgb, var(--neutral-color) 7%, transparent);
}

.strategy-params-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.8rem;
}

.strategy-params-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.9rem;
  border-radius: 0.95rem;
  background: color-mix(in srgb, var(--neutral-color) 3%, transparent);
  border: 1px solid color-mix(in srgb, var(--neutral-color) 6%, transparent);
}

.strategy-params-section-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 0.9rem;
  font-weight: 700;
}

.strategy-params-list {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.strategy-param-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.strategy-param-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.strategy-param-key {
  color: var(--text-secondary);
  font-size: 0.76rem;
  font-weight: 600;
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

.strategy-param-value {
  color: var(--accent-tertiary);
  font-size: 0.76rem;
  font-weight: 700;
}

.strategy-param-meaning {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.74rem;
  line-height: 1.45;
}

.seed-section {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.seed-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 1rem;
  font-weight: 700;
}

.seed-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.seed-pill {
  display: inline-flex;
  align-items: center;
  min-height: 2rem;
  padding: 0.3rem 0.75rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent-primary) 12%, transparent);
  color: var(--accent-primary);
  font-size: 0.8rem;
  font-weight: 600;
}

.seed-pill.secondary {
  background: color-mix(in srgb, var(--accent-tertiary) 12%, transparent);
  color: var(--accent-tertiary);
}

.content-shell {
  padding: 1.15rem;
}

.loading-shell {
  min-height: 18rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.recommendation-grid {
  align-items: start;
}

.recommendation-grid.standard-layout {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  grid-auto-rows: 1fr;
  gap: 1rem;
  align-items: stretch;
}

.recommendation-grid.standard-layout .recommendation-slot {
  display: flex;
  position: relative;
  height: 100%;
}

.recommendation-grid.standard-layout .recommendation-slot :deep(.recommendation-card) {
  width: 100%;
  height: 100%;
}

.recommendation-grid.masonry-layout {
  width: min(30rem, 100%);
  margin: 0 auto;
  column-count: 2;
  column-gap: 0.75rem;
}

.recommendation-grid.masonry-layout .recommendation-slot {
  break-inside: avoid;
  position: relative;
  margin-bottom: 0.75rem;
}

.results-stack {
  display: flex;
  flex-direction: column;
  gap: 1.15rem;
}

.results-footer {
  display: flex;
  justify-content: center;
}

.rec-footer-btn {
  border-width: 1.5px;
  border-color: color-mix(in srgb, var(--accent-primary) 32%, transparent);
  border-radius: 999px;
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--accent-primary) 12%, transparent),
      color-mix(in srgb, var(--accent-primary) 5%, transparent)
    ),
    color-mix(in srgb, var(--neutral-color) 4%, transparent);
  color: var(--on-accent);
  box-shadow: 0 12px 28px color-mix(in srgb, var(--accent-primary) 12%, transparent);
}

.scroll-top-btn {
  position: fixed;
  right: 2rem;
  bottom: 2rem;
  z-index: 20;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3.5rem;
  min-height: 3.5rem;
  padding: 0 0.5rem;
  border: 1px solid var(--accent-primary);
  border-radius: 999px;
  background: var(--accent-primary);
  color: var(--on-accent);
  font-weight: 700;
  font-size: 1.2rem;
  backdrop-filter: blur(14px);
  box-shadow: var(--shadow-accent-lg);
  cursor: pointer;
  transition: all 0.3s ease;
}

.scroll-top-btn:hover {
  transform: translateY(-2px);
  background: var(--accent-secondary);
  border-color: var(--accent-secondary);
  box-shadow: var(--shadow-accent-xl);
}

.reason-floating-panel {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  left: 0.75rem;
  z-index: 30;
  max-height: calc(100% - 1.5rem);
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  padding: 1rem;
  border-radius: 1.15rem;
  border: 1px solid var(--border-color);
  background: var(--bg-overlay);
  color: var(--text-primary);
  box-shadow: 0 18px 44px color-mix(in srgb, var(--shadow-ink) 22%, transparent);
  backdrop-filter: blur(14px);
}

.reason-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.reason-panel-eyebrow {
  color: var(--accent-primary);
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.reason-panel-title {
  margin: 0.35rem 0 0;
  color: var(--text-primary);
  font-size: 1.15rem;
  font-weight: 700;
}

.reason-panel-close {
  min-height: 2.25rem;
  padding: 0 0.85rem;
  border-radius: 999px;
  border: 1px solid var(--border-color);
  background: color-mix(in srgb, var(--neutral-color) 6%, transparent);
  color: var(--text-secondary);
  cursor: pointer;
}

.reason-panel-subtitle {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.92rem;
  line-height: 1.6;
}

.reason-panel-score {
  display: inline-flex;
  align-self: flex-start;
  min-height: 2rem;
  padding: 0.35rem 0.78rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent-primary) 12%, transparent);
  color: var(--accent-primary);
  font-size: 0.8rem;
  font-weight: 700;
}

.reason-panel-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow-y: auto;
  padding-right: 0.15rem;
}

.reason-panel-item {
  padding: 0.78rem 0.9rem;
  border-radius: 1rem;
  background: color-mix(in srgb, var(--accent-primary) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent-primary) 12%, transparent);
  color: var(--text-primary);
  font-size: 0.78rem;
  line-height: 1.4;
}

.reason-panel-fade-enter-active,
.reason-panel-fade-leave-active {
  transition: all 0.22s ease;
}

.reason-panel-fade-enter-from,
.reason-panel-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 960px) {
  .page-header,
  .meta-strip,
  .metrics-panel,
  .strategy-params-grid,
  .seed-panel {
    grid-template-columns: 1fr;
  }

  .metrics-refresh-btn {
    width: 100%;
    min-height: 3rem;
  }

  .page-header {
    align-items: stretch;
  }

  .header-actions {
    width: 100%;
  }

  .rec-action-btn {
    flex: 1 1 0;
    min-width: 0;
  }

  .scroll-top-btn {
    right: 1rem;
    bottom: 1rem;
  }

  .recommendation-grid.masonry-layout {
    column-count: 2;
    width: min(30rem, 100%);
  }
}

@media (max-width: 640px) {
  .recommendation-grid.masonry-layout {
    column-count: 1;
  }
}
</style>
