<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useResourceStore } from '../stores/resource'
import { useToastStore } from '../stores/toast'
import ResourcePagination from '../components/ResourcePagination.vue'
import ResourceCard from '../components/ResourceCard.vue'
import EmptyState from '../components/EmptyState.vue'
import BatchControls from '../components/BatchControls.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ResourceSearchBar from '../components/ResourceSearchBar.vue'

const resourceStore = useResourceStore()
const toastStore = useToastStore()

const selectedAvids = ref(new Set())
const batchLoading = ref(false)
const batchMode = ref(false)

const selectedCount = computed(() => selectedAvids.value.size)

function toggleSelect(avid, checked) {
  if (!avid) return
  if (checked) selectedAvids.value.add(avid)
  else selectedAvids.value.delete(avid)
  // trigger reactivity for Set
  selectedAvids.value = new Set(selectedAvids.value)
}

function toggleSelectAll(checked) {
  if (checked) {
    const arr = filteredResources.value.map((r) => r.avid)
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
    toastStore.success(`已提交 ${avids.length} 个下载任务`)
    selectedAvids.value = new Set()
    await fetchResourceList()
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
    toastStore.success(`已刷新 ${avids.length} 个资源`)
    selectedAvids.value = new Set()
    await fetchResourceList()
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
    await fetchResourceList()
  } catch (err) {
    toastStore.error(err.message || '批量删除失败')
  } finally {
    batchLoading.value = false
    batchDeleteAction.value = null
  }
}

const route = useRoute()
const router = useRouter()

// 从 URL query 初始化状态
const page = ref(parseInt(route.query.page) || 1)
const pageSize = ref(parseInt(route.query.pageSize) || 18)
const searchQuery = ref(route.query.search || '')
const filterStatus = ref(route.query.status || 'all')
const sortBy = ref(route.query.sortBy || 'metadata_create_time')
const sortOrder = ref(route.query.order || 'desc')
const actorParam = ref(route.query && route.query.actor ? route.query.actor : '')
const genreParam = ref(route.query && route.query.genre ? route.query.genre : '')
// 使用 store 中的 pagination（模板中自动解包）
const refreshing = ref(false)

onMounted(async () => {
  await fetchResourceList()
})

// 状态变化时同步到 URL
watch(
  [page, pageSize, searchQuery, filterStatus, sortBy, sortOrder],
  () => {
    const query = {
      page: page.value,
    }
    if (pageSize.value !== 18) query.pageSize = pageSize.value
    if (searchQuery.value) query.search = searchQuery.value
    if (filterStatus.value !== 'all') query.status = filterStatus.value
    if (sortBy.value !== 'metadata_create_time') query.sortBy = sortBy.value
    if (sortOrder.value !== 'desc') query.order = sortOrder.value
    if (actorParam.value) query.actor = actorParam.value
    if (genreParam.value) query.genre = genreParam.value

    router.replace({ query })
  },
  { deep: true }
)

