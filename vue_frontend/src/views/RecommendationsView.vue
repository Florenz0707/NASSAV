<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CustomSelect from '../components/CustomSelect.vue'
import RecommendationCard from '../components/RecommendationCard.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import SettingsModal from '../components/settings/SettingsModal.vue'
import { actorApi, genreApi, recommendationApi } from '../api'
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
const typePreference = ref(route.query.type_preference || 'balanced')
const actorPreference = ref(route.query.actor_preference || 'balanced')
const genrePreference = ref(route.query.genre_preference || 'balanced')
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
const showPersonalizationModal = ref(false)
const blacklistSeedType = ref('actor')
const blacklistSearch = ref('')
const blacklistBlockedOnly = ref(true)
const blacklistLoading = ref(false)
const blacklistItems = ref([])
const blacklistPagination = ref(null)
const blacklistSubmittingKey = ref('')
const RECOMMENDATIONS_STATE_KEY = 'nassav:recommendations:view-state'
const blacklistCache = new Map()
const blacklistTabs = [
  { value: 'actor', label: '演员黑名单' },
  { value: 'genre', label: '类别黑名单' },
  { value: 'resource', label: '资源黑名单' },
]

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
const normalizedBlacklistSearch = computed(() =>
  blacklistSeedType.value === 'resource'
    ? blacklistSearch.value.trim().toUpperCase()
    : blacklistSearch.value.trim()
)
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
    limit: limit.value || 12,
  })
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
    typePreference.value = state.typePreference || typePreference.value
    actorPreference.value = state.actorPreference || actorPreference.value
    genrePreference.value = state.genrePreference || genrePreference.value
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

function clearPageRecommendations() {
  items.value = []
  seeds.value = []
  meta.value = null
  error.value = ''
  hasRequested.value = false
  lastLoadedConfigKey.value = ''
  feedbackByAvid.value = {}
  closeReasonPanel()
}

function openPersonalizationModal() {
  showPersonalizationModal.value = true
}

function closePersonalizationModal() {
  showPersonalizationModal.value = false
}

function buildBlacklistCacheKey() {
  return JSON.stringify({
    type: blacklistSeedType.value,
    search: normalizedBlacklistSearch.value,
    blockedOnly: blacklistSeedType.value === 'resource' ? true : blacklistBlockedOnly.value,
  })
}

function invalidateBlacklistCache(seedType = '') {
  const keys = Array.from(blacklistCache.keys())
  for (const key of keys) {
    if (!seedType || key.includes(`"type":"${seedType}"`)) {
      blacklistCache.delete(key)
    }
  }
}

async function loadBlacklistItems() {
  const cacheKey = buildBlacklistCacheKey()
  const cached = blacklistCache.get(cacheKey)
  if (cached) {
    blacklistItems.value = cached.items
    blacklistPagination.value = cached.pagination
    return
  }

  blacklistLoading.value = true
  try {
    let response = null
    let list = []
    let pagination = null

    if (blacklistSeedType.value === 'actor' || blacklistSeedType.value === 'genre') {
      const params = {
        page: 1,
        page_size: 200,
        order_by: blacklistBlockedOnly.value ? 'name' : 'count',
        order: blacklistBlockedOnly.value ? 'asc' : 'desc',
      }
      if (normalizedBlacklistSearch.value) {
        params.search = normalizedBlacklistSearch.value
      }

      response =
        blacklistSeedType.value === 'actor'
          ? await actorApi.getList(params)
          : await genreApi.getList(params)
      list = Array.isArray(response.data) ? response.data : []
      list = blacklistBlockedOnly.value ? list.filter((item) => item.is_blocked) : list
      pagination = response.pagination || null
    } else {
      const params = { page: 1, page_size: 200 }
      if (normalizedBlacklistSearch.value) {
        params.search = normalizedBlacklistSearch.value
      }
      response = await recommendationApi.getAvidBlocklist(params)
      list = Array.isArray(response.data) ? response.data : []
      pagination = response.pagination || null
    }

    blacklistItems.value = list
    blacklistPagination.value = pagination
    blacklistCache.set(cacheKey, {
      items: list.map((item) => ({ ...item })),
      pagination: pagination ? { ...pagination } : null,
    })
  } catch (err) {
    toastStore.error(err.message || '加载黑名单列表失败')
    blacklistItems.value = []
    blacklistPagination.value = null
  } finally {
    blacklistLoading.value = false
  }
}

