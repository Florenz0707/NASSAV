<script setup>
import { createRequestGuard } from '../utils/requestGuard.js'
import AppButton from '../components/AppButton.vue'
import { useExternalSearchTask } from '../composables/useExternalSearchTask.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useToastStore } from '../stores/toast'
import { useRoute, useRouter } from 'vue-router'
import { useResourceStore } from '../stores/resource'
import { useSettingsStore } from '../stores/settings'
import { actorApi, genreApi, resourceApi, downloadApi } from '../api'
import ResourceCard from '../components/ResourceCard.vue'

import ExternalSearchCard from '../components/ExternalSearchCard.vue'
import ResourcePagination from '../components/ResourcePagination.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import CustomSelect from '../components/CustomSelect.vue'
import {
  useExternalSearchSources,
  createSearchRequestGuard,
} from '../composables/useExternalSearchSources.js'
import EmptyState from '../components/EmptyState.vue'
import BatchControls from '../components/BatchControls.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ResourceSearchBar from '../components/ResourceSearchBar.vue'

const props = defineProps({
  entityType: {
    type: String,
    required: true,
    validator: (value) => ['actor', 'genre'].includes(value),
  },
})
const isActor = props.entityType === 'actor'
const entityLabel = isActor ? '演员' : '类别'
const entityApi = isActor ? actorApi : genreApi
const routeParam = `${props.entityType}Id`
const infoGuard = createRequestGuard()
const navigationGuard = createRequestGuard()
const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
const settingsStore = useSettingsStore()

const entityId = ref(route.params[routeParam] || '')
// 从 URL query 初始化状态
const currentTab = ref(route.query.tab || 'local')
const page = ref(parseInt(route.query.page) || 1)
const pageSize = ref(parseInt(route.query.pageSize) || 18)
const sortBy = ref(route.query.sortBy || 'metadata_create_time')
const sortOrder = ref(route.query.order || 'desc')
const searchQuery = ref(route.query.search || '')
const filterStatus = ref(route.query.status || 'all')

const loadingEntity = ref(false)
const entity = ref({ id: entityId.value, name: '', resource_count: 0, avatar_url: null })
const toastStore = useToastStore()

// External Search states
const externalSearched = ref(false)
const loadingExternal = ref(false)
const externalResources = ref([])
const externalMeta = ref({})
const externalPage = ref(1)
const externalPagination = ref(null)
const {
  externalSource,
  sourceOptions,
  selectedCapability,
  sourcesReady,
  sourcesError,
  loadSearchSources,
} = useExternalSearchSources(props.entityType)
const requestGuard = createSearchRequestGuard()
const {
  status: searchStatus,
  progress: searchProgress,
  search: searchExternal,
  cancel: cancelExternalSearch,
  cancelJob: cancelExternalSearchJob,
  readPage: readExternalPage,
  getJobHandle,
  restoreJob,
} = useExternalSearchTask()
const externalError = ref('')
const externalCancelled = ref(false)
const cancellingExternal = ref(false)
function externalCacheKey() {
  return `external_cn_v4_${props.entityType}_${entityId.value}_${externalSource.value}`
}
function onExternalSourceChange(value) {
  cancelExternalSearch()
  requestGuard.invalidate()
  externalSource.value = value
  externalSortOrder.value = 'desc'
  resetExternalSearchState()
}
const availableSortOrders = computed(() =>
  externalSortOrderOptions.filter((item) =>
    selectedCapability.value?.orderings?.includes(
      `${item.value === 'desc' ? '-' : ''}${externalSortBy.value}`
    )
  )
)
const EXTERNAL_CACHE_TTL_MS = 1000 * 60 * 60

// queryKey -> pageNumber -> { results, meta }
const externalPageCache = ref({})

const externalSortBy = ref('views')
const externalSortOrder = ref('desc')
const externalSortByOptions = [
  { value: 'views', label: '播放量' },
  { value: 'likes', label: '收藏量' },
  { value: 'latest', label: '发布时间' },
]
const externalSortOrderOptions = [
  { value: 'desc', label: '降序' },
  { value: 'asc', label: '升序' },
]

function onExternalSortChange() {
  resetExternalSearchState()
}

