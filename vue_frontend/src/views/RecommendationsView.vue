<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CustomSelect from '../components/CustomSelect.vue'
import RecommendationCard from '../components/RecommendationCard.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import { recommendationApi } from '../api'
import { useResourceStore } from '../stores/resource'
import { useSettingsStore } from '../stores/settings'
import { useToastStore } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
const settingsStore = useSettingsStore()
const toastStore = useToastStore()

const loading = ref(false)
const error = ref('')
const items = ref([])
const seeds = ref([])
const meta = ref(null)
const options = ref({
  defaults: {
    recommender: 'jable_search',
    strategy: 'local_preference',
  },
  recommenders: [],
  strategies: [],
})

const selectedRecommender = ref(route.query.recommender || '')
const selectedStrategy = ref(route.query.strategy || '')
const limit = ref(Number.parseInt(route.query.limit, 10) || 12)
const addingAvids = ref(new Set())
const addedAvids = ref(new Set())
const feedbackSubmittingAvids = ref(new Set())
const feedbackByAvid = ref({})
const initialized = ref(false)
const hasRequested = ref(false)
const showScrollTop = ref(false)
const lastLoadedConfigKey = ref('')
const activeReasonAvid = ref('')
const activeReasonPopoverStyle = ref({})
const activeReasonAnchor = ref(null)
const RECOMMENDATIONS_STATE_KEY = 'nassav:recommendations:view-state'

const availableStrategies = computed(() => {
  return (options.value.strategies || []).filter((item) => {
    if (!selectedRecommender.value) return true
    return item.supported_recommenders?.includes(selectedRecommender.value)
  })
})

const selectedRecommenderDetail = computed(() => {
  return (
    (options.value.recommenders || []).find((item) => item.id === selectedRecommender.value) || null
  )
})

const selectedStrategyDetail = computed(() => {
  return availableStrategies.value.find((item) => item.id === selectedStrategy.value) || null
})

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
const activeReasonItem = computed(() => {
  if (!activeReasonAvid.value) return null
  return visibleItems.value.find((item) => item.avid === activeReasonAvid.value) || null
})
const showInitialLoading = computed(() => loading.value && !visibleItems.value.length)
const recommenderOptions = computed(() =>
  (options.value.recommenders || []).map((item) => ({
    value: item.id,
    label: item.name,
  }))
)
const strategyOptions = computed(() =>
  availableStrategies.value.map((item) => ({
    value: item.id,
    label: item.name,
  }))
)
const limitOptions = [
  { value: 12, label: '12' },
  { value: 24, label: '24' },
  { value: 36, label: '36' },
]

function buildConfigKey() {
  return JSON.stringify({
    recommender: selectedRecommender.value || '',
    strategy: selectedStrategy.value || '',
    limit: limit.value || 12,
  })
}

function serializeSet(value) {
  return Array.from(value || [])
}

function saveViewState() {
  const state = {
    selectedRecommender: selectedRecommender.value,
    selectedStrategy: selectedStrategy.value,
    limit: limit.value,
    items: items.value || [],
    seeds: seeds.value || [],
    meta: meta.value || null,
    hasRequested: hasRequested.value,
    lastLoadedConfigKey: lastLoadedConfigKey.value,
    addedAvids: serializeSet(addedAvids.value),
    feedbackByAvid: feedbackByAvid.value || {},
    scrollY: window.scrollY || 0,
  }
  window.sessionStorage.setItem(RECOMMENDATIONS_STATE_KEY, JSON.stringify(state))
}