async function toggleSeedBlocked(item) {
  const itemKey =
    blacklistSeedType.value === 'resource'
      ? `${blacklistSeedType.value}:${item?.avid || ''}`
      : `${blacklistSeedType.value}:${item?.id || ''}`
  if (!itemKey || itemKey.endsWith(':')) return
  const submitKey = itemKey
  if (blacklistSubmittingKey.value === submitKey) return

  blacklistSubmittingKey.value = submitKey
  try {
    if (blacklistSeedType.value === 'resource') {
      if (item.is_blocked) {
        await recommendationApi.unblockAvid({ avid: item.avid })
        toastStore.success(`已移除资源 ${item.avid} 的屏蔽`)
      } else {
        await recommendationApi.blockAvid({ avid: item.avid, reason: 'manual' })
        toastStore.success(`已将资源 ${item.avid} 加入黑名单`)
      }
    } else {
      if (item.is_blocked) {
        await recommendationApi.unblockSeed({
          seed_type: blacklistSeedType.value,
          id: item.id,
        })
        toastStore.success(`已移除${blacklistSeedType.value === 'actor' ? '演员' : '类别'}屏蔽`)
      } else {
        await recommendationApi.blockSeed({
          seed_type: blacklistSeedType.value,
          id: item.id,
          reason: 'manual',
        })
        toastStore.success(`已加入${blacklistSeedType.value === 'actor' ? '演员' : '类别'}屏蔽`)
      }
    }

    invalidateBlacklistCache(blacklistSeedType.value)
    blacklistItems.value = blacklistItems.value
      .map((entry) =>
        (blacklistSeedType.value === 'resource' ? entry.avid === item.avid : entry.id === item.id)
          ? {
              ...entry,
              is_blocked: !item.is_blocked,
            }
          : entry
      )
      .filter(
        (entry) =>
          !(
            blacklistSeedType.value !== 'resource' &&
            blacklistBlockedOnly.value &&
            !entry.is_blocked
          )
      )
  } catch (err) {
    toastStore.error(err.message || '更新屏蔽状态失败')
  } finally {
    blacklistSubmittingKey.value = ''
  }
}

