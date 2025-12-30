<script setup>
import {ref, onMounted, onUnmounted, onBeforeUnmount} from 'vue'
import {useResourceStore} from '../stores/resource'
import {resourceApi, taskApi} from '../api'

const resourceStore = useResourceStore()

const loading = ref(true)
const downloadedResources = ref([])
const pollingTimer = ref(null)

// 任务状态
const activeTasks = ref([])
const pendingTasks = ref([])
const scheduledTasks = ref([])  // 为了兼容模板
const notifications = ref([])  // 为了兼容模板
const activeCount = ref(0)
const pendingCount = ref(0)
const totalCount = ref(0)

onMounted(() => {
	// 不阻塞地加载下载列表
	loadDownloads()
	// 立即启动轮询
	startPolling()
})

onBeforeUnmount(() => {
	stopPolling()
})

onUnmounted(() => {
	stopPolling()
})

async function loadDownloads() {
	loading.value = true
	try {
		await resourceStore.fetchResources()
		await resourceStore.fetchDownloads()

		// 获取已下载资源的详情
		downloadedResources.value = resourceStore.resources.filter(r => r.has_video)
	} finally {
		loading.value = false
	}
}

// 获取任务队列状态
async function fetchQueueStatus() {
	try {
		const response = await taskApi.getQueueStatus()
		// 后端直接返回数据对象，不包装在 code/data 中
		const data = response.data
		if (data) {
			activeTasks.value = data.active_tasks || []
			pendingTasks.value = data.pending_tasks || []
			scheduledTasks.value = data.pending_tasks || []  // 使用 pending_tasks 作为 scheduledTasks
			activeCount.value = data.active_count || 0
			pendingCount.value = data.pending_count || 0
			totalCount.value = data.total_count || 0
		}
	} catch (error) {
		console.error('获取任务队列状态失败:', error)
	}
}

// 开始轮询
function startPolling() {
	// 先停止之前的轮询
	stopPolling()
	// 立即获取一次
	fetchQueueStatus()
	// 每 0.5 秒轮询一次
	pollingTimer.value = setInterval(() => {
		fetchQueueStatus()
	}, 1000)
}

// 停止轮询
function stopPolling() {
	if (pollingTimer.value) {
		console.log('停止轮询')
		clearInterval(pollingTimer.value)
		pollingTimer.value = null
	}
}

</script>

<template>
	<div class="downloads-view">
		<div class="page-header">
			<h1 class="page-title">下载管理</h1>
			<p class="page-subtitle">实时监控下载任务与已下载视频</p>
		</div>

		<!-- 任务队列统计 -->
		<div class="stats-bar">
			<div class="stat stat-active">
				<span class="stat-value">{{ activeCount }}</span>
				<span class="stat-label">正在下载</span>
			</div>
			<div class="stat stat-waiting">
				<span class="stat-value">{{ pendingCount }}</span>
				<span class="stat-label">等待中</span>
			</div>
			<div class="stat stat-total">
				<span class="stat-value">{{ totalCount }}</span>
				<span class="stat-label">总任务数</span>
			</div>
		</div>

		<!-- 正在下载的任务 -->
		<div v-if="activeTasks.length > 0" class="task-section">
			<h2 class="section-title">
				正在下载 ({{ activeTasks.length }})
			</h2>
			<div class="tasks-grid">
				<div v-for="task in activeTasks" :key="task.task_id" class="task-card downloading">
					<div class="task-cover">
						<img :src="resourceApi.getCoverUrl(task.avid)" :alt="task.avid" loading="lazy"/>
						<div v-if="task.progress" class="task-overlay">
							<span class="task-badge downloading">{{ task.progress.percent?.toFixed(1) || 0 }}%</span>
						</div>
					</div>
					<div class="task-content">
						<div class="task-avid">{{ task.avid }}</div>
						<div v-if="task.progress" class="progress-bar">
							<div class="progress-fill" :style="{ width: (task.progress.percent || 0) + '%' }"></div>
						</div>
						<div v-if="task.progress" class="task-status-text">
							{{ task.progress.speed || '计算中...' }}
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- 等待下载的任务 -->
		<div v-if="scheduledTasks.length > 0" class="task-section">
			<h2 class="section-title">
				<span class="title-icon">⏳</span>
				等待队列 ({{ scheduledTasks.length }})
			</h2>
			<div class="tasks-grid">
				<div v-for="task in scheduledTasks" :key="task.task_id" class="task-card waiting">
					<div class="task-cover">
						<img :src="resourceApi.getCoverUrl(task.avid)" :alt="task.avid" loading="lazy"/>
						<div class="task-overlay">
							<span class="task-badge">等待中</span>
						</div>
					</div>
					<div class="task-content">
						<div class="task-avid">{{ task.avid }}</div>
						<div class="progress-bar">
							<div class="progress-fill pending"></div>
						</div>
						<div class="task-status-text">排队等待...</div>
					</div>
				</div>
			</div>
		</div>

		<!-- 最近通知 -->
		<div v-if="notifications.length > 0" class="task-section">
			<h2 class="section-title">
				<span class="title-icon">🔔</span>
				最近通知 ({{ notifications.length }})
			</h2>
			<div class="notifications-list">
				<div
					v-for="(notif, index) in notifications.slice(0, 10)"
					:key="index"
					class="notification-item"
					:class="notif.type"
				>
					<span class="notification-icon">
						{{ notif.type === 'success' ? '✓' : notif.type === 'error' ? '✗' : 'ℹ' }}
					</span>
					<span class="notification-message">{{ notif.message }}</span>
					<span class="notification-time">{{ notif.time }}</span>
				</div>
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
	position: relative;
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
	margin-bottom: 1rem;
}

