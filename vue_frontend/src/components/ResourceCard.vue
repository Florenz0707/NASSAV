<script setup>
import {computed, ref, onMounted, onUnmounted} from 'vue'
import {resourceApi, downloadApi} from '../api'
import {useToastStore} from '../stores/toast'
import {RouterLink} from 'vue-router'

const props = defineProps({
	resource: {
		type: Object,
		required: true
	}
})

const emit = defineEmits(['download', 'refresh', 'delete', 'deleteFile'])

const coverUrl = computed(() => resourceApi.getCoverUrl(props.resource.avid))
const statusClass = computed(() => ({
	downloaded: props.resource.has_video,
	pending: !props.resource.has_video
}))

const toastStore = useToastStore()
const showDeleteMenu = ref(false)

// 生成删除菜单选项
const deleteOptions = computed(() => {
	const isDownloaded = props.resource.has_video
	const baseOptions = []

	if (isDownloaded) {
		baseOptions.push(
			{text: '删除视频', action: 'deleteFile', confirm: '确定要删除视频文件吗？元数据和封面将保留'},
			{text: '全部删除', action: 'delete', confirm: '确定要删除该资源的所有数据（包括视频、元数据、封面）吗？'}
		)
	} else {
		baseOptions.push(
			{text: '删除数据', action: 'delete', confirm: '确定要删除该资源的元数据和封面吗？'}
		)
	}
	return baseOptions
})

// 点击删除选项后的确认与执行
async function handleDeleteOption(option) {
	if (!confirm(option.confirm)) return

	try {
		if (option.action === 'deleteFile') {
			await downloadApi.deleteFile(props.resource.avid)
			toastStore.success('视频文件已删除')
			emit('deleteFile', props.resource.avid)
		} else {
			await resourceApi.delete(props.resource.avid)
			toastStore.success('资源已删除')
			emit('delete', props.resource.avid)
		}
		showDeleteMenu.value = false
	} catch (err) {
		toastStore.error(err.message || `删除${option.action === 'deleteFile' ? '视频' : '资源'}失败`)
	}
}

// 点击外部关闭菜单
function closeMenuOnOutsideClick(event) {
	const menu = document.querySelector(`.delete-menu[data-avid="${props.resource.avid}"]`)
	const btn = document.querySelector(`.delete-btn[data-avid="${props.resource.avid}"]`)
	if (menu && btn && !menu.contains(event.target) && !btn.contains(event.target)) {
		showDeleteMenu.value = false
	}
}

onMounted(() => {
	document.addEventListener('click', closeMenuOnOutsideClick)
})
onUnmounted(() => {
	document.removeEventListener('click', closeMenuOnOutsideClick)
})
</script>

<template>
	<div class="resource-card" :class="statusClass">
		<div class="card-cover">
			<img :src="coverUrl" :alt="resource.title" loading="lazy"/>
			<div class="cover-overlay">
				<RouterLink :to="`/resource/${resource.avid}`" class="btn-view">
					查看详情
				</RouterLink>
			</div>
			<div class="status-badge" :class="{ downloaded: resource.has_video }">
				{{ resource.has_video ? '已下载' : '未下载' }}
			</div>
		</div>

		<div class="card-content">
			<div class="meta-head">
				<div class="card-avid">{{ resource.avid }}</div>
				<div class="card-download" :class="{ downloaded: resource.has_video }">
					{{ resource.has_video ? '已下载' : '未下载' }}
				</div>
			</div>
			<h3 class="card-title" :title="resource.title">{{ resource.title }}</h3>

			<div class="card-meta">
        <span class="meta-item">
          <span class="meta-icon">◉</span>
          {{ resource.source }}
        </span>
				<span class="meta-item" v-if="resource.release_date">
          <span class="meta-icon">◷</span>
          {{ resource.release_date }}
        </span>
			</div>

			<div class="card-actions">
				<button
					class="btn btn-secondary btn-small"
					@click="emit('refresh', resource.avid)"
				>
					<span class="btn-icon">↻</span>
					刷新
				</button>

				<button
					v-if="!resource.has_video"
					class="btn btn-primary btn-small"
					@click="emit('download', resource.avid)"
				>
					<span class="btn-icon">⬇</span>
					下载
				</button>

				<!-- 删除按钮容器 -->
				<div class="delete-container" @click.stop>
					<button
						class="btn delete-btn btn-small"
						:data-avid="resource.avid"
						@click="showDeleteMenu = !showDeleteMenu"
						title="删除"
					>
						<span class="btn-icon">✕</span>
						删除
					</button>

					<!-- 下拉菜单（定位到按钮上方） -->
					<div
						class="delete-menu"
						v-if="showDeleteMenu"
						:data-avid="resource.avid"
					>
						<button
							v-for="option in deleteOptions"
							:key="option.action"
							class="delete-menu-item"
							@click="handleDeleteOption(option)"
						>
							{{ option.text }}
						</button>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.resource-card {
	background: var(--card-bg);
	border-radius: 16px;
	overflow: hidden;
	border: 1px solid var(--border-color);
	transition: all 0.3s ease;
}

.resource-card:hover {
	transform: translateY(-4px);
	border-color: rgba(255, 107, 107, 0.3);
	box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
}

.card-cover {
	position: relative;
	aspect-ratio: 16 / 9;
	overflow: hidden;
	background: rgba(0, 0, 0, 0.3);
}