async function stopExternalSearch() {
  if (!loadingExternal.value || cancellingExternal.value) return
  cancellingExternal.value = true
  try {
    if (await cancelExternalSearchJob()) externalCancelled.value = true
  } catch (error) {
    toastStore.error(error.message || '取消搜索失败，请重试')
  } finally {
    cancellingExternal.value = false
  }
}

function clearExternalQueryCache() {
  const queryKey = getExternalQueryKey()
  if (externalPageCache.value[queryKey]) {
    delete externalPageCache.value[queryKey]
  }
}

function refreshExternalSearch() {
  clearExternalQueryCache()
  startExternalSearch(externalPage.value || 1, true)
}

const addingExternalAvids = ref(new Set())
const handledScrapeJobs = new Set()
watch(
  () => resourceStore.visibleScrapeJobs,
  (jobs) => {
    for (const job of jobs) {
      if (job.state !== 'succeeded' || handledScrapeJobs.has(job.task_id)) continue
      handledScrapeJobs.add(job.task_id)
      if (job.action === 'add') {
        const item = externalResources.value.find((candidate) => candidate.avid === job.avid)
        if (item) markExternalItemInLibrary(item)
      }
      fetchResources(page.value)
      loadEntityInfo(entityId.value)
    }
  }
)

function saveExternalCache() {
  if (externalMeta.value?.partial) return
  const key = externalCacheKey()
  sessionStorage.setItem(
    key,
    JSON.stringify({
      results: externalResources.value,
      meta: externalMeta.value,
      page: externalPage.value,
      pagination: externalPagination.value,
      searched: externalSearched.value,
      sortBy: externalSortBy.value,
      sortOrder: externalSortOrder.value,
      pageCache: externalPageCache.value,
      job: getJobHandle(),
      timestamp: Date.now(),
    })
  )
}

function getExternalQueryKey() {
  return `${externalSource.value}|${externalSortBy.value}|${externalSortOrder.value}`
}

function getCachedExternalPage(pageNumber) {
  const queryKey = getExternalQueryKey()
  const queryCache = externalPageCache.value[queryKey]
  if (!queryCache) return null
  return queryCache[String(pageNumber)] || null
}

function setCachedExternalPage(pageNumber, payload) {
  const queryKey = getExternalQueryKey()
  if (!externalPageCache.value[queryKey]) {
    externalPageCache.value[queryKey] = {}
  }
  externalPageCache.value[queryKey][String(pageNumber)] = payload
}

function isExternalItemInLibrary(item) {
  return Boolean(item?.is_in_library || item?.in_library)
}

function markExternalItemInLibrary(item) {
  item.is_in_library = true
  item.in_library = true
}