function restoreViewState() {
  const raw = window.sessionStorage.getItem(RECOMMENDATIONS_STATE_KEY)
  if (!raw) return null

  try {
    const state = JSON.parse(raw)
    selectedRecommender.value = state.selectedRecommender || selectedRecommender.value
    selectedStrategy.value = state.selectedStrategy || selectedStrategy.value
    limit.value = Number.parseInt(state.limit, 10) || 12
    items.value = Array.isArray(state.items) ? state.items : []
    seeds.value = Array.isArray(state.seeds) ? state.seeds : []
    meta.value = state.meta || null
    hasRequested.value = Boolean(state.hasRequested)
    lastLoadedConfigKey.value = state.lastLoadedConfigKey || ''
    addedAvids.value = new Set(Array.isArray(state.addedAvids) ? state.addedAvids : [])
    feedbackByAvid.value =
      state.feedbackByAvid && typeof state.feedbackByAvid === 'object' ? state.feedbackByAvid : {}
    return state
  } catch (_error) {
    window.sessionStorage.removeItem(RECOMMENDATIONS_STATE_KEY)
    return null
  }
}

function mergeRecommendationItems(existingItems, nextItems) {
  const merged = []
  const seen = new Set()
  for (const item of [...(existingItems || []), ...(nextItems || [])]) {
    if (!item?.avid || seen.has(item.avid)) continue
    seen.add(item.avid)
    merged.push(item)
  }
  return merged
}

function updateScrollState() {
  showScrollTop.value = window.scrollY > 360
  if (activeReasonAvid.value) {
    const anchorElement = findReasonAnchorElement(activeReasonAvid.value)
    if (anchorElement) {
      activeReasonAnchor.value = anchorElement
      positionReasonPopover(anchorElement)
    }
  }
}

function syncActiveReasonItem() {
  if (!activeReasonAvid.value) return
  const exists = visibleItems.value.some((item) => item.avid === activeReasonAvid.value)
  if (!exists) {
    activeReasonAvid.value = ''
    activeReasonAnchor.value = null
    activeReasonPopoverStyle.value = {}
  }
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function closeReasonPanel() {
  activeReasonAvid.value = ''
  activeReasonAnchor.value = null
  activeReasonPopoverStyle.value = {}
}

function findReasonAnchorElement(avid) {
  if (!avid || !window.CSS?.escape) return null
  return document.querySelector(`[data-reason-anchor="${window.CSS.escape(avid)}"]`)
}

function positionReasonPopover(anchorElement) {
  if (!anchorElement) return

  const rect = anchorElement.getBoundingClientRect()
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight

  if (viewportWidth < 960) {
    activeReasonPopoverStyle.value = {
      left: '1rem',
      right: '1rem',
      bottom: '1rem',
      width: 'auto',
      maxWidth: 'none',
    }
    return
  }

  const popoverWidth = resultDisplayStyle.value === 'masonry' ? 240 : 300
  const offset = 12
  let left = rect.right + offset

  if (left + popoverWidth > viewportWidth - 16) {
    left = Math.max(16, rect.left - popoverWidth - offset)
  }

  const top = Math.min(Math.max(88, rect.top - 12), Math.max(88, viewportHeight - 360))

  activeReasonPopoverStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    width: `${popoverWidth}px`,
    maxWidth: `${Math.max(220, viewportWidth - 32)}px`,
  }
}

function toggleReasonPanel(item, event) {
  if (!item?.avid || !item.reasons?.length) return
  if (activeReasonAvid.value === item.avid) {
    closeReasonPanel()
    return
  }

  activeReasonAvid.value = item.avid
  activeReasonAnchor.value = event?.currentTarget || null
  positionReasonPopover(activeReasonAnchor.value)
}

function syncQuery() {
  const query = {}
  if (selectedRecommender.value) query.recommender = selectedRecommender.value
  if (selectedStrategy.value) query.strategy = selectedStrategy.value
  if (limit.value !== 12) query.limit = limit.value
  router.replace({ query })
}

async function loadOptions() {
  const response = await recommendationApi.getOptions()
  options.value = response.data || options.value

  if (!selectedRecommender.value) {
    selectedRecommender.value = options.value.defaults?.recommender || 'jable_search'
  }
  if (!selectedStrategy.value) {
    selectedStrategy.value = options.value.defaults?.strategy || 'local_preference'
  }

  const strategySupported = availableStrategies.value.some(
    (item) => item.id === selectedStrategy.value
  )
  if (!strategySupported && availableStrategies.value.length > 0) {
    selectedStrategy.value = availableStrategies.value[0].id
  }
}

