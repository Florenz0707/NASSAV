<script setup>
import { onMounted, ref, computed } from 'vue'
import { useResourceStore } from '../stores/resource'
import { useToastStore } from '../stores/toast'
import ResourceCard from '../components/ResourceCard.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'
import { downloadApi, resourceApi } from "../api/index.js";

const resourceStore = useResourceStore()
const toastStore = useToastStore()

const searchQuery = ref('')
const filterStatus = ref('all')
const sortBy = ref('metadata_create_time')
const sortOrder = ref('desc')
const page = ref(1)
const pageSize = ref(18)
// 使用 store 中的 pagination（模板中自动解包）
const refreshing = ref(false)

onMounted(async () => {
	await fetchResourceList()
})

async function fetchResourceList() {
	console.debug('[view] fetchResourceList called', { sort_by: sortBy.value, order: sortOrder.value, page: page.value, page_size: pageSize.value })
	await resourceStore.fetchResources({
		sort_by: sortBy.value,
		order: sortOrder.value,
		page: page.value,
		page_size: pageSize.value
	})
}

const filteredResources = computed(() => {
	let result = [...resourceStore.resources]

	// 搜索过滤
	if (searchQuery.value) {
		const query = searchQuery.value.toLowerCase()
		result = result.filter(r =>
			r.avid.toLowerCase().includes(query) ||
			r.title.toLowerCase().includes(query) ||
			r.source.toLowerCase().includes(query)
		)
	}

	// 状态过滤
	if (filterStatus.value === 'downloaded') {
		result = result.filter(r => r.has_video)
	} else if (filterStatus.value === 'pending') {
		result = result.filter(r => !r.has_video)
	}

	// 按最新下载排序时，只显示已下载的资源
	if (sortBy.value === 'latest_downloaded') {
		result = result.filter(r => r.has_video && r.video_create_time)
	}

	// 排序
	if (sortBy.value === 'date') {
		result.sort((a, b) => new Date(b.release_date) - new Date(a.release_date))
	} else if (sortBy.value === 'avid') {
		result.sort((a, b) => a.avid.localeCompare(b.avid))
	} else if (sortBy.value === 'source') {
		result.sort((a, b) => a.source.localeCompare(b.source))
	} else if (sortBy.value === 'latest_fetched') {
		result.sort((a, b) => (b.metadata_create_time || 0) - (a.metadata_create_time || 0))
	} else if (sortBy.value === 'latest_downloaded') {
		result.sort((a, b) => (b.video_create_time || 0) - (a.video_create_time || 0))
	}

	return result
})

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
	// 完全删除资源
	try {
		await resourceApi.delete(avid)
		await handleManualRefresh()
		toastStore.success(`${avid} 已被完全删除`)
	} catch (err) {
		toastStore.error(err.message || "删除失败")
	}
}

async function handleDeleteFile(avid) {
	// 删除资源视频
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
		await fetchResourceList()
		toastStore.success('资源列表已刷新')
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
	page.value = newPage
	fetchResourceList()
}

function onPageSizeChange() {
	page.value = 1
	fetchResourceList()
}

import { computed as vueComputed } from 'vue'

const visiblePages = vueComputed(() => {
	const total = resourceStore.pagination && resourceStore.pagination.pages ? resourceStore.pagination.pages : 1
	const cur = page.value || 1
	const maxButtons = 9
	let start = Math.max(1, cur - Math.floor(maxButtons / 2))
	let end = Math.min(total, start + maxButtons - 1)
	start = Math.max(1, end - maxButtons + 1)
	const res = []
	for (let i = start; i <= end; i++) res.push(i)
	return res
})

</script>