async function scrollToTopAfterExternalRefresh() {
  await nextTick()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function restoreExternalCache() {
  const key = externalCacheKey()
  try {
    const cached = JSON.parse(sessionStorage.getItem(key))
    if (cached && !cached.meta?.partial && Date.now() - cached.timestamp < EXTERNAL_CACHE_TTL_MS) {
      restoreJob(cached.job)
      externalResources.value = cached.results
      externalMeta.value = cached.meta
      externalPage.value = cached.page
      externalPagination.value = cached.pagination || null
      externalSearched.value = cached.searched
      if (cached.sortBy) externalSortBy.value = cached.sortBy
      if (cached.sortOrder) externalSortOrder.value = cached.sortOrder
      if (cached.pageCache && typeof cached.pageCache === 'object') {
        externalPageCache.value = cached.pageCache
      }
      return true
    }
  } catch (e) {}
  return false
}

function applyExternalResult(response) {
  if (!response?.data || response.pagination?.page !== externalPage.value) return
  const existing = new Map(externalResources.value.map((item) => [item.avid, item]))
  const formattedResults = (response.data.external_results || []).map((r) => ({
    ...r,
    title: r.source_title || r.original_title,
    cover_url: r.thumbnail_url,
    raw_metrics: r.metrics,
    is_in_library: isExternalItemInLibrary(r) || isExternalItemInLibrary(existing.get(r.avid)),
  }))
  externalResources.value = formattedResults
  externalMeta.value = response.data.external_meta || {}
  externalPagination.value = response.pagination || null
  if (response.data.detail) {
    entity.value = response.data.detail
  }
}
const pageReadGuard = createSearchRequestGuard()
const readingExternalPage = ref(false)
async function changeExternalPage(p) {
  const request = pageReadGuard.begin()
  externalPage.value = p
  readingExternalPage.value = true
  externalError.value = ''
  try {
    const cached = getCachedExternalPage(p)
    const result = cached
      ? {
          data: { external_results: cached.results, external_meta: cached.meta },
          pagination: cached.pagination,
        }
      : await readExternalPage(p, 15)
    if (!pageReadGuard.current(request)) return
    if (!result) throw new Error('结果缓存已失效，请重新搜索')
    applyExternalResult(result)
    if (!result.data?.external_meta?.partial) {
      setCachedExternalPage(p, {
        results: externalResources.value,
        meta: externalMeta.value,
        pagination: externalPagination.value,
      })
    }
  } catch (error) {
    if (pageReadGuard.current(request)) externalError.value = error.message || '读取结果页失败'
  } finally {
    if (pageReadGuard.current(request)) readingExternalPage.value = false
  }
}

async function startExternalSearch(p = 1, forceRefresh = false) {
  if (
    !sourcesReady.value ||
    !sourceOptions.value.some((item) => item.value === externalSource.value)
  )
    return
  cancelExternalSearch()
  pageReadGuard.invalidate()
  readingExternalPage.value = false
  const request = requestGuard.begin()
  externalError.value = ''
  externalCancelled.value = false
  externalSearched.value = true
  externalPage.value = p

  const cachedPage = getCachedExternalPage(p)
  if (!forceRefresh && cachedPage) {
    loadingExternal.value = false
    externalResources.value = cachedPage.results || []
    externalMeta.value = cachedPage.meta || externalMeta.value
    externalPagination.value = cachedPage.pagination || externalPagination.value
    await scrollToTopAfterExternalRefresh()
    return
  }

  loadingExternal.value = true
  try {
    const params = {
      source: externalSource.value,
      page: p,
      page_size: 15,
      ordering:
        externalSortOrder.value === 'desc' ? '-' + externalSortBy.value : externalSortBy.value,
    }
    if (forceRefresh) {
      params.force_refresh = true
    }
    const response = await searchExternal(
      { entity_type: props.entityType, entity_id: Number(entityId.value), ...params },
      () => requestGuard.current(request),
      (result) => requestGuard.current(request) && applyExternalResult(result),
      () => ({ page: externalPage.value, page_size: 15 })
    )
    if (!requestGuard.current(request)) return
    if (response && response.data) {
      applyExternalResult(response)
      setCachedExternalPage(externalPage.value, {
        results: externalResources.value,
        meta: externalMeta.value,
        pagination: externalPagination.value,
      })
      saveExternalCache()
      await scrollToTopAfterExternalRefresh()
    }
  } catch (err) {
    if (!requestGuard.current(request)) return
    externalError.value = err.message || '获取外部搜索失败'
    toastStore.error(externalError.value)
    if (p === 1 && externalResources.value.length === 0) {
      externalPagination.value = null
    }
  } finally {
    if (requestGuard.current(request)) loadingExternal.value = false
  }
}

function resetExternalSearchState() {
  cancelExternalSearch()
  requestGuard.invalidate()
  pageReadGuard.invalidate()
  readingExternalPage.value = false
  loadingExternal.value = false
  externalError.value = ''
  externalCancelled.value = false
  externalSearched.value = false
  externalResources.value = []
  externalMeta.value = {}
  externalPage.value = 1
  externalPagination.value = null
  externalPageCache.value = {}
}

function syncExternalResourceStatus(avid, inLibrary) {
  let updated = false
  const item = externalResources.value.find((r) => r.avid === avid)
  if (item) {
    item.is_in_library = inLibrary
    item.in_library = inLibrary
    updated = true
  }
  const queryKey = getExternalQueryKey()
  const pageCache = externalPageCache.value[queryKey]
  if (pageCache) {
    Object.values(pageCache).forEach((payload) => {
      if (payload && payload.results) {
        const cachedItem = payload.results.find((r) => r.avid === avid)
        if (cachedItem) {
          cachedItem.is_in_library = inLibrary
          cachedItem.in_library = inLibrary
          updated = true
        }
      }
    })
  }
  if (updated) saveExternalCache()
}

async function handleAddExternal(item) {
  if (addingExternalAvids.value.has(item.avid)) return
  addingExternalAvids.value.add(item.avid)
  try {
    await resourceStore.addResource(item.avid, item.source || externalSource.value)
  } catch (err) {
    if (err.httpStatus === 409 || err.code === 409 || err?.response?.status === 409) {
      toastStore.info(`${item.avid} 已经在资源库中`)
      markExternalItemInLibrary(item)
      saveExternalCache()
    } else {
      toastStore.error(err.message || '添加失败')
    }
  } finally {
    addingExternalAvids.value.delete(item.avid)
  }
}

function handleOpenExternal(item) {
  if (item.detail_url) {
    window.open(item.detail_url, '_blank')
  }
}

function handleViewExternal(item) {
  router.push({ path: `/resource/${item.avid}` })
}

// batch & search state (reuse logic from ResourcesView)
const selectedAvids = ref(new Set())
const batchLoading = ref(false)
const batchMode = ref(false)
const selectedCount = computed(() => selectedAvids.value.size)
const refreshing = ref(false)

function toggleSelect(avid, checked) {
  if (!avid) return
  if (checked) selectedAvids.value.add(avid)
  else selectedAvids.value.delete(avid)
  selectedAvids.value = new Set(selectedAvids.value)
}

function toggleSelectAll(checked) {
  if (checked) {
    const arr = displayedResources.value.map((r) => r.avid)
    selectedAvids.value = new Set(arr)
  } else {
    selectedAvids.value = new Set()
  }
}

function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) selectedAvids.value = new Set()
}