async function fetchResourceList() {
  console.debug('[view] fetchResourceList called', {
    sort_by: sortBy.value,
    order: sortOrder.value,
    page: page.value,
    page_size: pageSize.value,
    status: filterStatus.value,
    search: searchQuery.value,
  })

  const params = {
    sort_by: sortBy.value,
    order: sortOrder.value,
    page: page.value,
    page_size: pageSize.value,
    actor: actorParam.value || undefined,
    genre: genreParam.value || undefined,
  }

  // 添加搜索参数
  if (searchQuery.value && searchQuery.value.trim()) {
    params.search = searchQuery.value.trim()
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

// include actor filter if provided in query
watch(
  () => route.query.actor,
  (v) => {
    actorParam.value = v || ''
    page.value = 1
    fetchResourceList()
  }
)

// include genre filter if provided in query
watch(
  () => route.query.genre,
  (v) => {
    genreParam.value = v || ''
    page.value = 1
    fetchResourceList()
  }
)

// Use server-side filtered/sorted resources. Normalize the response shape to an array.
// 搜索已在后端完成，前端直接使用返回的数据
const filteredResources = computed(() => {
  const raw =
    resourceStore.resources && resourceStore.resources.value !== undefined
      ? resourceStore.resources.value
      : resourceStore.resources
  let resources = []
  if (Array.isArray(raw)) resources = raw
  else if (raw && Array.isArray(raw.results)) resources = raw.results
  else if (raw && Array.isArray(raw.data)) resources = raw.data

  return resources
})

// debounce search input - 触发后端搜索请求
let _searchTimer = null
watch(searchQuery, () => {
  if (_searchTimer) clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => {
    // 搜索时重置页码为1
    page.value = 1
    fetchResourceList()
  }, 300)
})

// trigger when filter status changes
watch(filterStatus, () => {
  page.value = 1
  fetchResourceList()
})

// scroll to top when page changes
watch(page, () => {
  window.scrollTo({ top: 0, behavior: 'smooth' })
})

onBeforeUnmount(() => {
  if (_searchTimer) clearTimeout(_searchTimer)
})

async function handleDownload(avid) {
  try {
    await resourceStore.submitDownload(avid)
    toastStore.success(`${avid} 下载任务已提交`)
  } catch (err) {
    toastStore.error(err.message || '下载失败')
  }
}

async function handleRefresh(avid, params = null) {
  try {
    await resourceStore.refreshResource(avid, params)
    toastStore.success(`${avid} 已刷新`)
  } catch (err) {
    toastStore.error(err.message || '刷新失败')
  }
}

async function handleDeleteResource(_avid) {
  // ResourceCard 已执行删除，这里只需刷新列表
  refreshing.value = true
  try {
    await fetchResourceList()
  } catch (err) {
    console.error('刷新列表失败:', err)
  } finally {
    refreshing.value = false
  }
}

async function handleDeleteFile(_avid) {
  // ResourceCard 已执行删除，这里只需刷新列表
  refreshing.value = true
  try {
    await fetchResourceList()
  } catch (err) {
    console.error('刷新列表失败:', err)
  } finally {
    refreshing.value = false
  }
}

async function handleManualRefresh() {
  refreshing.value = true
  try {
    await fetchResourceList()
    toastStore.success('列表已刷新')
  } catch (err) {
    toastStore.error(err.message || '刷新失败')
  } finally {
    refreshing.value = false
  }
}

function onSortChange() {
  page.value = 1
  fetchResourceList()
}

function changePage(newPage) {
  page.value = Number(newPage) || 1
  fetchResourceList()
}

function onPageSizeChange(newSize) {
  if (typeof newSize !== 'undefined' && newSize !== null) {
    pageSize.value = Number(newSize) || pageSize.value
  }
  page.value = 1
  fetchResourceList()
}
</script>

<template>
  <div class="animate-[fadeIn_0.5s_ease]">
    <!-- Page Header -->
    <div class="mb-8">
      <h1 class="text-[2rem] font-bold text-[var(--text-primary)] mb-2">资源库</h1>
      <!-- Results Info -->
      <div v-if="!resourceStore.loading" class="mb-6 text-[var(--text-muted)] text-sm">
        <span>管理您的 {{ resourceStore.pagination.total }} 个资源</span>
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
      :total-count="filteredResources.length"
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
      confirm-text="删除视频"
      cancel-text="取消"
      @confirm="() => confirmBatchDelete('delete-video')"
      @cancel="() => (showBatchDeleteConfirm = false)"
    >
      <template #extra-button>
        <button class="tw-btn-danger" @click="() => confirmBatchDelete('delete-all')">
          删除全部
        </button>
      </template>
    </ConfirmDialog>
    <!-- Skeleton Loading -->
    <div
      v-if="resourceStore.loading"
      class="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-6"
    >
      <div
        v-for="i in 6"
        :key="i"
        class="skeleton-card rounded-2xl overflow-hidden"
        style="height: 380px"
      />
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else-if="filteredResources.length === 0"
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
        v-for="resource in filteredResources"
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

    <!-- Floating Refresh Button -->
    <button
      class="tw-fab-primary"
      :disabled="refreshing"
      :title="refreshing ? '刷新中...' : '刷新资源列表'"
      @click="handleManualRefresh"
    >
      <svg
        v-if="refreshing"
        class="w-5 h-5 animate-spin"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <circle cx="12" cy="12" r="10" stroke-width="2" />
        <path stroke-linecap="round" d="M12 6v6l3 3" />
      </svg>
      <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
    </button>
  </div>
</template>

<style scoped>
/* 自定义动画 */
@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

@keyframes shimmer {
  from {
    background-position: -200% 0;
  }
  to {
    background-position: 200% 0;
  }
}

.skeleton-card {
  background: linear-gradient(
    90deg,
    var(--bg-secondary) 25%,
    var(--bg-overlay) 50%,
    var(--bg-secondary) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite linear;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

/* select样式 */
select option {
  background: var(--bg-primary);
  color: var(--text-primary);
}

/* 响应式 */
@media (max-width: 768px) {
  .floating-refresh-btn {
    bottom: 1.5rem;
    right: 1.5rem;
    width: 50px;
    height: 50px;
    font-size: 1rem;
  }
}
</style>
