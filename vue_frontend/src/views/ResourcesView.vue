<script setup>
import {onMounted, ref, computed} from 'vue'
import {useResourceStore} from '../stores/resource'
import {useToastStore} from '../stores/toast'
import ResourceCard from '../components/ResourceCard.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'
import {downloadApi, resourceApi} from "../api/index.js";

const resourceStore = useResourceStore()
const toastStore = useToastStore()

const searchQuery = ref('')
const filterStatus = ref('all')
const sortBy = ref('latest_fetched')
const refreshing = ref(false)

onMounted(async () => {
	await resourceStore.fetchResources()
})

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
		await resourceStore.fetchResources()
		toastStore.success('资源列表已刷新')
	} catch (err) {
		toastStore.error(err.message || '刷新失败')
	} finally {
		refreshing.value = false
	}
}
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
				<input
					v-model="searchQuery"
					type="text"
					placeholder="搜索 AVID、标题、来源..."
					class="w-full py-3.5 px-4 pl-11 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-[0.95rem] transition-all duration-200 focus:outline-none focus:border-[#ff6b6b] focus:shadow-[0_0_0_3px_rgba(255,107,107,0.1)] placeholder:text-[#71717a]"
				/>
			</div>

			<!-- Filters -->
			<div class="flex gap-3">
				<select
					v-model="filterStatus"
					class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b]"
				>
					<option value="all">全部状态</option>
					<option value="downloaded">已下载</option>
					<option value="pending">未下载</option>
				</select>

				<select
					v-model="sortBy"
					class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b]"
				>
					<option value="date">按发行日期</option>
					<option value="latest_fetched">按最新获取</option>
					<option value="latest_downloaded">按最新下载</option>
					<option value="avid">按编号</option>
					<option value="source">按来源</option>
				</select>
			</div>
		</div>

		<!-- Results Info -->
		<div v-if="!resourceStore.loading" class="mb-6 text-[#71717a] text-sm">
			<span>共 {{ filteredResources.length }} 个资源</span>
		</div>

		<!-- Loading State -->
		<LoadingSpinner v-if="resourceStore.loading" size="large" text="加载资源中..."/>

		<!-- Empty State -->
		<EmptyState
			v-else-if="filteredResources.length === 0"
			icon="◇"
			title="暂无资源"
			:description="searchQuery ? '没有找到匹配的资源' : '点击右上角添加您的第一个资源'"
		>
			<template #action>
				<RouterLink
					to="/add"
					class="inline-flex items-center gap-2 px-6 py-3 border-none rounded-[10px] text-[0.95rem] font-medium no-underline cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white hover:-translate-y-0.5"
				>
					添加资源
				</RouterLink>
			</template>
		</EmptyState>

		<!-- Resources Grid -->
		<div v-else class="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-6">
			<ResourceCard
				v-for="resource in filteredResources"
				:key="resource.avid"
				:resource="resource"
				@download="handleDownload"
				@refresh="handleRefresh"
				@delete="handleDeleteResource"
				@deleteFile="handleDeleteFile"
			/>
		</div>

		<!-- Floating Refresh Button -->
		<button
			class="fixed bottom-8 right-8 w-[60px] h-[60px] rounded-full bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] border-none shadow-[0_4px_20px_rgba(255,107,107,0.3)] cursor-pointer transition-all duration-300 z-[1000] flex items-center justify-center text-white text-xl hover:-translate-y-1 hover:shadow-[0_6px_25px_rgba(255,107,107,0.4)] disabled:opacity-70 disabled:cursor-not-allowed disabled:hover:translate-y-0"
			:disabled="refreshing"
			@click="handleManualRefresh"
			:title="refreshing ? '刷新中...' : '刷新资源列表'"
		>
			<span
				class="block transition-transform duration-300"
				:class="{ 'animate-spin': refreshing }"
			>
				{{ refreshing ? '◷' : '↻' }}
			</span>
		</button>
	</div>
</template>

<style scoped>
/* 自定义动画 */
@keyframes fadeIn {
	from { opacity: 0; }
	to { opacity: 1; }
}

@keyframes spin {
	from { transform: rotate(0deg); }
	to { transform: rotate(360deg); }
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
