<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useToastStore } from '../stores/toast'
import { useRoute, useRouter } from 'vue-router'
import { useResourceStore } from '../stores/resource'
import { useSettingsStore } from '../stores/settings'
import { actorApi, resourceApi, downloadApi } from '../api'
import ResourceCard from '../components/ResourceCard.vue'

import RecommendationCard from '../components/RecommendationCard.vue'
import ResourcePagination from '../components/ResourcePagination.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'
import BatchControls from '../components/BatchControls.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ResourceSearchBar from '../components/ResourceSearchBar.vue'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
const settingsStore = useSettingsStore()

const actorId = ref(route.params.actorId || '')
// 从 URL query 初始化状态
const currentTab = ref(route.query.tab || 'local')
const page = ref(parseInt(route.query.page) || 1)
const pageSize = ref(parseInt(route.query.pageSize) || 18)
const sortBy = ref(route.query.sortBy || 'metadata_create_time')
const sortOrder = ref(route.query.order || 'desc')
const searchQuery = ref(route.query.search || '')
const filterStatus = ref(route.query.status || 'all')

const loadingActor = ref(false)
const actor = ref({ id: actorId.value, name: '', resource_count: 0, avatar_url: null })
const toastStore = useToastStore()

// External Search states
const externalSearched = ref(false)
const loadingExternal = ref(false)
const externalResources = ref([])
const externalMeta = ref({})
const externalPage = ref(1)

const addingExternalAvids = ref(new Set())

function saveExternalCache() {
  const key = `external_actor_${actorId.value}`
  sessionStorage.setItem(
    key,
    JSON.stringify({
      results: externalResources.value,
      meta: externalMeta.value,
      page: externalPage.value,
      searched: externalSearched.value,
      timestamp: Date.now(),
    })
  )
}

function restoreExternalCache() {
  const key = `external_actor_${actorId.value}`
  try {
    const cached = JSON.parse(sessionStorage.getItem(key))
    if (cached && Date.now() - cached.timestamp < 1000 * 60 * 60) {
      externalResources.value = cached.results
      externalMeta.value = cached.meta
      externalPage.value = cached.page
      externalSearched.value = cached.searched
      return true
    }
  } catch (e) {}
  return false
}

async function startExternalSearch(p = 1) {
  loadingExternal.value = true
  externalSearched.value = true
  externalPage.value = p
  try {
    const params = {
      source: 'jable',
      page: p,
      page_size: 20,
      ordering:
        sortBy.value === 'metadata_create_time'
          ? '-views'
          : sortOrder.value === 'asc'
            ? sortBy.value
            : '-' + sortBy.value,
    }
    const response = await actorApi.getDetail(actorId.value, params)
    if (response && response.data) {
      const formattedResults = (response.data.external_results || []).map((r) => ({
        ...r,
        title: r.source_title || r.original_title,
        cover_url: r.thumbnail_url,
        raw_metrics: r.metrics,
      }))
      if (p === 1) {
        externalResources.value = formattedResults
      } else {
        externalResources.value = externalResources.value.concat(formattedResults)
      }
      externalMeta.value = response.data.external_meta || {}
      if (response.data.detail) {
        actor.value = response.data.detail
      }
      saveExternalCache()
    }
  } catch (err) {
    toastStore.error(err.message || '获取外部搜索失败')
    if (p === 1) externalResources.value = []
  } finally {
    loadingExternal.value = false
  }
}

