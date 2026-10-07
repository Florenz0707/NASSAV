<script setup>
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useToastStore } from '../../../shared/stores/toast.js'
import { useRoute, useRouter } from 'vue-router'
import { useResourceStore } from '../../resources/stores/resource.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { actorApi, genreApi } from '../../../api/index.js'
import ResourceCard from '../../resources/components/ResourceCard.vue'
import ExternalSearchPanel from '../../external-search/components/ExternalSearchPanel.vue'

import ResourcePagination from '../../../shared/ui/ResourcePagination.vue'

import EmptyState from '../../../shared/ui/EmptyState.vue'
import BatchControls from '../../resources/components/BatchControls.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import ResourceSearchBar from '../../resources/components/ResourceSearchBar.vue'

const props = defineProps({
  entityType: {
    type: String,
    required: true,
    validator: (value) => ['actor', 'genre'].includes(value),
  },
})
const isActor = props.entityType === 'actor'
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
const entityError = ref('')
const entity = ref({ id: entityId.value, name: '', resource_count: 0, avatar_url: null })
const toastStore = useToastStore()

const externalPanel = ref(null)
function refreshAfterSave() {
  fetchResources(page.value)
  loadEntityInfo(entityId.value)
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
      succeeded.forEach((item) => externalPanel.value?.syncLibraryStatus(item.avid, false))
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
  entityError.value = ''
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
  } catch (error) {
    if (!infoGuard.current(request)) return
    entityError.value = error.message || '实体信息加载失败'
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

  try {
    await resourceStore.fetchResources(params)
  } catch {
    /* Store owns the error and retry state. */
  }
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

async function handleRefresh(avid, params) {
  try {
    await resourceStore.refreshResource(avid, params)
  } catch (err) {
    toastStore.error(err.message || '刷新失败')
  }
}

async function handleDeleteResource(avid) {
  try {
    await handleManualRefresh()
    // 同步到外部搜索列表
    externalPanel.value?.syncLibraryStatus(avid, false)
    loadEntityInfo(entityId.value)
  } catch (err) {
    toastStore.error(err.message || '删除失败')
  }
}

async function handleDeleteFile(_avid) {
  try {
    await handleManualRefresh()
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
  await externalPanel.value.initialize()
  if (!navigationGuard.current(navigation)) return
  entityId.value = route.params[routeParam]
  await loadEntityInfo(entityId.value)
  if (!navigationGuard.current(navigation)) return
  await fetchResources(page.value)
  if (navigationGuard.current(navigation)) externalPanel.value?.restoreCache()
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
    externalPanel.value?.reset()
    await loadEntityInfo(entityId.value)
    if (!navigationGuard.current(navigation)) return
    page.value = 1
    await fetchResources(1)
    if (navigationGuard.current(navigation)) externalPanel.value?.restoreCache()
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
    <RequestError
      v-if="entityError"
      :message="entityError"
      compact
      @retry="loadEntityInfo(entityId)"
    />
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
        <h1 class="font-semibold text-primary" :class="isActor ? 'text-xl' : 'text-2xl'">
          {{ entity.name }}
        </h1>
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
        :aria-pressed="currentTab === 'local'"
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
        :aria-pressed="currentTab === 'external'"
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
      <RequestError
        v-if="resourceStore.error && !resourceStore.loading"
        :message="resourceStore.error"
        :compact="displayedResources.length > 0"
        @retry="fetchResources(page)"
      />
      <PageLoad
        v-if="resourceStore.loading && !displayedResources.length"
        :count="6"
        text="正在加载资源"
      />
      <PageLoad v-else-if="resourceStore.loading" variant="spinner" text="正在更新资源" />

      <!-- Empty State -->
      <EmptyState
        v-if="!resourceStore.loading && !resourceStore.error && displayedResources.length === 0"
        icon="empty"
        title="暂无资源"
        :description="searchQuery ? '没有找到匹配的资源' : '点击右上角添加您的第一个资源'"
      >
        <template #action>
          <RouterLink to="/add" class="tw-btn-primary"> 添加资源 </RouterLink>
        </template>
      </EmptyState>

      <!-- Resources Grid -->
      <div
        v-if="displayedResources.length"
        class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6"
      >
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

    <ExternalSearchPanel
      ref="externalPanel"
      v-show="currentTab === 'external'"
      :entity-type="entityType"
      :entity-id="entityId"
      @detail="entity = $event"
      @resource-saved="refreshAfterSave"
    />
  </div>
</template>