.card-cover img {
	width: 100%;
	height: 100%;
	object-fit: cover;
	transition: transform 0.5s ease;
}

.resource-card:hover .card-cover img {
	transform: scale(1.05);
}

.cover-overlay {
	position: absolute;
	inset: 0;
	background: rgba(0, 0, 0, 0.6);
	display: flex;
	align-items: center;
	justify-content: center;
	opacity: 0;
	transition: opacity 0.3s ease;
}

.resource-card:hover .cover-overlay {
	opacity: 1;
}

.btn-view {
	padding: 0.75rem 1.5rem;
	background: var(--accent-primary);
	color: white;
	border-radius: 8px;
	text-decoration: none;
	font-weight: 500;
	font-size: 0.9rem;
	transition: transform 0.2s ease;
}

.btn-view:hover {
	transform: scale(1.05);
}

.card-content {
	padding: 1.25rem;
	position: relative; /* 确保菜单不会超出卡片 */
}

.meta-head {
	display: grid;
	grid-template-columns: repeat(2, 1fr);
	gap: 1rem;
	margin-bottom: 10px;
}

.card-avid {
	font-family: 'JetBrains Mono', monospace;
	font-size: 0.85rem;
	color: var(--accent-primary);
	font-weight: 600;
	margin-bottom: 0.5rem;
	background: rgba(255, 107, 107, 0.15);
	border-radius: 6px;
	width: fit-content;
	padding: 4px 8px;
}

.card-download {
	font-family: 'JetBrains Mono', monospace;
	font-size: 0.85rem;
	color: var(--accent-secondary);
	font-weight: 600;
	margin-bottom: 0.5rem;
	background: rgba(255, 107, 107, 0.15);
	border-radius: 6px;
	width: fit-content;
	padding: 4px 8px;
}

.card-download.downloaded {
	color: var(--accent-primary);
}

.card-title {
	font-size: 1rem;
	font-weight: 500;
	color: var(--text-primary);
	line-height: 1.4;
	margin-bottom: 0.75rem;
	display: -webkit-box;
	-webkit-line-clamp: 2;
	-webkit-box-orient: vertical;
	overflow: hidden;
}

.card-meta {
	display: flex;
	flex-wrap: wrap;
	gap: 0.75rem;
	margin-bottom: 1rem;
	justify-content: left;
}

.meta-item {
	display: flex;
	align-items: center;
	gap: 0.35rem;
	font-size: 0.8rem;
	color: var(--text-muted);
}

.meta-icon {
	font-size: 0.7rem;
	opacity: 0.7;
}

.card-actions {
	display: flex;
	gap: 0.5rem;
	justify-content: space-between;
	align-items: center;
	position: relative;
}

.btn {
	display: inline-flex;
	align-items: center;
	gap: 0.4rem;
	padding: 0.6rem 1rem;
	border: none;
	border-radius: 8px;
	font-size: 0.85rem;
	font-weight: 500;
	cursor: pointer;
	transition: all 0.2s ease;
}

.btn-small {
	padding: 0.5rem 0.85rem;
	font-size: 0.8rem;
}

.btn-primary {
	background: var(--accent-primary);
	color: white;
}

.btn-primary:hover {
	background: #ff5252;
	transform: translateY(-1px);
}

.btn-secondary {
	background: rgba(255, 255, 255, 0.08);
	color: var(--text-secondary);
}

.btn-secondary:hover {
	background: rgba(255, 255, 255, 0.12);
	color: var(--text-primary);
}

.btn-icon {
	font-size: 0.9rem;
}

/* 删除按钮容器 */
.delete-container {
	position: relative;
}

/* 删除按钮样式 */
.delete-btn {
	background: rgba(239, 71, 111, 0.1);
	color: #ef476f;
	border: 1px solid rgba(239, 71, 111, 0.2);
}

.delete-btn:hover {
	background: rgba(239, 71, 111, 0.2);
	color: #ff5252;
}

/* 下拉菜单（核心修改：定位到按钮上方） */
.delete-menu {
	position: absolute;
	bottom: calc(100% + 0.5rem); /* 改为底部对齐按钮顶部，向上展开 */
	right: 0; /* 右对齐按钮 */
	background: var(--card-bg);
	border: 1px solid var(--border-color);
	border-radius: 8px;
	box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
	min-width: 85px;
	z-index: 100;
	overflow: hidden;
	/* 防止菜单超出卡片 */
	max-height: calc(100vh - 20px);
	overflow-y: auto;
}

/* 菜单选项样式 */
.delete-menu-item {
	width: 100%;
	padding: 0.6rem 1rem;
	text-align: center;
	background: rgba(239, 71, 111, 0.2);
	border: none;
	color: #ef476f;
	font-size: 0.8rem;
	cursor: pointer;
	transition: background 0.2s ease;
}

.delete-menu-item:hover {
	background: rgba(239, 71, 111, 0.1);
	color: #ef476f;
}

/* 响应式调整 */
@media (max-width: 480px) {
	.card-actions .btn span:not(.btn-icon) {
		display: none;
	}

	.card-actions .btn {
		padding: 0.5rem;
	}

	.delete-menu {
		min-width: 100px;
	}

	.delete-menu-item {
		padding: 0.5rem 0.8rem;
		font-size: 0.8rem;
	}
}
</style>
