<script setup>
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useResourceStore } from '../../resources/stores/resource.js'
import { useToastStore } from '../../../shared/stores/toast.js'
import { useResourceAdds } from '../../resources/composables/useResourceAdds.js'
import { useExternalSearchTask } from '../composables/useExternalSearchTask.js'
import {
  useExternalSearchSources,
  createSearchRequestGuard,
} from '../composables/useExternalSearchSources.js'
import AppIcon from '../../../shared/ui/AppIcon.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import ExternalSearchCard from './ExternalSearchCard.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
const props = defineProps({
  entityType: { type: String, required: true },
  entityId: { type: [String, Number], required: true },
})
const emit = defineEmits(['detail', 'resource-saved'])
const entityId = computed(() => props.entityId)
const entityLabel = props.entityType === 'actor' ? '演员' : '类别'
const router = useRouter(),
  resourceStore = useResourceStore(),
  toastStore = useToastStore()
// External Search states
const showSearchSettings = ref(false)
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

function restartExternalSearch() {
  clearExternalQueryCache()
  startExternalSearch(1, true)
}

const initialArea = ref(null)
const remainingHeight = ref(0)
let areaObserver
function updateInitialHeight() {
  const element = initialArea.value
  if (!element?.getClientRects().length) return
  let bottomSpace = 0
  for (
    let parent = element.parentElement;
    parent && parent !== document.body;
    parent = parent.parentElement
  ) {
    bottomSpace += parseFloat(getComputedStyle(parent).paddingBottom) || 0
  }
  remainingHeight.value = Math.max(
    0,
    window.innerHeight - element.getBoundingClientRect().top - window.scrollY - bottomSpace
  )
}
watch(initialArea, (element, previous) => {
  if (previous) areaObserver?.unobserve(previous)
  if (element) areaObserver?.observe(element)
  nextTick(updateInitialHeight)
})
onMounted(() => {
  areaObserver = new ResizeObserver(updateInitialHeight)
  if (initialArea.value) areaObserver.observe(initialArea.value)
  window.addEventListener('resize', updateInitialHeight)
})
onBeforeUnmount(() => {
  areaObserver?.disconnect()
  window.removeEventListener('resize', updateInitialHeight)
})

const addedExternalAvids = ref(new Set())
const { adding: addingExternalAvids, add: handleAddExternal } = useResourceAdds({
  added: addedExternalAvids,
  jobs: () => resourceStore.visibleScrapeJobs,
  submit: (avid, item) => resourceStore.addResource(avid, item.source || externalSource.value),
  onAdded: (item) => {
    syncExternalResourceStatus(item.avid, true)
  },
  onExisting: (item) => toastStore.info(`${item.avid} 已经在资源库中`),
  onError: (error) => toastStore.error(error.message || '添加失败'),
})
const handledScrapeJobs = new Set()
watch(
  () => resourceStore.visibleScrapeJobs,
  (jobs) => {
    for (const job of jobs) {
      const id = job.job_id || job.task_id
      if (
        !(job.resource_saved || job.resource_avid || job.state === 'succeeded') ||
        handledScrapeJobs.has(id)
      )
        continue
      handledScrapeJobs.add(id)
      emit('resource-saved')
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
  return Boolean(
    item?.is_in_library || item?.in_library || addedExternalAvids.value.has(item?.avid)
  )
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
    emit('detail', response.data.detail)
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
    if (result === undefined) return
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
  const added = new Set(addedExternalAvids.value)
  if (inLibrary) added.add(avid)
  else added.delete(avid)
  addedExternalAvids.value = added
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

function handleOpenExternal(item) {
  if (item.detail_url) {
    window.open(item.detail_url, '_blank')
  }
}

function handleViewExternal(item) {
  router.push({ path: `/resource/${item.avid}` })
}

onBeforeUnmount(() => {
  pageReadGuard.invalidate()
  cancelExternalSearch()
  requestGuard.invalidate()
})
defineExpose({
  initialize: loadSearchSources,
  restoreCache: restoreExternalCache,
  reset: resetExternalSearchState,
  syncLibraryStatus: syncExternalResourceStatus,
})
</script>
<template>
  <div>
    <SettingsModal :show="showSearchSettings" title="搜索设置" @close="showSearchSettings = false">
      <label for="entity-search-source" class="block text-secondary mb-3">搜索源</label>
      <CustomSelect
        id="entity-search-source"
        :model-value="externalSource"
        :options="sourceOptions"
        aria-label="搜索源"
        :disabled="loadingExternal"
        full-width
        @update:model-value="onExternalSourceChange"
      />
      <p class="text-muted text-sm mt-4">选择来源后，点击开始搜索。更改来源不会自动搜索。</p>
      <template #footer><AppButton @click="showSearchSettings = false">完成</AppButton></template>
    </SettingsModal>
    <div>
      <div
        v-if="!externalSearched && !loadingExternal"
        ref="initialArea"
        class="flex flex-col justify-center items-center gap-3"
        :style="{ minHeight: `${remainingHeight}px` }"
      >
        <div class="flex justify-center items-center gap-3">
          <AppButton :disabled="!sourcesReady || !externalSource" @click="startExternalSearch(1)"
            >开始搜索</AppButton
          >
          <AppButton
            variant="neutral"
            size="sm"
            aria-label="搜索设置"
            @click="showSearchSettings = true"
            ><AppIcon name="settings"
          /></AppButton>
          <AppButton v-if="sourcesError" variant="neutral" @click="loadSearchSources"
            >重新加载搜索源</AppButton
          >
        </div>
        <p v-if="sourcesError" class="text-muted" role="alert">{{ sourcesError }}</p>
        <p v-if="externalSource === 'missav'" class="text-muted text-sm text-center">
          缺少演员或类别映射时按名称关键词匹配；排序沿用源站，列表不提供播放量和收藏量数值。
        </p>
      </div>
      <div v-if="loadingExternal" class="flex justify-center items-center gap-3 mb-6">
        <AppButton variant="neutral" :disabled="cancellingExternal" @click="stopExternalSearch">{{
          cancellingExternal ? '正在取消…' : '取消搜索'
        }}</AppButton>
      </div>
      <p
        v-if="sourcesError && (externalSearched || loadingExternal)"
        class="text-muted mb-4"
        role="alert"
      >
        {{ sourcesError }}
      </p>
      <p
        v-if="externalSource === 'missav' && (externalSearched || loadingExternal)"
        class="text-muted text-sm mb-4"
      >
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
        已保留成功获取的结果；列表不完整，可重新搜索。
      </p>
      <RequestError
        v-if="externalError && !loadingExternal"
        :message="`搜索失败：${externalError}`"
        compact
        @retry="restartExternalSearch"
      />
      <p v-if="externalCancelled" class="text-muted mb-4 text-center" role="status">
        搜索已取消，已获取的结果仍可查看。
      </p>
      <PageLoad v-if="loadingExternal && externalResources.length === 0" text="正在搜索外部资源" />

      <template v-else-if="externalSearched">
        <div
          class="mb-4 text-sm text-[var(--text-muted)] flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        >
          <span>已获取 {{ externalPagination?.total || 0 }} 项结果</span>
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
        <div v-if="!loadingExternal" class="flex justify-center items-center gap-3 mt-6">
          <AppButton :disabled="!sourcesReady || !externalSource" @click="restartExternalSearch"
            >重新搜索</AppButton
          >
          <AppButton
            variant="neutral"
            size="sm"
            aria-label="搜索设置"
            @click="showSearchSettings = true"
            ><AppIcon name="settings"
          /></AppButton>
        </div>
      </template>
    </div>
  </div>
</template>