async function loadRecommendations() {
  loading.value = true
  error.value = ''
  hasRequested.value = true
  const requestConfigKey = buildConfigKey()
  const shouldMerge = requestConfigKey === lastLoadedConfigKey.value && items.value.length > 0

  try {
    const response = await recommendationApi.getList({
      recommender: selectedRecommender.value,
      strategy: selectedStrategy.value,
      limit: limit.value,
      exclude_existing: true,
    })

    const payload = response.data || {}
    items.value = shouldMerge
      ? mergeRecommendationItems(items.value, payload.items || [])
      : payload.items || []
    seeds.value = [...(payload.seeds || [])]
    meta.value = payload.meta || null
    lastLoadedConfigKey.value = requestConfigKey
    syncActiveReasonItem()
    window.requestAnimationFrame(() => {
      if (!activeReasonAvid.value) return
      const anchorElement = findReasonAnchorElement(activeReasonAvid.value)
      if (anchorElement) {
        activeReasonAnchor.value = anchorElement
        positionReasonPopover(anchorElement)
      }
    })
  } catch (err) {
    error.value = err.message || '获取推荐失败'
    if (!shouldMerge) {
      items.value = []
      seeds.value = []
    }
  } finally {
    loading.value = false
  }
}

async function handleAdd(item) {
  if (!item?.avid || addingAvids.value.has(item.avid)) return

  const next = new Set(addingAvids.value)
  next.add(item.avid)
  addingAvids.value = next

  try {
    await resourceStore.addResource(item.avid, 'any')
    toastStore.success(`${item.avid} 已加入资源库`)

    const added = new Set(addedAvids.value)
    added.add(item.avid)
    addedAvids.value = added
  } catch (err) {
    if (err.code === 409) {
      toastStore.info(`${item.avid} 已存在于资源库`)
      const added = new Set(addedAvids.value)
      added.add(item.avid)
      addedAvids.value = added
      return
    }
    toastStore.error(err.message || '添加资源失败')
  } finally {
    const done = new Set(addingAvids.value)
    done.delete(item.avid)
    addingAvids.value = done
  }
}

async function handleFeedback(item, feedbackType) {
  if (!item?.avid || !item?.snapshot_id || feedbackSubmittingAvids.value.has(item.avid)) return

  const currentFeedback = feedbackByAvid.value[item.avid] || ''
  const nextFeedback = currentFeedback === feedbackType ? 'clear' : feedbackType

  const nextSubmitting = new Set(feedbackSubmittingAvids.value)
  nextSubmitting.add(item.avid)
  feedbackSubmittingAvids.value = nextSubmitting

  try {
    const response = await recommendationApi.submitFeedback({
      snapshot_id: item.snapshot_id,
      avid: item.avid,
      feedback: nextFeedback,
    })
    const savedFeedback = response.data?.feedback || ''
    feedbackByAvid.value = {
      ...feedbackByAvid.value,
      [item.avid]: savedFeedback,
    }
    if (savedFeedback) {
      toastStore.success(`${item.avid} 的推荐反馈已更新`)
    } else {
      toastStore.info(`${item.avid} 的推荐反馈已清除`)
    }
  } catch (err) {
    toastStore.error(err.message || '提交推荐反馈失败')
  } finally {
    const done = new Set(feedbackSubmittingAvids.value)
    done.delete(item.avid)
    feedbackSubmittingAvids.value = done
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
    closeReasonPanel()
  }
}

function handleViewportResize() {
  updateScrollState()
}

watch(selectedRecommender, () => {
  const strategySupported = availableStrategies.value.some(
    (item) => item.id === selectedStrategy.value
  )
  if (!strategySupported && availableStrategies.value.length > 0) {
    selectedStrategy.value = availableStrategies.value[0].id
  }
  if (!initialized.value) return
  syncQuery()
})