async function handleAddExternal(item) {
  if (addingExternalAvids.value.has(item.avid)) return
  addingExternalAvids.value.add(item.avid)
  try {
    await resourceStore.addResource(item.avid, 'any')
    toastStore.success(`${item.avid} 已加入资源库`)
    item.metadata_create_time = Date.now() / 1000
    saveExternalCache()
  } catch (err) {
    if (err.httpStatus === 409 || err.code === 409 || err?.response?.status === 409) {
      toastStore.info(`${item.avid} 已经在资源库中`)
      item.metadata_create_time = Date.now() / 1000
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

async function loadActorInfo(id) {
  loadingActor.value = true
  try {
    const response = await actorApi.getList({ id: String(id), page: 1, page_size: 1 })
    if (
      response &&
      response.code === 200 &&
      Array.isArray(response.data) &&
      response.data.length > 0
    ) {
      actor.value = response.data[0]
    } else {
      // fallback: set id and empty name
      actor.value = { id, name: String(id), resource_count: 0, avatar_url: null }
    }
  } catch (_error) {
    actor.value = { id, name: String(id), resource_count: 0, avatar_url: null }
  } finally {
    loadingActor.value = false
  }
}

async function fetchResources(p = 1) {
  const pg = Number(p || 1)
  page.value = pg

  const params = {
    page: pg,
    page_size: pageSize.value,
    actor: actorId.value,
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
  actorId.value = route.params.actorId
  await loadActorInfo(actorId.value)
  await fetchResources(1)
  restoreExternalCache()
})

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
  () => route.params.actorId,
  async (v) => {
    actorId.value = v
    await loadActorInfo(actorId.value)
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

const initialChar = computed(() => {
  if (!actor.value || !actor.value.name) return ''
  return actor.value.name.trim().slice(0, 1)
})

const displayedCount = computed(() => {
  const rc =
    actor.value && typeof actor.value.resource_count !== 'undefined'
      ? actor.value.resource_count
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
        class="w-20 h-20 rounded-full flex items-center justify-center text-4xl overflow-hidden border-2"
        style="
          color: var(--detail-badge-text);
          background: var(--detail-badge-bg);
          border-color: var(--detail-badge-border);
          box-shadow: var(--detail-badge-shadow);
        "
      >
        <img
          v-if="settingsStore.showActorAvatar && actor.id && actor.avatar_filename"
          :src="actorApi.getAvatarUrl(actor.id)"
          :alt="actor.name"
          class="w-full h-full object-cover"
        />
        <span v-else>{{ initialChar }}</span>
      </div>
      <div class="flex-1">
        <div class="text-xl font-semibold text-[var(--text-primary)]">
          {{ actor.name }}
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
      <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-6">
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
      <div
        v-if="!externalSearched && !loadingExternal"
        class="flex flex-col items-center justify-center py-20 text-center"
      >
        <div class="text-4xl mb-4 opacity-50">🌐</div>
        <h3 class="text-xl font-medium text-[var(--text-primary)] mb-2">外部搜索</h3>
        <p class="text-[var(--text-muted)] mb-6 max-w-md">
          点击下方按钮，开始使用外部数据源 (当前仅支持 Jable)
          搜索与该演员相关的资源。搜索过程可能需要一些时间，请耐心等待。
        </p>
        <button class="tw-btn tw-btn-primary px-8 py-2 rounded-lg" @click="startExternalSearch(1)">
          开始搜索
        </button>
      </div>

      <LoadingSpinner
        v-else-if="loadingExternal && externalPage === 1"
        size="large"
        text="正在执行外部搜索，请耐心等待..."
        alt="Loading external search results"
        justify="center"
      />

      <template v-else>
        <div class="mb-4 text-sm text-[var(--text-muted)] flex justify-between">
          <span
            >来源: {{ externalMeta.supported_sources?.includes('jable') ? 'jable' : 'jable' }}</span
          >
          <span>排序: 按播放量降低</span>
        </div>

        <EmptyState
          v-if="externalResources.length === 0"
          icon="◇"
          title="外部搜索暂无结果"
          description="未能从外部源获取到关于该演员的更多资源"
        />

        <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-6 mb-6">
          <RecommendationCard
            v-for="resource in externalResources"
            :key="resource.avid"
            :item="resource"
            :added="!!resource.metadata_create_time"
            :adding="addingExternalAvids.has(resource.avid)"
            @add="handleAddExternal(resource)"
            @view="handleViewExternal(resource)"
            @open="handleOpenExternal(resource)"
          />
        </div>

        <div v-if="externalResources.length > 0" class="flex justify-center mt-6">
          <button
            class="tw-btn bg-[var(--bg-secondary)] border border-[var(--border-color)] hover:border-[var(--accent-primary)] text-[var(--text-primary)] px-8 py-2 rounded-lg"
            :disabled="loadingExternal"
            @click="startExternalSearch(externalPage + 1)"
          >
            {{ loadingExternal ? '加载中...' : '加载下一页' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