async function handleBatchDownload() {
  if (selectedAvids.value.size === 0) return
  batchLoading.value = true
  try {
    const avids = Array.from(selectedAvids.value)
    await resourceStore.batchSubmitDownload(avids)
    selectedAvids.value = new Set()
    await fetchResources()
    toastStore.success(`已提交 ${avids.length} 个下载任务`)
  } catch (err) {
    toastStore.error(err.message || '批量提交下载失败')
  } finally {
    batchLoading.value = false
  }
}

async function handleBatchRefresh() {
  if (selectedAvids.value.size === 0) return
  batchLoading.value = true
  try {
    const avids = Array.from(selectedAvids.value)
    await resourceStore.batchRefresh(avids)
    selectedAvids.value = new Set()
  } catch (err) {
    toastStore.error(err.message || '批量刷新失败')
  } finally {
    batchLoading.value = false
  }
}

const showBatchDeleteConfirm = ref(false)
const batchDeleteAction = ref(null)

function handleBatchDelete() {
  if (selectedAvids.value.size === 0) return
  showBatchDeleteConfirm.value = true
}

async function confirmBatchDelete(action) {
  batchDeleteAction.value = action
  showBatchDeleteConfirm.value = false
  batchLoading.value = true
  try {
    const avids = Array.from(selectedAvids.value)
    const { succeeded, failed } = await resourceStore.batchDelete(avids, action)
    const actionText = action === 'delete-video' ? '删除视频' : '删除全部数据'
    if (failed.length) {
      toastStore.error(
        `${actionText}：成功 ${succeeded.length} 个，失败 ${failed.length} 个；可重试失败项`
      )
    } else {
      toastStore.success(`已${actionText}: ${succeeded.length} 个资源`)
    }
    selectedAvids.value = new Set(failed.map((item) => item.avid).filter(Boolean))
    await fetchResources()
    if (action === 'delete' || action === 'delete-all') {
      succeeded.forEach((item) => syncExternalResourceStatus(item.avid, false))
      loadEntityInfo(entityId.value)
    }
  } catch (err) {
    toastStore.error(err.message || '批量删除失败')
  } finally {
    batchLoading.value = false
    batchDeleteAction.value = null
  }
}

