<script setup>
import { useExternalSearchTask } from '../composables/useExternalSearchTask.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useToastStore } from '../stores/toast'
import { useRoute, useRouter } from 'vue-router'
import { useResourceStore } from '../stores/resource'
import { genreApi, resourceApi, downloadApi } from '../api'
import ExternalSearchCard from '../components/ExternalSearchCard.vue'
import ResourceCard from '../components/ResourceCard.vue'
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

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()

const genreId = ref(route.params.genreId || '')
// 从 URL query 初始化状态
const currentTab = ref(route.query.tab || 'local')
const page = ref(parseInt(route.query.page) || 1)
const pageSize = ref(parseInt(route.query.pageSize) || 18)
const sortBy = ref(route.query.sortBy || 'metadata_create_time')
const sortOrder = ref(route.query.order || 'desc')
const searchQuery = ref(route.query.search || '')
const filterStatus = ref(route.query.status || 'all')

const loadingGenre = ref(false)
const genre = ref({ id: genreId.value, name: '', resource_count: 0 })
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
} = useExternalSearchSources('genre')
const requestGuard = createSearchRequestGuard()
const {
  status: searchStatus,
  progress: searchProgress,
  search: searchExternal,
  cancel: cancelExternalSearch,
} = useExternalSearchTask()
const externalError = ref('')
function externalCacheKey() {
  return `external_cn_v4_genre_${genreId.value}_${externalSource.value}`
}
function onExternalSourceChange(value) {
  cancelExternalSearch()
  requestGuard.invalidate()
  externalSource.value = value
  externalSortOrder.value = 'desc'
  resetExternalSearchState()
  restoreExternalCache()
  if (!externalSearched.value) startExternalSearch(1)
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
  externalPage.value = 1
  startExternalSearch(1)
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
      loadGenreInfo(genreId.value)
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

async function startExternalSearch(p = 1, forceRefresh = false) {
  if (
    !sourcesReady.value ||
    !sourceOptions.value.some((item) => item.value === externalSource.value)
  )
    return
  cancelExternalSearch()
  const request = requestGuard.begin()
  externalError.value = ''
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
      page_size: 20,
      ordering:
        externalSortOrder.value === 'desc' ? '-' + externalSortBy.value : externalSortBy.value,
    }
    if (forceRefresh) {
      params.force_refresh = true
    }
    function applyResult(response) {
      if (!requestGuard.current(request) || !response?.data) return
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
        genre.value = response.data.detail
      }
    }
    const response = await searchExternal(
      { entity_type: 'genre', entity_id: Number(genreId.value), ...params },
      () => requestGuard.current(request),
      (result) => applyResult(result)
    )
    if (!requestGuard.current(request)) return
    if (response && response.data) {
      applyResult(response)
      setCachedExternalPage(p, {
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
  loadingExternal.value = false
  externalError.value = ''
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
      loadGenreInfo(genreId.value)
    }
  } catch (err) {
    toastStore.error(err.message || '批量删除失败')
  } finally {
    batchLoading.value = false
    batchDeleteAction.value = null
  }
}

async function loadGenreInfo(id) {
  loadingGenre.value = true
  try {
    const response = await genreApi.getList({ id: String(id), page: 1, page_size: 1 })
    if (
      response &&
      response.code === 200 &&
      Array.isArray(response.data) &&
      response.data.length > 0
    ) {
      genre.value = response.data[0]
    } else {
      // fallback: set id and empty name
      genre.value = { id, name: String(id), resource_count: 0 }
    }
  } catch (_error) {
    genre.value = { id, name: String(id), resource_count: 0 }
  } finally {
    loadingGenre.value = false
  }
}

async function fetchResources(p = 1) {
  const pg = Number(p || 1)
  page.value = pg

  const params = {
    page: pg,
    page_size: pageSize.value,
    genre: genreId.value,
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
    loadGenreInfo(genreId.value)
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
  await loadSearchSources()
  genreId.value = route.params.genreId
  await loadGenreInfo(genreId.value)
  await fetchResources(1)
  restoreExternalCache()
  if (currentTab.value === 'external' && !externalSearched.value) startExternalSearch(1)
})

watch(
  currentTab,
  (newTab) => {
    if (newTab === 'external' && !externalSearched.value && !loadingExternal.value) {
      startExternalSearch(1)
    }
  },
  { immediate: true }
)

