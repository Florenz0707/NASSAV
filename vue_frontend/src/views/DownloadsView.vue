<script setup>
import {computed, onBeforeUnmount, onUnmounted, ref, watch} from 'vue'
import {useRouter} from 'vue-router'
import {useResourceStore} from '../stores/resource'
import {useWebSocketStore} from '../stores/websocket'
import {useSettingsStore} from '../stores/settings'
import {resourceApi, taskApi} from '../api'

const resourceStore = useResourceStore()
const wsStore = useWebSocketStore()
const settingsStore = useSettingsStore()
const router = useRouter()

const pollingTimer = ref(null)

const POLLING_INTERVAL = 1000  // API 轮询间隔

// 调试模式 - 设为 true 显示样例数据
const DEBUG_MODE = false

// helper to normalize resources array (store may expose a ref)
function getResourcesArray() {
	const raw = resourceStore.resources && resourceStore.resources.value !== undefined ? resourceStore.resources.value : resourceStore.resources
	return Array.isArray(raw) ? raw : []
}

// 根据设置获取显示的标题
function getDisplayedTitle(resource) {
	if (!resource) return ''

	const titleField = settingsStore.displayTitle

	if (titleField === 'original_title' && resource.original_title) {
		return resource.original_title
	}
	if (titleField === 'source_title' && resource.source_title) {
		return resource.source_title
	}
	if (titleField === 'translated_title' && resource.translated_title) {
		return resource.translated_title
	}

	// 降级逻辑：如果首选字段不存在，按优先级返回可用的标题
	return resource.translated_title || resource.source_title || resource.original_title || resource.title || resource.avid
}

// 获取任务标题（从任务对象或资源列表）
function getTaskTitle(task) {
	if (!task) return '正在加载标题...'

	// 如果任务已有标题，直接返回
	if (task.title) return task.title

	// 尝试从资源列表中查找对应的资源
	const resources = getResourcesArray()
	const resource = resources.find(r => r.avid === task.avid)

	if (resource) {
		return getDisplayedTitle(resource)
	}

	// 如果都找不到，返回 AVID
	return task.avid || '正在加载标题...'
}

// 基于资源列表生成模拟任务
const mockActiveTasks = computed(() => {
	const resources = getResourcesArray().slice(0, 2)
	return resources.map((r, i) => ({
		task_id: `mock-active-${i + 1}`,
		avid: r.avid,
		title: getDisplayedTitle(r),
		state: 'STARTED',
		progress: {percent: i === 0 ? 45.2 : 78.9, speed: i === 0 ? '5.2MB/s' : '3.8MB/s'}
	}))
})

const mockPendingTasks = computed(() => {
	const resources = getResourcesArray().slice(2, 5)
	return resources.map((r, i) => ({
		task_id: `mock-pending-${i + 1}`,
		avid: r.avid,
		title: getDisplayedTitle(r)
	}))
})

// 合并所有任务为单一列表
const allTasks = computed(() => {
	const active = DEBUG_MODE && wsStore.activeTasks.length === 0 ? mockActiveTasks.value : wsStore.activeTasks
	const pending = DEBUG_MODE && wsStore.pendingTasks.length === 0 ? mockPendingTasks.value : wsStore.pendingTasks
	return [
		...active.map(t => ({...t, isActive: true})),
		...pending.map(t => ({...t, isActive: false}))
	]
})

// 显示用的计数
const displayActiveCount = computed(() => DEBUG_MODE && wsStore.activeCount === 0 ? mockActiveTasks.value.length : wsStore.activeCount)
const displayPendingCount = computed(() => DEBUG_MODE && wsStore.pendingCount === 0 ? mockPendingTasks.value.length : wsStore.pendingCount)
const displayTotalCount = computed(() => displayActiveCount.value + displayPendingCount.value)

onBeforeUnmount(() => {
	// 离开下载页时停止轮询
	stopPolling()
})

onUnmounted(() => {
	stopPolling()
})

// 监听 WebSocket 连接状态变化
watch(() => wsStore.connected, (isConnected) => {
	if (isConnected) {
		// WebSocket 连接成功，停止轮询
		console.log('[DownloadsView] WebSocket 已连接，停止轮询')
		stopPolling()
	} else if (wsStore.connectionFailed) {
		// WebSocket 断开且已发生连接失败，启动轮询
		console.log('[DownloadsView] WebSocket 连接失败，启动轮询')
		startPolling()
	}
})

// 获取任务队列状态（API 轮询）
async function fetchQueueStatus() {
	try {
		const response = await taskApi.getQueueStatus()
		const data = response.data
		if (data) {
			// 通过 store 更新数据
			wsStore.updateTaskData(data)
		}
	} catch (error) {
		console.error('获取任务队列状态失败:', error)
	}
}