async function loadEntityInfo(id) {
  const request = infoGuard.begin()
  loadingEntity.value = true
  try {
    const response = await entityApi.getList({ id: String(id), page: 1, page_size: 1 })
    if (!infoGuard.current(request)) return
    if (
      response &&
      response.code === 200 &&
      Array.isArray(response.data) &&
      response.data.length > 0
    ) {
      entity.value = response.data[0]
    } else {
      // fallback: set id and empty name
      entity.value = { id, name: String(id), resource_count: 0, avatar_url: null }
    }
  } catch (_error) {
    if (!infoGuard.current(request)) return
    entity.value = { id, name: String(id), resource_count: 0, avatar_url: null }
  } finally {
    if (infoGuard.current(request)) loadingEntity.value = false
  }
}

async function fetchResources(p = 1) {
  const pg = Number(p || 1)
  page.value = pg

  const params = {
    page: pg,
    page_size: pageSize.value,
    [props.entityType]: entityId.value,
    search: searchQuery.value,
    sort_by: sortBy.value,
    order: sortOrder.value,
  }

  // 处理状态过滤
  if (filterStatus.value === 'watched') {
    params.watched = true
  } else if (filterStatus.value === 'unwatched') {
    params.watched = false
  } else if (filterStatus.value === 'favorite') {
    params.is_favorite = true
  } else if (filterStatus.value !== 'all') {
    params.status = filterStatus.value
  }

  await resourceStore.fetchResources(params)
}

function onSortChange() {
  page.value = 1
  fetchResources(1)
}

async function handleDownload(avid) {
  try {
    await resourceStore.submitDownload(avid)
    toastStore.success(`${avid} 下载任务已提交`)
  } catch (err) {
    toastStore.error(err.message || '下载失败')
  }
}

async function handleRefresh(avid) {
  try {
    await resourceStore.refreshResource(avid)
  } catch (err) {
    toastStore.error(err.message || '刷新失败')
  }
}

async function handleDeleteResource(avid) {
  try {
    await resourceApi.delete(avid)
    await handleManualRefresh()
    toastStore.success(`${avid} 已被完全删除`)
    // 同步到外部搜索列表
    syncExternalResourceStatus(avid, false)
    loadEntityInfo(entityId.value)
  } catch (err) {
    toastStore.error(err.message || '删除失败')
  }
}

async function handleDeleteFile(avid) {
  try {
    await downloadApi.deleteFile(avid)
    await handleManualRefresh()
    toastStore.success(`${avid} 已删除视频`)
  } catch (err) {
    toastStore.error(err.message || '删除失败')
  }
}

async function handleManualRefresh() {
  refreshing.value = true
  try {
    await fetchResources()
    toastStore.success('资源列表已刷新')
  } catch (err) {
    toastStore.error(err.message || '刷新失败')
  } finally {
    refreshing.value = false
  }
}

onMounted(async () => {
  const navigation = navigationGuard.begin()
  await loadSearchSources()
  if (!navigationGuard.current(navigation)) return
  entityId.value = route.params[routeParam]
  await loadEntityInfo(entityId.value)
  if (!navigationGuard.current(navigation)) return
  await fetchResources(page.value)
  if (navigationGuard.current(navigation)) restoreExternalCache()
})

// 状态变化时同步到 URL
watch(
  [currentTab, page, pageSize, searchQuery, sortBy, sortOrder, filterStatus],
  () => {
    const query = {
      tab: currentTab.value,
      page: page.value,
    }
    if (pageSize.value !== 18) query.pageSize = pageSize.value
    if (searchQuery.value) query.search = searchQuery.value
    if (sortBy.value !== 'metadata_create_time') query.sortBy = sortBy.value
    if (sortOrder.value !== 'desc') query.order = sortOrder.value
    if (filterStatus.value !== 'all') query.status = filterStatus.value
    if (route.query.from) query.from = route.query.from

    router.replace({ query })
  },
  { deep: true }
)

watch(
  () => route.params[routeParam],
  async (v) => {
    const navigation = navigationGuard.begin()
    resourceStore.cancelResourceQuery()
    entityId.value = v
    resetExternalSearchState()
    await loadEntityInfo(entityId.value)
    if (!navigationGuard.current(navigation)) return
    page.value = 1
    await fetchResources(1)
    if (navigationGuard.current(navigation)) restoreExternalCache()
  }
)

function changePage(newPage) {
  page.value = Number(newPage) || 1
  fetchResources(page.value)
}