.ws-status {
	display: inline-flex;
	align-items: center;
	gap: 0.5rem;
	padding: 0.5rem 1rem;
	background: rgba(0, 0, 0, 0.2);
	border-radius: 8px;
	font-size: 0.85rem;
}

.ws-indicator {
	width: 8px;
	height: 8px;
	border-radius: 50%;
	background: #ff4757;
	animation: pulse-red 2s infinite;
}

.ws-indicator.connected {
	background: #2ed573;
	animation: pulse-green 2s infinite;
}

@keyframes pulse-red {
	0%, 100% { opacity: 1; }
	50% { opacity: 0.5; }
}

@keyframes pulse-green {
	0%, 100% { opacity: 1; }
	50% { opacity: 0.6; }
}

.ws-text {
	color: var(--text-muted);
}

.stats-bar {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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

.stat-completed {
	border-color: rgba(72, 219, 251, 0.3);
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

.task-section {
	margin-bottom: 2.5rem;
}

.section-title {
	display: flex;
	align-items: center;
	gap: 0.5rem;
	font-size: 1.25rem;
	font-weight: 600;
	color: var(--text-primary);
	margin-bottom: 1rem;
}

.title-icon {
	font-size: 1.5rem;
}

.tasks-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
	gap: 1.25rem;
}

.task-card {
	background: var(--card-bg);
	border-radius: 16px;
	overflow: hidden;
	border: 1px solid var(--border-color);
	transition: all 0.3s ease;
}

.task-card.downloading {
	border-color: rgba(46, 213, 115, 0.3);
}

.task-card.waiting {
	border-color: rgba(255, 159, 67, 0.3);
}

.task-card:hover {
	transform: translateY(-4px);
	box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
}

.task-cover {
	position: relative;
	aspect-ratio: 16 / 9;
	overflow: hidden;
	background: rgba(0, 0, 0, 0.3);
}

.task-cover img {
	width: 100%;
	height: 100%;
	object-fit: cover;
	transition: transform 0.3s ease;
}

.task-card:hover .task-cover img {
	transform: scale(1.05);
}

.task-overlay {
	position: absolute;
	inset: 0;
	background: linear-gradient(to bottom, rgba(0,0,0,0.3), rgba(0,0,0,0.7));
	display: flex;
	align-items: center;
	justify-content: center;
}

.task-duration {
	font-size: 1.5rem;
	color: white;
	font-family: 'JetBrains Mono', monospace;
	font-weight: 700;
	text-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
}

.task-badge {
	padding: 0.5rem 1rem;
	background: rgba(255, 159, 67, 0.9);
	color: white;
	border-radius: 6px;
	font-size: 0.85rem;
	font-weight: 600;
	text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.task-content {
	display: flex;
	justify-content: center;
	padding: 1rem;
}

.task-avid {
	font-family: 'JetBrains Mono', monospace;
	font-size: 0.9rem;
	font-weight: 600;
	color: var(--accent-primary);
	margin-bottom: 0.2rem;
	background: rgba(255, 107, 107, 0.15);
	border-radius: 6px;
	width: fit-content;
	padding: 4px 8px;
}

.progress-bar {
	width: 100%;
	height: 6px;
	background: rgba(0, 0, 0, 0.3);
	border-radius: 3px;
	overflow: hidden;
	margin-bottom: 0.75rem;
}

.progress-fill {
	height: 100%;
	border-radius: 3px;
	transition: width 0.3s ease;
}

.progress-fill.active {
	width: 100%;
	background: linear-gradient(90deg,
		#2ed573 0%,
		#7bed9f 50%,
		#2ed573 100%
	);
	background-size: 200% 100%;
	animation: shimmer 2s infinite;
}

.progress-fill.pending {
	width: 20%;
	background: rgba(255, 159, 67, 0.5);
}

@keyframes shimmer {
	0% { background-position: 200% 0; }
	100% { background-position: -200% 0; }
}

.task-status-text {
	font-size: 0.85rem;
	color: var(--text-muted);
	font-weight: 500;
}

.notifications-list {
	display: flex;
	flex-direction: column;
	gap: 0.5rem;
}

.notification-item {
	display: flex;
	align-items: center;
	gap: 1rem;
	padding: 1rem 1.25rem;
	background: var(--card-bg);
	border-radius: 10px;
	border-left: 3px solid;
	transition: all 0.2s ease;
	animation: slideIn 0.3s ease;
}

@keyframes slideIn {
	from {
		opacity: 0;
		transform: translateX(-20px);
	}
	to {
		opacity: 1;
		transform: translateX(0);
	}
}

.notification-item.success {
	border-left-color: #2ed573;
	background: rgba(46, 213, 115, 0.05);
}

.notification-item.error {
	border-left-color: #ff4757;
	background: rgba(255, 71, 87, 0.05);
}

.notification-item.info {
	border-left-color: #56ccf2;
	background: rgba(86, 204, 242, 0.05);
}

.notification-item:hover {
	transform: translateX(4px);
}

.notification-icon {
	font-size: 1.25rem;
	font-weight: bold;
	flex-shrink: 0;
}

.notification-item.success .notification-icon {
	color: #2ed573;
}

.notification-item.error .notification-icon {
	color: #ff4757;
}

.notification-item.info .notification-icon {
	color: #56ccf2;
}

.notification-message {
	flex: 1;
	color: var(--text-primary);
	font-size: 0.9rem;
}

.notification-time {
	color: var(--text-muted);
	font-size: 0.8rem;
	font-family: 'JetBrains Mono', monospace;
	flex-shrink: 0;
}

.downloads-list {
	display: flex;
	flex-direction: column;
	gap: 1rem;
}

.download-item {
	display: flex;
	align-items: center;
	gap: 1.25rem;
	padding: 1rem;
	background: var(--card-bg);
	border-radius: 16px;
	border: 1px solid var(--border-color);
	text-decoration: none;
	transition: all 0.2s ease;
}

.download-item:hover {
	border-color: rgba(46, 213, 115, 0.3);
	transform: translateX(4px);
}

.download-cover {
	width: 120px;
	height: 68px;
	object-fit: cover;
	border-radius: 10px;
	background: rgba(0, 0, 0, 0.3);
	flex-shrink: 0;
}

.download-info {
	flex: 1;
	min-width: 0;
}

.download-avid {
	font-family: 'JetBrains Mono', monospace;
	font-size: 0.9rem;
	font-weight: 600;
	color: var(--accent-primary);
	margin-bottom: 0.35rem;
}

.download-title {
	font-size: 1rem;
	color: var(--text-primary);
	margin-bottom: 0.5rem;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}

.download-meta {
	display: flex;
	gap: 0.5rem;
}

.meta-tag {
	padding: 0.25rem 0.6rem;
	background: rgba(255, 255, 255, 0.05);
	border-radius: 4px;
	font-size: 0.75rem;
	color: var(--text-muted);
}

.meta-tag.source {
	background: rgba(255, 159, 67, 0.15);
	color: var(--accent-secondary);
}

.download-status {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 0.25rem;
	padding: 0.75rem 1rem;
	background: rgba(46, 213, 115, 0.1);
	border-radius: 10px;
	flex-shrink: 0;
}

.status-icon {
	font-size: 1.25rem;
	color: #2ed573;
}

.status-text {
	font-size: 0.75rem;
	color: #2ed573;
	font-weight: 500;
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

@media (max-width: 768px) {
	.stats-bar {
		grid-template-columns: repeat(2, 1fr);
	}

	.tasks-list {
		grid-template-columns: 1fr;
	}

	.notification-item {
		flex-direction: column;
		align-items: flex-start;
		gap: 0.5rem;
	}
}

@media (max-width: 640px) {
	.download-item {
		flex-direction: column;
		align-items: flex-start;
	}

	.download-cover {
		width: 100%;
		height: auto;
		aspect-ratio: 16 / 9;
	}

	.download-status {
		width: 100%;
		flex-direction: row;
		justify-content: center;
	}
}
</style>