// 开始轮询（仅在下载页且 WebSocket 未连接时使用）
function startPolling() {
	// 如果 WebSocket 已连接，不启动轮询
	if (wsStore.connected) {
		console.log('[DownloadsView] WebSocket 已连接，跳过轮询')
		return
	}

	// 先停止之前的轮询
	stopPolling()
	console.log('[DownloadsView] 启动 API 轮询')
	// 立即获取一次
	fetchQueueStatus()
	// 定时轮询
	pollingTimer.value = setInterval(() => {
		// 再次检查 WebSocket 状态，如果已连接则停止轮询
		if (wsStore.connected) {
			stopPolling()
			return
		}
		fetchQueueStatus()
	}, POLLING_INTERVAL)
}

// 停止轮询
function stopPolling() {
	if (pollingTimer.value) {
		console.log('[DownloadsView] 停止轮询')
		clearInterval(pollingTimer.value)
		pollingTimer.value = null
	}
}

// 点击任务跳转到详情页
function goToResourceDetail(task) {
	if (task && task.avid) {
		router.push(`/resource/${task.avid}`)
	}
}

</script>

<template>
	<div class="downloads-view">
		<div class="page-header">
			<h1 class="page-title">
				下载管理
			</h1>
			<p class="page-subtitle">
				实时监控下载任务与已下载视频
			</p>
		</div>

		<!-- 任务队列统计 -->
		<div class="stats-bar">
			<div class="stat stat-active">
				<span class="stat-value">{{ displayActiveCount }}</span>
				<span class="stat-label">正在下载</span>
			</div>
			<div class="stat stat-waiting">
				<span class="stat-value">{{ displayPendingCount }}</span>
				<span class="stat-label">等待中</span>
			</div>
			<div class="stat stat-total">
				<span class="stat-value">{{ displayTotalCount }}</span>
				<span class="stat-label">总任务数</span>
			</div>
		</div>

		<!-- 下载任务列表 -->
		<div v-if="allTasks.length > 0" class="task-section">
			<h2 class="section-title">
				下载队列
			</h2>
			<div class="tasks-list">
				<div
					v-for="task in allTasks"
					:key="task.task_id"
					class="task-row"
					:class="{ 'is-active': task.isActive }"
					@click="goToResourceDetail(task)"
				>
					<!-- 左侧封面 -->
					<div class="task-cover">
						<img :src="resourceApi.getCoverUrl(task.avid, 'small')" :alt="task.avid" loading="lazy">
					</div>

					<!-- 右侧信息 -->
					<div class="task-info">
						<div class="task-header">
							<span class="task-avid">{{ task.avid }}</span>
							<div v-if="task.isActive" class="task-status-badge active">
								<span class="pulse-dot"/>
								下载中
							</div>
							<div v-else class="task-status-badge pending">
								等待中
							</div>
						</div>
						<div class="task-title">
							{{ getTaskTitle(task) }}
						</div>
						<div class="task-progress">
							<div class="progress-bar">
								<div
									class="progress-fill"
									:class="{ 'is-active': task.isActive }"
									:style="{ width: task.isActive ? (task.progress?.percent || 0) + '%' : '0%' }"
								/>
							</div>
							<span v-if="task.isActive && task.progress"
								class="progress-text">{{ task.progress.percent?.toFixed(1) || 0 }}%</span>
							<span v-else class="progress-text pending">排队中</span>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- 空状态 -->
		<div v-else class="empty-state">
			<div class="empty-icon">
				📥
			</div>
			<div class="empty-text">
				暂无下载任务
			</div>
			<div class="empty-hint">
				在资源详情页点击下载按钮添加任务
			</div>
		</div>
	</div>
</template>