function onPageSizeChange(newSize) {
  if (typeof newSize !== 'undefined' && newSize !== null) {
    pageSize.value = Number(newSize) || pageSize.value
  }
  page.value = 1
  fetchResources(1)
}

// debounce search
let _searchTimer = null
watch(searchQuery, () => {
  if (_searchTimer) clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => {
    page.value = 1
    fetchResources(1)
  }, 300)
})

onBeforeUnmount(() => {
  navigationGuard.invalidate()
  infoGuard.invalidate()
  resourceStore.cancelResourceQuery()
  pageReadGuard.invalidate()
  cancelExternalSearch()
  requestGuard.invalidate()
  if (_searchTimer) clearTimeout(_searchTimer)
})

const displayedResources = computed(() => {
  const raw =
    resourceStore.resources && resourceStore.resources.value !== undefined
      ? resourceStore.resources.value
      : resourceStore.resources
  if (Array.isArray(raw)) return raw
  if (raw && Array.isArray(raw.results)) return raw.results
  if (raw && Array.isArray(raw.data)) return raw.data
  return []
})

const initialChar = computed(
  () => entity.value?.name?.trim().slice(0, isActor ? 1 : 2) || (isActor ? '' : '类')
)

const displayedCount = computed(() => {
  const rc =
    entity.value && typeof entity.value.resource_count !== 'undefined'
      ? entity.value.resource_count
      : null
  if (rc !== null && rc !== undefined) return rc
  return resourceStore.pagination && resourceStore.pagination.total
    ? resourceStore.pagination.total
    : 0
})

function goBack() {
  const fromPath = route.query.from
  if (fromPath) router.push(fromPath)
  else router.back()
}
</script>

