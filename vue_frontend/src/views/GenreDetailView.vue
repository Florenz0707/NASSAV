<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useToastStore } from '../stores/toast'
import { useRoute, useRouter } from 'vue-router'
import { useResourceStore } from '../stores/resource'
import { genreApi, resourceApi, downloadApi } from '../api'
import ResourceCard from '../components/ResourceCard.vue'
import ResourcePagination from '../components/ResourcePagination.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'
import BatchControls from '../components/BatchControls.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ResourceSearchBar from '../components/ResourceSearchBar.vue'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()

const genreId = ref(route.params.genreId || '')
// 从 URL query 初始化状态
const page = ref(parseInt(route.query.page) || 1)
const pageSize = ref(parseInt(route.query.pageSize) || 18)
const sortBy = ref(route.query.sortBy || 'metadata_create_time')
const sortOrder = ref(route.query.order || 'desc')
const searchQuery = ref(route.query.search || '')
const filterStatus = ref(route.query.status || 'all')

const loadingGenre = ref(false)
const genre = ref({ id: genreId.value, name: '', resource_count: 0 })
const toastStore = useToastStore()
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
    await fetchResources()
    toastStore.success(`已刷新 ${avids.length} 个资源`)
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
    await resourceStore.batchDelete(avids, action)
    const actionText = action === 'delete-video' ? '删除视频' : '删除全部数据'
    toastStore.success(`已${actionText}: ${avids.length} 个资源`)
    selectedAvids.value = new Set()
    await fetchResources()
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
    toastStore.success(`${avid} 已刷新`)
  } catch (err) {
    toastStore.error(err.message || '刷新失败')
  }
}

async function handleDeleteResource(avid) {
  try {
    await resourceApi.delete(avid)
    await handleManualRefresh()
    toastStore.success(`${avid} 已被完全删除`)
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
  genreId.value = route.params.genreId
  await loadGenreInfo(genreId.value)
  await fetchResources(1)
})

// 状态变化时同步到 URL
watch(
  [page, pageSize, searchQuery, sortBy, sortOrder],
  () => {
    const query = {
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
    await loadGenreInfo(genreId.value)
    page.value = 1
    await fetchResources(1)
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
    <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-6">
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
</template>