async function addResourceBlacklist() {
  const avid = normalizedBlacklistSearch.value
  if (!avid) return
  const submitKey = `resource:${avid}`
  if (blacklistSubmittingKey.value === submitKey) return

  blacklistSubmittingKey.value = submitKey
  try {
    await recommendationApi.blockAvid({ avid, reason: 'manual' })
    toastStore.success(`已将资源 ${avid} 加入黑名单`)
    invalidateBlacklistCache('resource')
    await loadBlacklistItems()
  } catch (err) {
    toastStore.error(err.message || '添加资源黑名单失败')
  } finally {
    blacklistSubmittingKey.value = ''
  }
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

async function loadRecommendations() {
  loading.value = true
  error.value = ''
  hasRequested.value = true
  const requestConfigKey = buildConfigKey()
  const shouldMerge = requestConfigKey === lastLoadedConfigKey.value && items.value.length > 0

  try {
    const response = await recommendationApi.getList({
      type_preference: typePreference.value,
      actor_preference: actorPreference.value,
      genre_preference: genrePreference.value,
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
  if (feedbackType !== 'dislike') return

  const nextSubmitting = new Set(feedbackSubmittingAvids.value)
  nextSubmitting.add(item.avid)
  feedbackSubmittingAvids.value = nextSubmitting

  try {
    const response = await recommendationApi.submitFeedback({
      snapshot_id: item.snapshot_id,
      avid: item.avid,
      feedback: 'dislike',
    })
    const savedFeedback = response.data?.feedback || ''
    feedbackByAvid.value = {
      ...feedbackByAvid.value,
      [item.avid]: savedFeedback,
    }
    invalidateBlacklistCache('resource')
    toastStore.success(`${item.avid} 已加入不喜欢黑名单`)
  } catch (err) {
    toastStore.error(err.message || '提交推荐反馈失败')
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
  window.sessionStorage.removeItem(RECOMMENDATIONS_STATE_KEY)
  toastStore.success('当前推荐列表已清空')
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

watch(showPersonalizationModal, (visible) => {
  if (visible) {
    loadBlacklistItems()
  }
})

watch([blacklistSeedType, blacklistBlockedOnly], () => {
  if (blacklistSeedType.value === 'resource' && !blacklistBlockedOnly.value) {
    blacklistBlockedOnly.value = true
    return
  }
  if (!showPersonalizationModal.value) return
  loadBlacklistItems()
})

watch(blacklistSearch, () => {
  if (!showPersonalizationModal.value) return
  loadBlacklistItems()
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
          @click="loadRecommendations"
        >
          <LoadingSpinner v-if="loading" size="small" />
          <template v-else>{{ recommendationActionLabel }}</template>
        </button>
        <button class="rec-action-btn rec-action-btn-secondary" @click="openPersonalizationModal">
          个性化
        </button>
        <button
          class="rec-action-btn rec-action-btn-muted"
          :disabled="loading"
          @click="handleResetRecommendations"
        >
          清空页面
        </button>
      </div>
    </section>

    <section class="meta-strip">
      <div class="meta-card">
        <div class="meta-label">种子偏好</div>
        <label class="meta-control">
          <CustomSelect
            v-model="typePreference"
            :options="typePreferenceOptions"
            class="meta-select"
            full-width
          />
        </label>
        <p class="meta-desc">控制演员种子与类别种子的整体权重倾向。</p>
      </div>
      <div class="meta-card strategy-card">
        <div class="meta-label">演员偏好</div>
        <label class="meta-control">
          <CustomSelect
            v-model="actorPreference"
            :options="actorPreferenceOptions"
            class="meta-select"
            full-width
          />
        </label>
        <p class="meta-desc">控制演员种子“熟悉/平衡/少见”偏好，叠加种子轮换抑制。</p>
      </div>
      <div class="meta-card strategy-card">
        <div class="meta-label">类别偏好</div>
        <label class="meta-control">
          <CustomSelect
            v-model="genrePreference"
            :options="genrePreferenceOptions"
            class="meta-select"
            full-width
          />
        </label>
        <p class="meta-desc">控制类别种子“熟悉/平衡/少见”偏好，叠加种子轮换抑制。</p>
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
        <LoadingSpinner size="large" text="正在和妈妈桑交涉..." />
      </div>

      <EmptyState
        v-else-if="!hasRequested && !visibleItems.length"
        icon="✦"
        title="尚未开始推荐"
        description="设置偏好，开始推荐"
      />

      <EmptyState
        v-else-if="error && !visibleItems.length"
        icon="!"
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
        icon="✦"
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
          <button
            class="tw-btn-footer rec-footer-btn"
            :disabled="loading"
            @click="loadRecommendations"
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

    <SettingsModal
      :show="showPersonalizationModal"
      title="个性化"
      max-width-class="max-w-4xl"
      @close="closePersonalizationModal"
    >
      <template #header-extra>
        <div class="blacklist-tabs header-tabs">
          <button
            v-for="tab in blacklistTabs"
            :key="tab.value"
            class="blacklist-tab"
            :class="{ active: blacklistSeedType === tab.value }"
            @click="blacklistSeedType = tab.value"
          >
            {{ tab.label }}
          </button>
        </div>
      </template>

      <div class="blacklist-modal">
        <div class="blacklist-toolbar">
          <label class="blacklist-search">
            <span class="blacklist-search-label"></span>
            <input
              v-model.trim="blacklistSearch"
              type="text"
              :placeholder="
                blacklistSeedType === 'actor'
                  ? '搜索演员名'
                  : blacklistSeedType === 'genre'
                    ? '搜索类别名'
                    : '输入 AVID，例如 IPZZ-001'
              "
            />
          </label>

          <label v-if="blacklistSeedType !== 'resource'" class="pretty-toggle">
            <input
              v-model="blacklistBlockedOnly"
              type="checkbox"
              :disabled="blacklistSeedType === 'resource'"
            />
            <span class="pretty-toggle-track">
              <span class="pretty-toggle-thumb" />
            </span>
            <span class="pretty-toggle-label">仅看已屏蔽</span>
          </label>
        </div>

        <div
          v-if="blacklistSeedType === 'resource' && normalizedBlacklistSearch"
          class="blacklist-add-strip"
        >
          <div class="blacklist-add-copy">
            <span>将当前 AVID 直接加入资源黑名单</span>
          </div>
          <button
            class="blacklist-action-btn is-block"
            :disabled="blacklistSubmittingKey === `resource:${normalizedBlacklistSearch}`"
            @click="addResourceBlacklist"
          >
            {{
              blacklistSubmittingKey === `resource:${normalizedBlacklistSearch}` ? '...' : '屏蔽'
            }}
          </button>
        </div>

        <div class="blacklist-summary">
          <span>
            当前类型：
            {{
              blacklistSeedType === 'actor'
                ? '演员'
                : blacklistSeedType === 'genre'
                  ? '类别'
                  : '资源'
            }}
          </span>
          <span v-if="blacklistPagination">
            {{ blacklistSeedType === 'resource' ? '屏蔽条目' : '总条目' }}
            {{ blacklistPagination.total }}
          </span>
          <span>当前展示 {{ blacklistItems.length }}</span>
        </div>

        <div v-if="blacklistLoading" class="blacklist-loading">
          <LoadingSpinner size="medium" text="正在读取..." />
        </div>

        <div v-else-if="!blacklistItems.length" class="blacklist-empty">
          {{ blacklistBlockedOnly ? '当前没有已屏蔽项。' : '没有匹配到可操作的条目。' }}
        </div>

        <div v-else class="blacklist-list">
          <div
            v-for="item in blacklistItems"
            :key="`${blacklistSeedType}-${item.avid || item.id}`"
            class="blacklist-row"
          >
            <div class="blacklist-main">
              <div class="blacklist-name">
                {{ item.name || item.title || item.avid }} （{{
                  blacklistSeedType === 'resource' ? '' : `${item.resource_count ?? 0}个资源`
                }}
                {{ `${item.is_blocked ? '已屏蔽' : '未屏蔽'}` }}）
              </div>
            </div>

            <button
              class="blacklist-action-btn"
              :class="item.is_blocked ? 'is-unblock' : 'is-block'"
              :disabled="
                blacklistSubmittingKey ===
                `${blacklistSeedType}:${blacklistSeedType === 'resource' ? item.avid : item.id}`
              "
              @click="toggleSeedBlocked(item)"
            >
              {{
                blacklistSubmittingKey ===
                `${blacklistSeedType}:${blacklistSeedType === 'resource' ? item.avid : item.id}`
                  ? '...'
                  : item.is_blocked
                    ? '取消'
                    : '屏蔽'
              }}
            </button>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="blacklist-footer">
          <button class="tw-btn-outline-muted" @click="closePersonalizationModal">关闭</button>
        </div>
      </template>
    </SettingsModal>
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
  color: #fff;
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-primary));
  box-shadow: 0 10px 22px rgba(255, 107, 107, 0.22);
}

.rec-action-btn-secondary {
  color: #fff7ef;
  background: var(--accent-danger);
  box-shadow: 0 10px 22px rgba(255, 159, 67, 0.2);
}

.rec-action-btn-muted {
  color: var(--text-secondary);
  border-color: rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.04);
}

.meta-strip,
.strategy-params-panel,
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
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
}

.strategy-params-toggle:hover {
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.07);
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
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
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

.rec-footer-btn {
  border-width: 1.5px;
  border-color: rgba(255, 107, 107, 0.32);
  border-radius: 999px;
  background:
    linear-gradient(180deg, rgba(255, 107, 107, 0.12), rgba(255, 107, 107, 0.05)),
    rgba(255, 255, 255, 0.04);
  box-shadow: 0 12px 28px rgba(255, 107, 107, 0.12);
}

.scroll-top-btn {
  position: fixed;
  right: 2rem;
  bottom: 2rem;
  z-index: 20;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3rem;
  min-height: 3rem;
  padding: 0 0.5rem;
  border: 1px solid rgba(223, 218, 218, 0.5);
  border-radius: 999px;
  background:
    linear-gradient(135deg, rgba(255, 107, 107, 0.22), rgba(255, 139, 95, 0.18)),
    rgba(18, 24, 38, 0);
  color: rgba(255, 255, 255, 1);
  font-weight: 700;
  backdrop-filter: blur(14px);
  box-shadow:
    0 18px 36px rgba(0, 0, 0, 0.34),
    0 0 0 1px rgba(255, 107, 107, 0.08);
  cursor: pointer;
}

.scroll-top-btn:hover {
  border-color: rgba(255, 151, 117, 0.48);
  background:
    linear-gradient(135deg, rgba(255, 107, 107, 0.3), rgba(255, 139, 95, 0.24)),
    rgba(22, 28, 44, 0.94);
  box-shadow:
    0 22px 42px rgba(0, 0, 0, 0.4),
    0 0 0 1px rgba(255, 139, 95, 0.14);
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
  background: rgba(255, 107, 107, 0.06);
  border: 1px solid rgba(255, 107, 107, 0.12);
  color: var(--text-primary);
  font-size: 0.78rem;
  line-height: 1.4;
}

.blacklist-modal {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.blacklist-toolbar {
  display: flex;
  flex-direction: column;
  align-items: left;
  gap: 1rem;
}

.blacklist-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.7rem;
}

.blacklist-tab {
  min-height: 2.3rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 60px;
  padding: 0 1rem;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 400;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.blacklist-tab.active {
  border-color: rgba(255, 159, 67, 0.32);
  background: rgba(255, 159, 67, 0.12);
  color: #fff7ef;
}

.header-tabs {
  margin-left: 0.5rem;
}

.blacklist-search {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  width: 100%;
  margin: left -0.5rem;
}

.blacklist-search-label {
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 600;
}

.blacklist-search input {
  min-height: 2.8rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 0.95rem;
  background: rgba(255, 255, 255, 0.04);
  padding: 0 0.9rem;
  color: var(--text-primary);
}

.pretty-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.7rem;
  cursor: pointer;
  user-select: none;
}

.pretty-toggle input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.pretty-toggle-track {
  position: relative;
  display: inline-flex;
  width: 2.7rem;
  height: 1.2rem;
  align-items: center;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.08);
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.pretty-toggle-thumb {
  position: absolute;
  left: 0.2rem;
  width: 1.05rem;
  height: 1.05rem;
  border-radius: 999px;
  background: #fff7ef;
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.2);
  transition: transform 0.2s ease;
}

.pretty-toggle input:checked + .pretty-toggle-track {
  border-color: rgba(255, 159, 67, 0.28);
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-danger));
}

