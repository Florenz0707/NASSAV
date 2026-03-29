<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import RecommendationCard from '../components/RecommendationCard.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import { recommendationApi } from '../api'
import { useResourceStore } from '../stores/resource'
import { useToastStore } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
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
const initialized = ref(false)
const hasRequested = ref(false)
const showScrollTop = ref(false)
const lastLoadedConfigKey = ref('')

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

function buildConfigKey() {
  return JSON.stringify({
    recommender: selectedRecommender.value || '',
    strategy: selectedStrategy.value || '',
    limit: limit.value || 12,
  })
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
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
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
    seeds.value = payload.seeds || []
    meta.value = payload.meta || null
    lastLoadedConfigKey.value = requestConfigKey
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

function handleOpen(item) {
  if (!item?.detail_url) return
  window.open(item.detail_url, '_blank', 'noopener,noreferrer')
}

function handleView(item) {
  if (!item?.avid) return
  router.push(`/resource/${item.avid}`)
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
  await loadOptions()
  initialized.value = true
  syncQuery()
  updateScrollState()
  window.addEventListener('scroll', updateScrollState, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', updateScrollState)
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
          <select v-model="selectedRecommender" class="meta-select">
            <option v-for="item in options.recommenders" :key="item.id" :value="item.id">
              {{ item.name }}
            </option>
          </select>
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
          <select v-model="selectedStrategy" class="meta-select">
            <option v-for="item in availableStrategies" :key="item.id" :value="item.id">
              {{ item.name }}
            </option>
          </select>
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
          <select v-model.number="limit" class="meta-select">
            <option v-for="size in [12, 24, 36]" :key="size" :value="size">
              {{ size }}
            </option>
          </select>
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
      <div v-if="loading" class="loading-shell">
        <LoadingSpinner size="large" text="正在生成推荐结果..." />
      </div>

      <EmptyState
        v-else-if="!hasRequested"
        icon="✦"
        title="尚未开始推荐"
        description="先选择推荐器与策略，再按上方按钮生成推荐结果。"
      />

      <EmptyState v-else-if="error" icon="!" title="推荐加载失败" :description="error">
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
        <div class="recommendation-grid">
          <RecommendationCard
            v-for="item in visibleItems"
            :key="item.avid"
            :item="item"
            :adding="addingAvids.has(item.avid)"
            :added="addedAvids.has(item.avid)"
            @add="handleAdd(item)"
            @open="handleOpen(item)"
            @view="handleView(item)"
          />
        </div>

        <div class="results-footer">
          <button class="footer-refresh-btn" :disabled="loading" @click="loadRecommendations">
            <LoadingSpinner v-if="loading" size="small" />
            <template v-else> 继续刷新推荐 </template>
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
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 0.95rem;
  padding: 0.65rem 0.85rem;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
  font-size: 0.85rem;
  font-weight: 600;
  appearance: none;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    background 0.2s ease;
}

.meta-select:focus {
  outline: none;
  border-color: rgba(255, 107, 107, 0.35);
  box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.12);
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
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1rem;
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
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  background: rgba(18, 18, 24, 0.82);
  color: var(--text-primary);
  font-weight: 600;
  backdrop-filter: blur(14px);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.24);
  cursor: pointer;
}

.scroll-top-btn:hover {
  border-color: rgba(255, 107, 107, 0.28);
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
}
</style>
