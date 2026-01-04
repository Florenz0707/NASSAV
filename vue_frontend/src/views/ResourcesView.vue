<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useResourceStore } from '../stores/resource'
import { useToastStore } from '../stores/toast'
import ResourcePagination from '../components/ResourcePagination.vue'
import ResourceCard from '../components/ResourceCard.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'
import BatchControls from '../components/BatchControls.vue'

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
		const arr = filteredResources.value.map(r => r.avid)
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

async function handleBatchDelete() {
	if (selectedAvids.value.size === 0) return
	if (!confirm(`确认删除 ${selectedAvids.value.size} 个资源？此操作不可恢复！`)) return
	batchLoading.value = true
	try {
		const avids = Array.from(selectedAvids.value)
		await resourceStore.batchDelete(avids)
		toastStore.success(`已删除 ${avids.length} 个资源`)
		selectedAvids.value = new Set()
		await fetchResourceList()
	} catch (err) {
		toastStore.error(err.message || '批量删除失败')
	} finally {
		batchLoading.value = false
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
watch([page, pageSize, searchQuery, filterStatus, sortBy, sortOrder], () => {
	const query = {
		page: page.value
	}
	if (pageSize.value !== 18) query.pageSize = pageSize.value
	if (searchQuery.value) query.search = searchQuery.value
	if (filterStatus.value !== 'all') query.status = filterStatus.value
	if (sortBy.value !== 'metadata_create_time') query.sortBy = sortBy.value
	if (sortOrder.value !== 'desc') query.order = sortOrder.value
	if (actorParam.value) query.actor = actorParam.value
	if (genreParam.value) query.genre = genreParam.value

	router.replace({ query })
}, { deep: true })

async function fetchResourceList() {
	console.debug('[view] fetchResourceList called', {
		sort_by: sortBy.value,
		order: sortOrder.value,
		page: page.value,
		page_size: pageSize.value,
		search: searchQuery.value,
		status: filterStatus.value
	})
	await resourceStore.fetchResources({
		sort_by: sortBy.value,
		order: sortOrder.value,
		page: page.value,
		page_size: pageSize.value,
		search: searchQuery.value,
		status: filterStatus.value,
		actor: actorParam.value || undefined,
		genre: genreParam.value || undefined
	})
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
const filteredResources = computed(() => {
	const raw = resourceStore.resources && resourceStore.resources.value !== undefined ? resourceStore.resources.value : resourceStore.resources
	if (Array.isArray(raw)) return raw
	if (raw && Array.isArray(raw.results)) return raw.results
	if (raw && Array.isArray(raw.data)) return raw.data
	return []
})

// debounce search input to avoid frequent requests
let _searchTimer = null
watch(searchQuery, () => {
	if (_searchTimer) clearTimeout(_searchTimer)
	_searchTimer = setTimeout(() => {
		page.value = 1
		fetchResourceList()
	}, 300)
})

// trigger when filter status changes
watch(filterStatus, () => {
	page.value = 1
	fetchResourceList()
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
			<h1 class="text-[2rem] font-bold text-[#f4f4f5] mb-2">
				资源库
			</h1>
			<!-- Results Info -->
			<div v-if="!resourceStore.loading" class="mb-6 text-[#71717a] text-sm">
				<span>管理您的 {{ resourceStore.pagination.total }} 个资源</span>
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
			:total-count="filteredResources.length" @toggle-batch-mode="toggleBatchMode"
			@toggle-select-all="toggleSelectAll" @batch-refresh="handleBatchRefresh"
			@batch-download="handleBatchDownload" @batch-delete="handleBatchDelete" />

		<!-- Loading State -->
		<LoadingSpinner v-if="resourceStore.loading" size="large" text="加载资源中..." />

		<!-- Empty State -->
		<EmptyState v-else-if="filteredResources.length === 0" icon="◇" title="暂无资源"
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
			<ResourceCard v-for="resource in filteredResources" :key="resource.avid" :resource="resource"
				:selectable="batchMode" :selected="selectedAvids.has(resource.avid)" :coverSize="'medium'"
				@toggle-select="toggleSelect" @download="handleDownload" @refresh="handleRefresh"
				@delete="handleDeleteResource" @deleteFile="handleDeleteFile" />
		</div>
		<ResourcePagination :page="page" :pages="resourceStore.pagination.pages" :pageSize="pageSize"
			:total="resourceStore.pagination.total" @change-page="changePage" @change-page-size="onPageSizeChange" />

		<!-- Floating Refresh Button -->
		<button
			class="fixed bottom-8 right-8 w-[60px] h-[60px] rounded-full bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] border-none shadow-[0_4px_20px_rgba(255,107,107,0.3)] cursor-pointer transition-all duration-300 z-[1000] flex items-center justify-center text-white text-xl hover:-translate-y-1 hover:shadow-[0_6px_25px_rgba(255,107,107,0.4)] disabled:opacity-70 disabled:cursor-not-allowed disabled:hover:translate-y-0"
			:disabled="refreshing" :title="refreshing ? '刷新中...' : '刷新资源列表'" @click="handleManualRefresh">
			<span class="block transition-transform duration-300" :class="{ 'animate-spin': refreshing }">
				{{ refreshing ? '◷' : '↻' }}
			</span>
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
	background: #0d0d14;
	color: #f4f4f5;
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