.pretty-toggle input:checked + .pretty-toggle-track .pretty-toggle-thumb {
  transform: translateX(1.1rem);
}

.pretty-toggle-label {
  color: var(--text-secondary);
  font-size: 0.92rem;
  font-weight: 600;
}

.blacklist-add-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border: 1px solid rgba(255, 159, 67, 0.14);
  border-radius: 1rem;
  background: rgba(255, 159, 67, 0.06);
  padding: 0.9rem 1rem;
}

.blacklist-add-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.18rem;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.blacklist-add-copy strong {
  color: var(--text-primary);
  font-size: 0.96rem;
}

.blacklist-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1rem;
  color: var(--text-muted);
  font-size: 0.86rem;
}

.blacklist-loading,
.blacklist-empty {
  display: flex;
  min-height: 13rem;
  align-items: center;
  justify-content: center;
  border-radius: 1rem;
  border: 1px dashed rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.025);
  color: var(--text-secondary);
}

.blacklist-list {
  display: flex;
  max-height: 13rem;
  flex-direction: column;
  gap: 0.75rem;
  overflow-y: auto;
  padding-right: 0.2rem;
}

.blacklist-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.03);
  padding: 0.95rem 1rem;
}

.blacklist-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.3rem;
}

.blacklist-name {
  color: var(--text-primary);
  font-weight: 700;
  word-break: break-word;
}

.blacklist-action-btn {
  min-width: 5.5rem;
  min-height: 1.5rem;
  border-radius: 0.9rem;
  padding: 0.3rem 1.7rem;
  font-size: 1rem;
  font-weight: 500;
  transition:
    transform 0.2s ease,
    opacity 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.blacklist-action-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.blacklist-action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.blacklist-action-btn.is-block {
  border: none;
  background: var(--accent-primary);
  color: #fff7ef;
}

.blacklist-action-btn.is-unblock {
  border: 1px solid rgba(220, 38, 38, 0.22);
  background: rgba(220, 38, 38, 0.1);
  color: var(--accent-danger);
}

.blacklist-footer {
  display: flex;
  justify-content: flex-end;
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
  .strategy-params-grid,
  .seed-panel {
    grid-template-columns: 1fr;
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

  .reason-floating-panel {
    top: auto;
    max-height: min(70vh, 34rem);
  }

  .blacklist-toolbar,
  .blacklist-row {
    flex-direction: column;
    align-items: stretch;
  }

  .blacklist-search {
    width: 100%;
  }

  .blacklist-action-btn,
  .blacklist-add-strip {
    width: 100%;
  }

  .header-tabs {
    margin-left: 0;
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
