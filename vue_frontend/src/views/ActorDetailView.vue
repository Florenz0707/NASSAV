<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useToastStore } from '../stores/toast'
import { useRoute, useRouter } from 'vue-router'
import { useResourceStore } from '../stores/resource'
import { actorApi, resourceApi, downloadApi } from '../api'
import ResourceCard from '../components/ResourceCard.vue'
import ResourcePagination from '../components/ResourcePagination.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'
import BatchControls from '../components/BatchControls.vue'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()

const actorId = ref(route.params.actorId || '')
// 从 URL query 初始化状态
const page = ref(parseInt(route.query.page) || 1)
const pageSize = ref(parseInt(route.query.pageSize) || 18)
const sortBy = ref(route.query.sortBy || 'metadata_create_time')
const sortOrder = ref(route.query.order || 'desc')
const searchQuery = ref(route.query.search || '')
const filterStatus = ref(route.query.status || 'all')

const loadingActor = ref(false)
const actor = ref({ id: actorId.value, name: '', resource_count: 0, avatar_url: null })
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
		const arr = displayedResources.value.map(r => r.avid)
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

async function handleBatchDelete() {
	if (selectedAvids.value.size === 0) return
	if (!confirm(`确认删除 ${selectedAvids.value.size} 个资源？此操作不可恢复！`)) return
	batchLoading.value = true
	try {
		const avids = Array.from(selectedAvids.value)
		await resourceStore.batchDelete(avids)
		selectedAvids.value = new Set()
		await fetchResources()
		toastStore.success(`已删除 ${avids.length} 个资源`)
	} catch (err) {
		toastStore.error(err.message || '批量删除失败')
	} finally {
		batchLoading.value = false
	}
}

async function loadActorInfo(id) {
	loadingActor.value = true
	try {
		const response = await actorApi.getList({ id: String(id), page: 1, page_size: 1 })
		if (response && response.code === 200 && Array.isArray(response.data) && response.data.length > 0) {
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
	await resourceStore.fetchResources({
		page: pg,
		page_size: pageSize.value,
		actor: actorId.value,
		search: searchQuery.value,
		sort_by: sortBy.value,
		order: sortOrder.value,
		status: filterStatus.value
	})
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
		toastStore.error(err.message || "删除失败")
	}
}

async function handleDeleteFile(avid) {
	try {
		await downloadApi.deleteFile(avid)
		await handleManualRefresh()
		toastStore.success(`${avid} 已删除视频`)
	} catch (err) {
		toastStore.error(err.message || "删除失败")
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
})

// 状态变化时同步到 URL
watch([page, pageSize, searchQuery, sortBy, sortOrder], () => {
	const query = {
		page: page.value
	}
	if (pageSize.value !== 18) query.pageSize = pageSize.value
	if (searchQuery.value) query.search = searchQuery.value
	if (sortBy.value !== 'metadata_create_time') query.sortBy = sortBy.value
	if (sortOrder.value !== 'desc') query.order = sortOrder.value
	if (route.query.from) query.from = route.query.from

	router.replace({ query })
}, { deep: true })

watch(() => route.params.actorId, async (v) => {
	actorId.value = v
	await loadActorInfo(actorId.value)
	page.value = 1
	await fetchResources(1)
})

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
	const raw = resourceStore.resources && resourceStore.resources.value !== undefined ? resourceStore.resources.value : resourceStore.resources
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
	const rc = actor.value && typeof actor.value.resource_count !== 'undefined' ? actor.value.resource_count : null
	if (rc !== null && rc !== undefined) return rc
	return resourceStore.pagination && resourceStore.pagination.total ? resourceStore.pagination.total : 0
})
</script>

<template>
	<div class="px-6 pt-4 pb-6">
		<div class="mb-6 flex items-center gap-6">
			<div class="w-20 h-20 rounded-full bg-[#0b0b10] flex items-center justify-center text-4xl text-white overflow-hidden border-2 border-white/10">
				<img v-if="actor.id && actor.avatar_filename" :src="actorApi.getAvatarUrl(actor.id)" :alt="actor.name" class="w-full h-full object-cover">
				<span v-else>{{ initialChar }}</span>
			</div>
			<div class="flex-1">
				<div class="text-xl font-semibold text-[#f4f4f5]">
					{{ actor.name }}
				</div>
				<div class="text-sm text-[#71717a]">
					共有 {{ displayedCount }} 部作品
				</div>
			</div>
		</div>

		<!-- Controls -->
		<div class="flex gap-4 mb-6 flex-wrap">
			<!-- Search Box -->
			<div class="flex-1 min-w-[250px] relative">
				<span class="absolute left-4 top-1/2 -translate-y-1/2 text-[#71717a] text-[1.1rem]">⌕</span>
				<input v-model="searchQuery" type="text" placeholder="搜索 AVID、标题、来源..."
					class="w-full py-3.5 px-4 pl-11 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-[0.95rem] transition-all duration-200 focus:outline-none focus:border-[#ff6b6b] focus:shadow-[0_0_0_3px_rgba(255,107,107,0.1)] placeholder:text-[#71717a]" >
			</div>

			<!-- Filters -->
			<div class="flex gap-3">
				<select v-model="filterStatus"
					class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b]">
					<option value="all">
						全部状态
					</option>
					<option value="downloaded">
						已下载
					</option>
					<option value="pending">
						未下载
					</option>
				</select>

				<select v-model="sortBy"
					class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b]"
					@change="onSortChange">
					<option value="avid">
						按编号
					</option>
					<option value="metadata_create_time">
						按元数据获取时间
					</option>
					<option value="video_create_time">
						按视频下载时间
					</option>
					<option value="source">
						按来源
					</option>
				</select>
				<select v-model="sortOrder"
					class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b] ml-2"
					@change="onSortChange">
					<option value="desc">
						降序
					</option>
					<option value="asc">
						升序
					</option>
				</select>
			</div>
		</div>

		<!-- Batch controls -->
		<BatchControls :batch-mode="batchMode" :batch-loading="batchLoading" :selected-count="selectedCount"
			:total-count="displayedResources.length" @toggle-batch-mode="toggleBatchMode"
			@toggle-select-all="toggleSelectAll" @batch-refresh="handleBatchRefresh"
			@batch-download="handleBatchDownload" @batch-delete="handleBatchDelete" />

		<!-- Loading State -->
		<LoadingSpinner v-if="resourceStore.loading" size="large" text="加载资源中..." />

		<!-- Empty State -->
		<EmptyState v-else-if="displayedResources.length === 0" icon="◇" title="暂无资源"
			:description="searchQuery ? '没有找到匹配的资源' : '点击右上角添加您的第一个资源'">
			<template #action>
				<RouterLink to="/add"
					class="inline-flex items-center gap-2 px-6 py-3 border-none rounded-[10px] text-[0.95rem] font-medium no-underline cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white hover:-translate-y-0.5">
					添加资源
				</RouterLink>
			</template>
		</EmptyState>

		<!-- Resources Grid -->
		<div v-else class="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-6">
			<ResourceCard v-for="resource in displayedResources" :key="resource.avid" :resource="resource"
				:selectable="batchMode" :selected="selectedAvids.has(resource.avid)" :coverSize="'medium'"
				@toggle-select="toggleSelect" @download="handleDownload" @refresh="handleRefresh"
				@delete="handleDeleteResource" @deleteFile="handleDeleteFile" />
		</div>
		<ResourcePagination :page="page" :pages="resourceStore.pagination.pages" :pageSize="pageSize"
			:total="resourceStore.pagination.total" @change-page="changePage" @change-page-size="onPageSizeChange" />
	</div>
</template>