<style scoped>
.downloads-view {
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

/* 统计栏 */
.stats-bar {
	display: grid;
	grid-template-columns: repeat(3, 1fr);
	gap: 1rem;
	margin-bottom: 2rem;
}

.stat {
	display: flex;
	flex-direction: column;
	align-items: center;
	padding: 1.5rem;
	background: var(--card-bg);
	border-radius: 16px;
	border: 1px solid var(--border-color);
	transition: all 0.3s ease;
}

.stat:hover {
	transform: translateY(-2px);
}

.stat-active {
	border-color: rgba(46, 213, 115, 0.3);
}

.stat-waiting {
	border-color: rgba(255, 159, 67, 0.3);
}

.stat-total {
	border-color: rgba(86, 204, 242, 0.3);
}

.stat-value {
	font-size: 2.5rem;
	font-weight: 700;
	color: var(--text-primary);
	font-family: 'JetBrains Mono', monospace;
	margin-bottom: 0.25rem;
}

.stat-label {
	font-size: 0.9rem;
	color: var(--text-muted);
}

/* 任务区块 */
.task-section {
	margin-bottom: 2rem;
}

.section-title {
	font-size: 1.25rem;
	font-weight: 600;
	color: var(--text-primary);
	margin-bottom: 1rem;
}

/* 任务列表 - 长条状布局 */
.tasks-list {
	display: flex;
	flex-direction: column;
	gap: 1rem;
}

.task-row {
	display: flex;
	align-items: stretch;
	background: transparent;
	border-radius: 12px;
	border: 2px solid var(--border-color);
	overflow: visible;
	transition: all 0.3s ease;
	cursor: pointer;
}

.task-row:hover {
	border-color: rgba(255, 107, 107, 0.3);
	transform: translateX(4px);
	box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
}

.task-row.is-active {
	border-color: rgba(46, 213, 115, 0.4);
}

.task-row.is-active:hover {
	border-color: rgba(46, 213, 115, 0.6);
}

/* 任务封面 */
.task-cover {
	position: relative;
	width: 180px;
	min-width: 180px;
	aspect-ratio: 16 / 9;
	overflow: hidden;
	background: rgba(0, 0, 0, 0.3);
	flex-shrink: 0;
	border-radius: 10px;
	margin: 0.5rem;
}

.task-cover img {
	width: 100%;
	height: 100%;
	object-fit: cover;
	border-radius: 10px;
	transition: transform 0.3s ease;
}

/* 状态徽章 - 现在在 header 中 */
.task-status-badge {
	padding: 4px 10px;
	border-radius: 6px;
	font-size: 0.75rem;
	font-weight: 600;
	display: flex;
	align-items: center;
	gap: 6px;
}

.task-status-badge.active {
	background: rgba(46, 213, 115, 0.9);
	color: white;
}

.task-status-badge.pending {
	background: rgba(255, 159, 67, 0.9);
	color: white;
}

.pulse-dot {
	width: 6px;
	height: 6px;
	border-radius: 50%;
	background: white;
	animation: pulse 1.5s infinite;
}

@keyframes pulse {
	0%, 100% {
		opacity: 1;
		transform: scale(1);
	}
	50% {
		opacity: 0.5;
		transform: scale(0.8);
	}
}

/* 任务信息 */
.task-info {
	flex: 1;
	display: flex;
	flex-direction: column;
	justify-content: center;
	padding: 1rem 1.5rem;
	min-width: 0;
}

.task-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 0.5rem;
}

.task-avid {
	font-family: 'JetBrains Mono', monospace;
	font-size: 0.9rem;
	font-weight: 600;
	color: var(--accent-primary);
	background: rgba(255, 107, 107, 0.15);
	border-radius: 6px;
	padding: 4px 10px;
}

.task-speed {
	font-family: 'JetBrains Mono', monospace;
	font-size: 0.85rem;
	color: var(--accent-success);
	font-weight: 500;
}

.task-title {
	font-size: 1rem;
	color: var(--text-primary);
	margin-bottom: 0.75rem;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}

/* 进度条 */
.task-progress {
	display: flex;
	align-items: center;
	gap: 1rem;
}

.progress-bar {
	flex: 1;
	height: 8px;
	background: rgba(255, 255, 255, 0.1);
	border-radius: 4px;
	overflow: hidden;
}

.progress-fill {
	height: 100%;
	border-radius: 4px;
	background: rgba(100, 100, 100, 0.5);
	transition: width 0.3s ease;
}

.progress-fill.is-active {
	background: linear-gradient(90deg, var(--accent-success), #7bed9f, var(--accent-success));
	background-size: 200% 100%;
	animation: shimmer 2s infinite;
}

@keyframes shimmer {
	0% {
		background-position: 200% 0;
	}
	100% {
		background-position: -200% 0;
	}
}

.progress-text {
	font-family: 'JetBrains Mono', monospace;
	font-size: 0.85rem;
	font-weight: 600;
	color: var(--accent-success);
	min-width: 50px;
	text-align: right;
}

.progress-text.pending {
	color: var(--text-muted);
}

/* 空状态 */
.empty-state {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	padding: 4rem 2rem;
	background: var(--card-bg);
	border-radius: 16px;
	border: 1px dashed var(--border-color);
}

.empty-icon {
	font-size: 4rem;
	margin-bottom: 1rem;
	opacity: 0.5;
}

.empty-text {
	font-size: 1.25rem;
	color: var(--text-primary);
	margin-bottom: 0.5rem;
}

.empty-hint {
	font-size: 0.9rem;
	color: var(--text-muted);
}

/* 响应式 */
@media (max-width: 768px) {
	.stats-bar {
		grid-template-columns: repeat(3, 1fr);
		gap: 0.5rem;
	}

	.stat {
		padding: 1rem;
	}

	.stat-value {
		font-size: 1.75rem;
	}

	.task-row {
		flex-direction: column;
	}

	.task-cover {
		width: 100%;
		min-width: unset;
	}

	.task-info {
		padding: 1rem;
	}
}

@media (max-width: 480px) {
	.stats-bar {
		grid-template-columns: 1fr;
	}

	.task-header {
		flex-direction: column;
		align-items: flex-start;
		gap: 0.5rem;
	}
}
</style>