// 状态变化时同步到 URL
watch(
  [currentTab, page, pageSize, searchQuery, sortBy, sortOrder],
  () => {
    const query = {
      tab: currentTab.value,
      page: page.value,
    }
    if (pageSize.value !== 18) query.pageSize = pageSize.value
    if (searchQuery.value) query.search = searchQuery.value
    if (sortBy.value !== 'metadata_create_time') query.sortBy = sortBy.value
    if (sortOrder.value !== 'desc') query.order = sortOrder.value
    if (route.query.from) query.from = route.query.from

    router.replace({ query })
  },
  { deep: true }
)

watch(
  () => route.params.genreId,
  async (v) => {
    genreId.value = v
    resetExternalSearchState()
    await loadGenreInfo(genreId.value)
    page.value = 1
    await fetchResources(1)
    restoreExternalCache()
    if (currentTab.value === 'external' && !externalSearched.value) startExternalSearch(1)
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

const iconText = computed(() => {
  if (!genre.value || !genre.value.name) return '类'
  return genre.value.name.trim().slice(0, 2)
})

const displayedCount = computed(() => {
  const rc =
    genre.value && typeof genre.value.resource_count !== 'undefined'
      ? genre.value.resource_count
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
        class="w-28 h-28 rounded-full flex items-center justify-center text-4xl font-bold border-2"
        style="
          color: var(--detail-badge-text);
          background: var(--detail-badge-bg);
          border-color: var(--detail-badge-border);
          box-shadow: var(--detail-badge-shadow);
        "
      >
        {{ iconText }}
      </div>
      <div class="flex-1">
        <div class="text-2xl font-semibold text-[var(--text-primary)]">
          {{ genre.name }}
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
        icon="◇"
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
      <div class="flex items-center gap-3 mb-4 text-text-primary">
        <span>搜索源</span>
        <CustomSelect
          :model-value="externalSource"
          :options="sourceOptions"
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
      <p v-if="sourcesError" class="text-text-muted mb-4" role="alert">{{ sourcesError }}</p>
      <p v-if="externalSource === 'missav'" class="text-text-muted text-sm mb-4">
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
        {{ searchProgress.fetchPages }} 页，结果与排序仍在更新。
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
      <div
        v-if="!externalSearched && !loadingExternal"
        class="flex flex-col items-center justify-center py-20 text-center"
      >
        <svg
          class="w-10 h-10 mb-4 text-text-muted"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18" />
        </svg>
        <h3 class="text-xl font-medium text-[var(--text-primary)] mb-2">外部搜索</h3>
        <p class="text-[var(--text-muted)] mb-6 max-w-md">
          点击下方按钮，开始使用外部数据源 (可选择 Jable 或 MissAV)
          搜索与该类别相关的资源。搜索过程可能需要一些时间，请耐心等待。
        </p>
        <button
          class="tw-btn tw-btn-primary px-8 py-2 rounded-lg"
          :disabled="!sourcesReady || !externalSource"
          @click="startExternalSearch(1)"
        >
          开始搜索
        </button>
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
              class="w-28"
              @update:model-value="(v) => ((externalSortBy = v), onExternalSortChange())"
            />
            <CustomSelect
              :model-value="externalSortOrder"
              :options="availableSortOrders"
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
          icon="◇"
          title="外部搜索暂无结果"
          description="未能从外部源获取到关于该类别的更多资源"
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
            :disabled="externalPage === 1 || loadingExternal"
            @click="startExternalSearch(externalPage - 1)"
          >
            上一页
          </button>
          <span class="text-[var(--text-muted)] text-sm">
            第 {{ externalPage }} 页
            <template v-if="externalPagination && externalPagination.pages">
              / 共 {{ externalPagination.pages }} 页
            </template>
          </span>
          <button
            class="tw-btn bg-[var(--bg-secondary)] border border-[var(--border-color)] hover:border-[var(--accent-primary)] text-[var(--text-primary)] px-6 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="
              loadingExternal ||
              (externalPagination && externalPagination.pages
                ? externalPage >= externalPagination.pages
                : externalResources.length < 20)
            "
            @click="startExternalSearch(externalPage + 1)"
          >
            下一页
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