watch([selectedStrategy, limit], () => {
  if (!initialized.value) return
  syncQuery()
})

onMounted(async () => {
  await settingsStore.loadSettings()
  const restoredState = restoreViewState()
  await loadOptions()
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

      <button class="refresh-btn" :disabled="loading" @click="loadRecommendations">
        <LoadingSpinner v-if="loading" size="small" />
        <template v-else>
          {{ hasRequested ? '刷新推荐' : '开始推荐' }}
        </template>
      </button>
    </section>

    <section class="meta-strip">
      <div class="meta-card">
        <div class="meta-label">推荐器</div>
        <label class="meta-control">
          <CustomSelect
            v-model="selectedRecommender"
            :options="recommenderOptions"
            class="meta-select"
            full-width
          />
        </label>
        <p class="meta-desc">
          {{
            meta?.recommender_detail?.description ||
            selectedRecommenderDetail?.description ||
            '决定从哪里召回候选资源。'
          }}
        </p>
      </div>
      <div class="meta-card strategy-card">
        <div class="meta-label">策略</div>
        <label class="meta-control">
          <CustomSelect
            v-model="selectedStrategy"
            :options="strategyOptions"
            class="meta-select"
            full-width
          />
        </label>
        <p class="meta-desc">
          {{
            meta?.strategy_detail?.description ||
            selectedStrategyDetail?.description ||
            '决定种子来源、打分因子和默认过滤行为。'
          }}
        </p>
      </div>
      <div class="meta-card">
        <div class="meta-label">返回数量</div>
        <label class="meta-control">
          <CustomSelect v-model="limit" :options="limitOptions" class="meta-select" full-width />
        </label>
        <p class="meta-desc">默认返回 12 条推荐结果。</p>
      </div>
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
        <LoadingSpinner size="large" text="正在生成推荐结果..." />
      </div>

      <EmptyState
        v-else-if="!hasRequested && !visibleItems.length"
        icon="✦"
        title="尚未开始推荐"
        description="先选择推荐器与策略，再按上方按钮生成推荐结果。"
      />

      <EmptyState
        v-else-if="error && !visibleItems.length"
        icon="!"
        title="推荐加载失败"
        :description="error"
      >
        <template #action>
          <button class="empty-action" @click="loadRecommendations">重新加载</button>
        </template>
      </EmptyState>

      <EmptyState
        v-else-if="!visibleItems.length"
        icon="✦"
        title="暂时没有可展示的推荐"
        description="可以先增加资源，或者稍后重新刷新推荐结果。"
      >
        <template #action>
          <button class="empty-action" @click="loadRecommendations">再试一次</button>
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
              :feedback="feedbackByAvid[item.avid] || ''"
              :feedback-submitting="feedbackSubmittingAvids.has(item.avid)"
              :layout-style="resultDisplayStyle"
              :reasons-open="activeReasonAvid === item.avid"
              @add="handleAdd(item)"
              @feedback="handleFeedback(item, $event)"
              @open="handleOpen(item)"
              @view="handleView(item)"
              @reasons="toggleReasonPanel(item, $event)"
            />
          </div>
        </div>

        <div class="results-footer">
          <button class="footer-refresh-btn" :disabled="loading" @click="loadRecommendations">
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
      回到顶部
    </button>

    <transition name="reason-panel-fade">
      <aside
        v-if="activeReasonItem"
        class="reason-floating-panel"
        :style="activeReasonPopoverStyle"
      >
        <div class="reason-panel-header">
          <div>
            <div class="reason-panel-eyebrow">Recommendation Notes</div>
          </div>
          <button class="reason-panel-close" type="button" @click="closeReasonPanel">⨉</button>
        </div>
        <div class="reason-panel-score">
          推荐评分 {{ Number(activeReasonItem.score || 0).toFixed(1) }}
        </div>

        <div class="reason-panel-list">
          <div
            v-for="reason in activeReasonItem.reasons || []"
            :key="reason"
            class="reason-panel-item"
          >
            {{ reason }}
          </div>
        </div>
      </aside>
    </transition>
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
    radial-gradient(circle at top right, rgba(255, 107, 107, 0.18), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02));
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.18);
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  min-height: 1.85rem;
  padding: 0.2rem 0.7rem;
  border-radius: 999px;
  background: rgba(255, 107, 107, 0.12);
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