<template>
  <div class="px-6 pt-2 pb-6">
    <button class="tw-back-btn mb-10" @click="goBack">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M19 12H5M12 5l-7 7 7 7"
        />
      </svg>
      返回
    </button>
    <div class="mb-6 flex items-center gap-6">
      <div
        class="rounded-full flex items-center justify-center text-4xl overflow-hidden border-2"
        :class="isActor ? 'w-20 h-20' : 'w-28 h-28 font-bold'"
        style="
          color: var(--detail-badge-text);
          background: var(--detail-badge-bg);
          border-color: var(--detail-badge-border);
          box-shadow: var(--detail-badge-shadow);
        "
      >
        <img
          v-if="isActor && settingsStore.showActorAvatar && entity.id && entity.avatar_filename"
          :src="entityApi.getAvatarUrl(entity.id)"
          :alt="entity.name"
          class="w-full h-full object-cover"
        />
        <span v-else>{{ initialChar }}</span>
      </div>
      <div class="flex-1">
        <div class="font-semibold text-primary" :class="isActor ? 'text-xl' : 'text-2xl'">
          {{ entity.name }}
        </div>
        <div class="text-sm text-[var(--text-muted)]">共有 {{ displayedCount }} 部作品</div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex border-b border-[var(--border-color)] mb-6 gap-6">
      <button
        :class="[
          'py-2 px-1 border-b-2 font-medium transition-colors',
          currentTab === 'local'
            ? 'border-[var(--accent-primary)] text-[var(--accent-primary)]'
            : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]',
        ]"
        @click="currentTab = 'local'"
      >
        本地资源
      </button>
      <button
        :class="[
          'py-2 px-1 border-b-2 font-medium transition-colors',
          currentTab === 'external'
            ? 'border-[var(--accent-primary)] text-[var(--accent-primary)]'
            : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]',
        ]"
        @click="currentTab = 'external'"
      >
        外部搜索
      </button>
    </div>

    <div v-show="currentTab === 'local'">
      <!-- Controls -->
      <ResourceSearchBar
        v-model:search-query="searchQuery"
        v-model:filter-status="filterStatus"
        v-model:sort-by="sortBy"
        v-model:sort-order="sortOrder"
        :show-favorite-filter="true"
        :show-watched-filter="true"
        :show-metadata-update-sort="true"
        @sort-change="onSortChange"
      />

      <!-- Batch controls -->
      <BatchControls
        :batch-mode="batchMode"
        :batch-loading="batchLoading"
        :selected-count="selectedCount"
        :total-count="displayedResources.length"
        @toggle-batch-mode="toggleBatchMode"
        @toggle-select-all="toggleSelectAll"
        @batch-refresh="handleBatchRefresh"
        @batch-download="handleBatchDownload"
        @batch-delete="handleBatchDelete"
      />
      <!-- 批量删除确认对话框 -->
      <ConfirmDialog
        v-model:show="showBatchDeleteConfirm"
        title="批量删除资源"
        :message="`即将删除 ${selectedAvids.size} 个资源，请选择删除方式：`"
        type="danger"
        confirm-text="只删除视频"
        cancel-text="取消"
        @confirm="() => confirmBatchDelete('delete-video')"
        @cancel="() => (showBatchDeleteConfirm = false)"
      >
        <template #extra-button>
          <button class="tw-btn-danger" @click="() => confirmBatchDelete('delete-all')">
            全部删除
          </button>
        </template>
      </ConfirmDialog>
      <!-- Loading State -->
      <LoadingSpinner v-if="resourceStore.loading" size="large" text="加载资源中..." />

      <!-- Empty State -->
      <EmptyState
        v-else-if="displayedResources.length === 0"
        icon="empty"
        title="暂无资源"
        :description="searchQuery ? '没有找到匹配的资源' : '点击右上角添加您的第一个资源'"
      >
        <template #action>
          <RouterLink to="/add" class="tw-btn-primary"> 添加资源 </RouterLink>
        </template>
      </EmptyState>

      <!-- Resources Grid -->
      <div v-else class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        <ResourceCard
          v-for="resource in displayedResources"
          :key="resource.avid"
          :resource="resource"
          :selectable="batchMode"
          :selected="selectedAvids.has(resource.avid)"
          :cover-size="'medium'"
          @toggle-select="toggleSelect"
          @download="handleDownload"
          @refresh="handleRefresh"
          @delete="handleDeleteResource"
          @delete-file="handleDeleteFile"
        />
      </div>
      <ResourcePagination
        :page="page"
        :pages="resourceStore.pagination.pages"
        :page-size="pageSize"
        :total="resourceStore.pagination.total"
        @change-page="changePage"
        @change-page-size="onPageSizeChange"
      />
    </div>

    <div v-show="currentTab === 'external'">
      <div class="flex flex-col items-center gap-3 mb-6">
        <AppButton
          v-if="!loadingExternal"
          :disabled="!sourcesReady || !externalSource"
          @click="startExternalSearch(1, externalSearched)"
        >
          {{ externalSearched ? '重新搜索' : '开始搜索' }}
        </AppButton>
        <AppButton
          v-else
          variant="neutral"
          :disabled="cancellingExternal"
          @click="stopExternalSearch"
        >
          {{ cancellingExternal ? '正在取消…' : '取消搜索' }}
        </AppButton>
        <span class="text-secondary text-sm">搜索源</span>
        <CustomSelect
          :model-value="externalSource"
          :options="sourceOptions"
          :disabled="loadingExternal"
          class="w-36"
          @update:model-value="onExternalSourceChange"
        />
        <button
          v-if="sourcesError"
          class="tw-btn tw-btn-primary rounded-lg px-3 py-2"
          @click="loadSearchSources"
        >
          重新加载搜索源
        </button>
      </div>
      <p v-if="sourcesError" class="text-muted mb-4" role="alert">{{ sourcesError }}</p>
      <p v-if="externalSource === 'missav'" class="text-muted text-sm mb-4">
        缺少演员或类别映射时按名称关键词匹配；排序沿用源站，列表不提供播放量和收藏量数值。
      </p>
      <p v-if="loadingExternal" class="text-muted text-sm mb-4" role="status">
        {{
          searchStatus === 'running'
            ? '正在搜索，已获取的结果会逐页显示…'
            : '搜索已提交，正在等待处理…'
        }}
      </p>
      <p v-if="loadingExternal && searchProgress" class="text-muted text-sm mb-4" role="status">
        已完成 {{ searchProgress.pagesCompleted }} /
        {{ searchProgress.fetchPages }} 个源站页面，结果与排序仍在更新。
      </p>
      <p
        v-if="!loadingExternal && externalMeta.partial && externalError"
        class="text-muted text-sm mb-4"
      >
        已保留成功获取的结果；列表不完整，可刷新重试。
      </p>
      <p v-if="externalError" class="text-accent-danger mb-4" role="alert">
        搜索失败：{{ externalError }}
      </p>
      <p v-if="externalCancelled" class="text-muted mb-4 text-center" role="status">
        搜索已取消，已获取的结果仍可查看。
      </p>
      <div
        v-if="!externalSearched && !loadingExternal"
        class="flex flex-col items-center justify-center py-20 text-center"
      >
        <svg
          class="w-10 h-10 mb-4 text-muted"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18" />
        </svg>
        <h3 class="text-xl font-medium text-[var(--text-primary)] mb-2">外部搜索</h3>
        <p class="text-[var(--text-muted)] mb-6 max-w-md">
          点击上方按钮，开始使用所选外部数据源 搜索与该{{
            entityLabel
          }}相关的资源。搜索过程可能需要一些时间，请耐心等待。
        </p>
      </div>

      <div
        v-else-if="loadingExternal && externalResources.length === 0"
        class="flex items-center justify-center py-20"
      >
        <LoadingSpinner size="large" text="正在执行外部搜索，请耐心等待..." />
      </div>

      <template v-else>
        <div
          class="mb-4 text-sm text-[var(--text-muted)] flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        >
          <span>来源: {{ externalSource }}</span>
          <div class="flex items-center gap-2">
            <span class="text-[var(--text-muted)]">排序</span>
            <CustomSelect
              :model-value="externalSortBy"
              :options="externalSortByOptions"
              :disabled="loadingExternal"
              class="w-28"
              @update:model-value="(v) => ((externalSortBy = v), onExternalSortChange())"
            />
            <CustomSelect
              :model-value="externalSortOrder"
              :options="availableSortOrders"
              :disabled="loadingExternal"
              class="w-24"
              @update:model-value="(v) => ((externalSortOrder = v), onExternalSortChange())"
            />
            <button
              class="tw-btn bg-[var(--bg-secondary)] border border-[var(--border-color)] hover:border-[var(--accent-primary)] text-[var(--text-primary)] px-3 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="loadingExternal"
              @click="refreshExternalSearch"
            >
              刷新外部结果
            </button>
          </div>
        </div>

        <EmptyState
          v-if="externalResources.length === 0 && !externalError"
          icon="empty"
          :title="externalCancelled ? '搜索已取消' : '外部搜索暂无结果'"
          :description="`未能从外部源获取到关于该${entityLabel}的更多资源`"
        />

        <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-6 mb-6">
          <ExternalSearchCard
            v-for="resource in externalResources"
            :key="resource.avid"
            :item="resource"
            :added="isExternalItemInLibrary(resource)"
            :adding="addingExternalAvids.has(resource.avid)"
            @add="handleAddExternal(resource)"
            @view="handleViewExternal(resource)"
            @open="handleOpenExternal(resource)"
          />
        </div>

        <div
          v-if="externalResources.length > 0"
          class="flex justify-center items-center gap-4 mt-6"
        >
          <button
            class="tw-btn bg-[var(--bg-secondary)] border border-[var(--border-color)] hover:border-[var(--accent-primary)] text-[var(--text-primary)] px-6 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="externalPage === 1 || readingExternalPage"
            @click="changeExternalPage(externalPage - 1)"
          >
            上一页
          </button>
          <span class="text-[var(--text-muted)] text-sm">
            第 {{ externalPage }} 页
            <template v-if="externalPagination && externalPagination.pages">
              / {{ loadingExternal || externalMeta.partial ? '当前可浏览' : '共' }}
              {{ externalPagination.pages }} 页
            </template>
          </span>
          <button
            class="tw-btn bg-[var(--bg-secondary)] border border-[var(--border-color)] hover:border-[var(--accent-primary)] text-[var(--text-primary)] px-6 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="
              readingExternalPage ||
              (externalPagination && externalPagination.pages
                ? externalPage >= externalPagination.pages
                : externalResources.length < 15)
            "
            @click="changeExternalPage(externalPage + 1)"
          >
            下一页
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