<template>
	<div class="animate-[fadeIn_0.5s_ease]">
		<!-- Page Header -->
		<div class="mb-8">
			<h1 class="text-[2rem] font-bold text-[#f4f4f5] mb-2">资源库</h1>
			<p class="text-[#71717a] text-base">管理您的所有视频资源</p>
		</div>

		<!-- Controls -->
		<div class="flex gap-4 mb-6 flex-wrap">
			<!-- Search Box -->
			<div class="flex-1 min-w-[250px] relative">
				<span class="absolute left-4 top-1/2 -translate-y-1/2 text-[#71717a] text-[1.1rem]">⌕</span>
				<input v-model="searchQuery" type="text" placeholder="搜索 AVID、标题、来源..."
					class="w-full py-3.5 px-4 pl-11 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-[0.95rem] transition-all duration-200 focus:outline-none focus:border-[#ff6b6b] focus:shadow-[0_0_0_3px_rgba(255,107,107,0.1)] placeholder:text-[#71717a]" />
			</div>

			<!-- Filters -->
			<div class="flex gap-3">
				<select v-model="filterStatus"
					class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b]">
					<option value="all">全部状态</option>
					<option value="downloaded">已下载</option>
					<option value="pending">未下载</option>
				</select>

				<select v-model="sortBy"
					class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b]"
					@change="onSortChange">
					<option value="avid">按编号</option>
					<option value="metadata_create_time">按元数据获取时间</option>
					<option value="video_create_time">按视频下载时间</option>
					<option value="source">按来源</option>
				</select>
				<select v-model="sortOrder"
					class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b] ml-2"
					@change="onSortChange">
					<option value="desc">降序</option>
					<option value="asc">升序</option>
				</select>
			</div>
		</div>

		<!-- Results Info -->
		<div v-if="!resourceStore.loading" class="mb-6 text-[#71717a] text-sm">
			<span>共 {{ resourceStore.pagination.total }} 个资源，页码 {{ resourceStore.pagination.page }}/{{
				resourceStore.pagination.pages }}</span>
		</div>

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
			<ResourceCard v-for="resource in resourceStore.resources" :key="resource.avid" :resource="resource"
				@download="handleDownload" @refresh="handleRefresh" @delete="handleDeleteResource"
				@deleteFile="handleDeleteFile" />
		</div>
		<div v-if="resourceStore.pagination.pages > 1" class="mt-8 flex flex-col items-center gap-4">
			<div class="flex flex-wrap gap-2 justify-center">
				<button :disabled="page === 1" @click="changePage(page - 1)"
					class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white font-medium shadow-md disabled:opacity-50 disabled:translate-y-0 transition-transform hover:-translate-y-1">上一页</button>
				<button v-for="p in visiblePages" :key="p" @click="changePage(p)"
					:class="['px-3 py-1 rounded-md min-w-[36px] text-sm', p === page ? 'bg-[#ff6b6b] text-white font-semibold' : 'bg-[rgba(255,255,255,0.03)] text-[#f4f4f5] hover:bg-white/5']">{{
						p }}</button>
				<button :disabled="page === resourceStore.pagination.pages" @click="changePage(page + 1)"
					class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white font-medium shadow-md disabled:opacity-50 disabled:translate-y-0 transition-transform hover:-translate-y-1">下一页</button>
			</div>

			<div class="flex items-center gap-3 justify-center">
				<label class="text-sm text-[#bcbcbc]">每页显示</label>
				<select v-model="pageSize" @change="onPageSizeChange"
					class="px-3 py-1 rounded-md bg-[#1b1b26] text-[#f4f4f5] border border-white/[0.06] focus:outline-none focus:ring-2 focus:ring-[#ff6b6b]/40">
					<option v-for="size in [12, 18, 24, 30]" :key="size" :value="size">{{ size }}</option>
				</select>
			</div>
		</div>

		<!-- Floating Refresh Button -->
		<button
			class="fixed bottom-8 right-8 w-[60px] h-[60px] rounded-full bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] border-none shadow-[0_4px_20px_rgba(255,107,107,0.3)] cursor-pointer transition-all duration-300 z-[1000] flex items-center justify-center text-white text-xl hover:-translate-y-1 hover:shadow-[0_6px_25px_rgba(255,107,107,0.4)] disabled:opacity-70 disabled:cursor-not-allowed disabled:hover:translate-y-0"
			:disabled="refreshing" @click="handleManualRefresh" :title="refreshing ? '刷新中...' : '刷新资源列表'">
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