.refresh-btn,
.empty-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 8rem;
  min-height: 2.9rem;
  padding: 0 1rem;
  border: none;
  border-radius: 0.95rem;
  background: linear-gradient(135deg, var(--accent-primary), #ff8b5f);
  color: white;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(255, 107, 107, 0.22);
}

.refresh-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.meta-strip,
.seed-panel,
.content-shell {
  border-radius: 1.35rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 18px 38px rgba(0, 0, 0, 0.14);
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
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
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
  border-color: rgba(78, 205, 196, 0.35);
  box-shadow: 0 0 0 3px rgba(78, 205, 196, 0.12);
}

.seed-panel {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  padding: 1.15rem;
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
  background: rgba(255, 107, 107, 0.12);
  color: var(--accent-primary);
  font-size: 0.8rem;
  font-weight: 600;
}

.seed-pill.secondary {
  background: rgba(78, 205, 196, 0.12);
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

.footer-refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 10rem;
  min-height: 2.85rem;
  padding: 0 1.1rem;
  border-radius: 0.95rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
  font-weight: 600;
  cursor: pointer;
}

.footer-refresh-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.scroll-top-btn {
  position: fixed;
  right: 1.5rem;
  bottom: 1.5rem;
  z-index: 20;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 6.5rem;
  min-height: 2.75rem;
  padding: 0 1rem;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-overlay) 88%, transparent);
  color: var(--text-primary);
  font-weight: 600;
  backdrop-filter: blur(14px);
  box-shadow: var(--shadow-lg);
  cursor: pointer;
}

.scroll-top-btn:hover {
  border-color: rgba(255, 107, 107, 0.28);
  background: color-mix(in srgb, var(--bg-overlay) 94%, transparent);
}

.reason-floating-panel {
  position: fixed;
  z-index: 30;
  max-height: min(24rem, calc(100vh - 6rem));
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  padding: 1rem;
  border-radius: 1.15rem;
  border: 1px solid var(--border-color);
  background: var(--bg-overlay);
  color: var(--text-primary);
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.22);
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
  font-size: 0.72rem;
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
  background: rgba(255, 255, 255, 0.06);
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
  background: rgba(255, 107, 107, 0.12);
  color: var(--accent-primary);
  font-size: 0.84rem;
  font-weight: 700;
}

.reason-panel-list {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
  overflow-y: auto;
  padding-right: 0.15rem;
}

.reason-panel-item {
  padding: 0.78rem 0.9rem;
  border-radius: 1rem;
  background: rgba(255, 107, 107, 0.06);
  border: 1px solid rgba(255, 107, 107, 0.12);
  color: var(--text-primary);
  font-size: 0.88rem;
  line-height: 1.6;
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
  .seed-panel {
    grid-template-columns: 1fr;
  }

  .page-header {
    align-items: stretch;
  }

  .refresh-btn {
    width: 100%;
  }

  .scroll-top-btn {
    right: 1rem;
    bottom: 1rem;
  }

  .recommendation-grid.masonry-layout {
    column-count: 2;
    width: min(30rem, 100%);
  }

  .reason-floating-panel {
    top: auto;
    max-height: min(70vh, 34rem);
  }
}

@media (max-width: 640px) {
  .recommendation-grid.masonry-layout {
    column-count: 1;
  }

  .reason-floating-panel {
    left: 1rem !important;
    right: 1rem !important;
    bottom: 1rem !important;
    width: auto !important;
    max-height: min(70vh, 34rem);
  }
}
</style>
