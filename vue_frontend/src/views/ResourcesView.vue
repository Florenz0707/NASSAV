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
	<div class="resources-view">
		<div class="page-header">
			<h1 class="page-title">资源库</h1>
			<p class="page-subtitle">管理您的所有视频资源</p>
		</div>

		<div class="controls">
			<div class="search-box">
				<span class="search-icon">⌕</span>
				<input
					v-model="searchQuery"
					type="text"
					placeholder="搜索 AVID、标题、来源..."
					class="search-input"
				/>
			</div>

			<div class="filters">
				<select v-model="filterStatus" class="filter-select">
					<option value="all">全部状态</option>
					<option value="downloaded">已下载</option>
					<option value="pending">未下载</option>
				</select>

				<select v-model="sortBy" class="filter-select">
					<option value="date">按发行日期</option>
					<option value="latest_fetched">按最新获取</option>
					<option value="latest_downloaded">按最新下载</option>
					<option value="avid">按编号</option>
					<option value="source">按来源</option>
				</select>
			</div>
		</div>

		<div class="results-info" v-if="!resourceStore.loading">
			<span>共 {{ filteredResources.length }} 个资源</span>
		</div>

		<LoadingSpinner v-if="resourceStore.loading" size="large" text="加载资源中..."/>

		<EmptyState
			v-else-if="filteredResources.length === 0"
			icon="◇"
			title="暂无资源"
			:description="searchQuery ? '没有找到匹配的资源' : '点击右上角添加您的第一个资源'"
		>
			<template #action>
				<RouterLink to="/add" class="btn btn-primary">
					添加资源
				</RouterLink>
			</template>
		</EmptyState>

		<div v-else class="resources-grid">
			<ResourceCard
				v-for="resource in filteredResources"
				:key="resource.avid"
				:resource="resource"
				@download="handleDownload"
				@refresh="handleRefresh"
				@deleteResource="handleDeleteResource"
				@deleteFile="handleDeleteFile"
			/>
		</div>

		<!-- 悬浮刷新按钮 -->
		<button
			class="floating-refresh-btn"
			:disabled="refreshing"
			@click="handleManualRefresh"
			:title="refreshing ? '刷新中...' : '刷新资源列表'"
		>
			<span class="refresh-icon" :class="{ spinning: refreshing }">
				{{ refreshing ? '◷' : '↻' }}
			</span>
		</button>
	</div>
</template>

<style scoped>
.resources-view {
	animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
	from {
		opacity: 0;
	}
	to {
		opacity: 1;
	}
}

.page-header {
	margin-bottom: 2rem;
}

.page-title {
	font-size: 2rem;
	font-weight: 700;
	color: var(--text-primary);
	margin-bottom: 0.5rem;
}

.page-subtitle {
	color: var(--text-muted);
	font-size: 1rem;
}

.controls {
	display: flex;
	gap: 1rem;
	margin-bottom: 1.5rem;
	flex-wrap: wrap;
}

.search-box {
	flex: 1;
	min-width: 250px;
	position: relative;
}

.search-icon {
	position: absolute;
	left: 1rem;
	top: 50%;
	transform: translateY(-50%);
	color: var(--text-muted);
	font-size: 1.1rem;
}

.search-input {
	width: 100%;
	padding: 0.875rem 1rem 0.875rem 2.75rem;
	background: var(--card-bg);
	border: 1px solid var(--border-color);
	border-radius: 12px;
	color: var(--text-primary);
	font-size: 0.95rem;
	transition: all 0.2s ease;
}

.search-input:focus {
	outline: none;
	border-color: var(--accent-primary);
	box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.1);
}

.search-input::placeholder {
	color: var(--text-muted);
}

.filters {
	display: flex;
	gap: 0.75rem;
}

.filter-select {
	padding: 0.875rem 1rem;
	background: var(--card-bg);
	border: 1px solid var(--border-color);
	border-radius: 12px;
	color: var(--text-primary);
	font-size: 0.9rem;
	cursor: pointer;
	transition: all 0.2s ease;
}

.filter-select:focus {
	outline: none;
	border-color: var(--accent-primary);
}

.filter-select option {
	background: var(--bg-primary);
	color: var(--text-primary);
}

.results-info {
	margin-bottom: 1.5rem;
	color: var(--text-muted);
	font-size: 0.9rem;
}

.resources-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
	gap: 1.5rem;
}

.btn {
	display: inline-flex;
	align-items: center;
	gap: 0.5rem;
	padding: 0.75rem 1.5rem;
	border: none;
	border-radius: 10px;
	font-size: 0.95rem;
	font-weight: 500;
	text-decoration: none;
	cursor: pointer;
	transition: all 0.2s ease;
}

.btn-primary {
	background: linear-gradient(135deg, var(--accent-primary), #ff5252);
	color: white;
}

.btn-primary:hover {
	transform: translateY(-2px);
}

/* 悬浮刷新按钮 */
.floating-refresh-btn {
	position: fixed;
	bottom: 2rem;
	right: 2rem;
	width: 60px;
	height: 60px;
	border-radius: 50%;
	background: linear-gradient(135deg, var(--accent-primary), #ff5252);
	border: none;
	box-shadow: 0 4px 20px rgba(255, 107, 107, 0.3);
	cursor: pointer;
	transition: all 0.3s ease;
	z-index: 1000;
	display: block;
	align-items: center;
	justify-content: center;
	color: white;
	font-size: 1.2rem;
}

.floating-refresh-btn:hover:not(:disabled) {
	transform: translateY(-3px);
	box-shadow: 0 6px 25px rgba(255, 107, 107, 0.4);
}

.floating-refresh-btn:disabled {
	opacity: 0.7;
	cursor: not-allowed;
}

.refresh-icon {
	display: block;
	transition: transform 0.3s ease;
}

.refresh-icon.spinning {
	animation: spin 1s linear infinite;
}

@keyframes spin {
	from {
		transform: rotate(0deg);
	}
	to {
		transform: rotate(360deg);
	}
}

@media (max-width: 768px) {
	.controls {
		flex-direction: column;
	}

	.filters {
		width: 100%;
	}

	.filter-select {
		flex: 1;
	}

	.floating-refresh-btn {
		bottom: 1.5rem;
		right: 1.5rem;
		width: 50px;
		height: 50px;
		font-size: 1rem;
	}
}
</style>
