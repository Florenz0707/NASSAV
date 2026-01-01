<script setup>
import {computed, onMounted, ref, watch} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {downloadApi, resourceApi} from '../api'
import {useResourceStore} from '../stores/resource'
import {useToastStore} from '../stores/toast'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
const toastStore = useToastStore()

const avid = computed(() => route.params.avid)
const metadata = ref(null)
const loading = ref(true)
const error = ref(null)
const downloading = ref(false)
const refreshing = ref(false)
const showConfirmDialog = ref(false)
const pendingDeleteAction = ref(null)

const coverUrl = ref(null)

async function loadCover() {
	if (!avid.value) return
	// For detail view prefer the original/full cover URL (no size)
	coverUrl.value = resourceApi.getCoverUrl(avid.value)
}

watch(avid, () => loadCover(), {immediate: true})

const actorsText = computed(() => {
	const list = metadata.value?.actors
	if (!Array.isArray(list) || list.length === 0) return null
	return list.join(', ')
})

const genresText = computed(() => {
	const list = metadata.value?.genres
	if (!Array.isArray(list) || list.length === 0) return null
	return list.join(', ')
})

const fileSize = computed(() => {
	if (!metadata.value?.file_size) return null
	const bytes = metadata.value.file_size
	if (bytes < 1024) return `${bytes} B`
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
	if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
	return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
})

onMounted(async () => {
	await fetchMetadata()
})

async function fetchMetadata() {
	loading.value = true
	error.value = null
	try {
		const response = await resourceApi.getMetadata(avid.value)
		metadata.value = response.data
	} catch (err) {
		error.value = err.message || '获取元数据失败'
	} finally {
		loading.value = false
	}
}

async function handleDownload() {
	downloading.value = true
	try {
		await resourceStore.submitDownload(avid.value)
		toastStore.success('下载任务已提交')
	} catch (err) {
		if (err.code === 409) {
			toastStore.info('视频已下载')
		} else {
			toastStore.error(err.message || '提交下载失败')
		}
	} finally {
		downloading.value = false
	}
}

async function handleRefresh() {
	refreshing.value = true
	try {
		await resourceStore.refreshResource(avid.value)
		await fetchMetadata()
		toastStore.success('刷新成功')
	} catch (err) {
		toastStore.error(err.message || '刷新失败')
	} finally {
		refreshing.value = false
	}
}

function goBack() {
	router.back()
}

async function jumpPlay() {
	try {
		const resp = await downloadApi.getFilePath(avid.value)
		if (!resp || (typeof resp.code === 'number' && (resp.code < 200 || resp.code >= 300))) {
			toastStore.error(resp.message || '获取路径失败')
		}

		const path = resp.data.abspath
		if (!path)
			toastStore.error('未返回文件路径')

		const fileUrl = `file:/${path}`
		await navigator.clipboard.writeText(fileUrl)
		toastStore.success('视频路径已复制到剪贴板')
	} catch (err) {
		toastStore.error(err.message)
	}
}

// 删除全部数据
function deleteMetadata() {
	pendingDeleteAction.value = {
		action: 'delete',
		title: '删除全部数据',
		message: '确定要删除该资源的所有数据（包括视频、元数据、封面）吗？此操作不可恢复！'
	}
	showConfirmDialog.value = true
}

// 删除视频文件
function deleteFile() {
	pendingDeleteAction.value = {
		action: 'deleteFile',
		title: '删除视频文件',
		message: '确定要删除视频文件吗？元数据和封面将保留。'
	}
	showConfirmDialog.value = true
}

// 确认删除操作
async function confirmDelete() {
	const action = pendingDeleteAction.value
	if (!action) return

	try {
		if (action.action === 'deleteFile') {
			await downloadApi.deleteFile(avid.value)
			toastStore.success('视频文件已删除')
			await fetchMetadata() // 刷新元数据以更新状态
		} else {
			await resourceApi.delete(avid.value)
			toastStore.success('资源已删除')
			// 删除后返回上一页
			setTimeout(() => router.back(), 500)
		}
	} catch (err) {
		toastStore.error(err.message || `删除${action.action === 'deleteFile' ? '视频' : '资源'}失败`)
	} finally {
		pendingDeleteAction.value = null
	}
}

// 取消删除操作
function cancelDelete() {
	pendingDeleteAction.value = null
}
</script>

<template>
	<div class="animate-[fadeIn_0.5s_ease]">
		<!-- 返回按钮 -->
		<button
			class="inline-flex items-center gap-2 px-4 py-2.5 bg-transparent border border-white/[0.08] rounded-lg text-[#a1a1aa] text-sm cursor-pointer transition-all duration-200 mb-8 hover:bg-white/5 hover:text-[#f4f4f5]"
			@click="goBack"
		>
			<span class="text-[1.1rem]">←</span>
			返回
		</button>

		<!-- 加载状态 -->
		<LoadingSpinner v-if="loading" size="large" text="加载详情中..."/>

		<!-- 错误状态 -->
		<div v-else-if="error" class="text-center py-16 px-8">
			<div
				class="w-16 h-16 mx-auto mb-6 bg-[#ff6b6b]/10 rounded-full flex items-center justify-center text-2xl text-[#ff6b6b]">
				✕
			</div>
			<h2 class="text-xl text-[#f4f4f5] mb-2">加载失败</h2>
			<p class="text-[#71717a] mb-6">{{ error }}</p>
			<button
				class="inline-flex items-center gap-2 px-6 py-3.5 border-none rounded-[10px] text-[0.95rem] font-medium cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(255,107,107,0.3)]"
				@click="fetchMetadata"
			>
				重试
			</button>
		</div>

		<!-- 详情内容 -->
		<template v-else-if="metadata">
			<!-- 头部信息 -->
			<div class="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-10 mb-12">
				<!-- 封面 -->
				<div
					class="relative h-[310px] rounded-2xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.1)] flex justify-center items-center">
					<img
						:src="coverUrl"
						:alt="metadata.title"
						class="h-full aspect-auto object-cover block"
					/>
				</div>

				<!-- 右侧信息 -->
				<div class="flex flex-col justify-center">
					<!-- AVID 和状态 -->
					<div class="grid grid-cols-2 gap-4 mb-2.5">
						<div
							class="inline-block px-3.5 py-1.5 bg-[#ff6b6b]/15 rounded-md font-['JetBrains_Mono',monospace] text-[0.9rem] font-semibold text-[#ff6b6b] w-fit">
							{{ metadata.avid }}
						</div>
						<div
							class="inline-block px-3.5 py-1.5 bg-[#ff6b6b]/15 rounded-md font-['JetBrains_Mono',monospace] text-[0.9rem] font-semibold w-fit"
							:class="metadata.file_exists ? 'text-[#ff6b6b]' : 'text-[#ff9f43]'"
						>
							{{ metadata.file_exists ? '已下载' : '未下载' }}
						</div>
					</div>

					<!-- 标题 -->
					<h1 class="text-[1.75rem] font-semibold text-[#f4f4f5] leading-[1.4] mb-6">
						{{ metadata.title }}
					</h1>

					<!-- 元数据网格 -->
					<div class="grid grid-cols-2 gap-4 mb-8">
						<div v-if="metadata.release_date" class="flex flex-col gap-1">
							<span class="text-[0.8rem] text-[#71717a] uppercase tracking-wider">发行日期</span>
							<span class="text-base text-[#f4f4f5]">{{ metadata.release_date }}</span>
						</div>
						<div v-if="metadata.duration" class="flex flex-col gap-1">
							<span class="text-[0.8rem] text-[#71717a] uppercase tracking-wider">时长</span>
							<span class="text-base text-[#f4f4f5]">{{ metadata.duration }}</span>
						</div>
						<div class="flex flex-col gap-1">
							<span class="text-[0.8rem] text-[#71717a] uppercase tracking-wider">来源</span>
							<span class="text-base text-[#ff9f43] font-medium">{{ metadata.source }}</span>
						</div>
						<div v-if="fileSize" class="flex flex-col gap-1">
							<span class="text-[0.8rem] text-[#71717a] uppercase tracking-wider">文件大小</span>
							<span class="text-base text-[#f4f4f5]">{{ fileSize }}</span>
						</div>
					</div>

					<!-- 操作按钮 -->
					<div class="flex flex-wrap gap-4">
						<button
							v-if="!metadata.file_exists"
							class="inline-flex items-center justify-center px-6 py-3.5 border-none rounded-[10px] text-[0.95rem] font-medium cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(255,107,107,0.3)] disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:translate-y-0"
							:disabled="downloading"
							@click="handleDownload"
						>
							{{ downloading ? '提交中...' : '下载视频' }}
						</button>
						<button
							v-if="metadata.file_exists"
							class="inline-flex items-center gap-2 px-6 py-3.5 border-none rounded-[10px] text-[0.95rem] font-medium cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(255,107,107,0.3)]"
							@click="jumpPlay"
						>
							<span class="text-[1.1rem]">▶</span>
							点击播放
						</button>
						<button
							class="inline-flex items-center justify-center px-6 py-3.5 border-none rounded-[10px] text-[0.95rem] font-medium cursor-pointer transition-all duration-200 bg-white/[0.08] text-[#f4f4f5] border border-white/[0.08] hover:bg-white/[0.12] disabled:opacity-60 disabled:cursor-not-allowed"
							:disabled="refreshing"
							@click="handleRefresh"
						>
							{{ refreshing ? '刷新中...' : '刷新信息' }}
						</button>
						<button
							v-if="metadata.file_exists"
							class="inline-flex items-center justify-center px-6 py-3.5 border-none rounded-[10px] text-[0.95rem] font-medium cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#dc3558] to-[#ff5252] text-white hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(255,107,107,0.3)]"
							@click="deleteFile"
						>
							删除视频
						</button>
						<button
							class="inline-flex items-center justify-center px-6 py-3.5 border-none rounded-[10px] text-[0.95rem] font-medium cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff0000] to-[#dc3558] text-white hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(255,107,107,0.3)]"
							@click="deleteMetadata"
						>
							删除全部
						</button>
					</div>
				</div>
			</div>

			<!-- 详细信息区域 -->
			<div class="flex flex-col gap-8">
				<section
					v-if="metadata.director || metadata.studio || metadata.label || metadata.actors?.length || metadata.series || metadata.genres?.length"
					class="bg-[rgba(18,18,28,0.8)] rounded-2xl border border-white/[0.08] p-6"
				>
					<h2 class="text-[1.1rem] font-semibold text-[#f4f4f5] mb-5 pb-3 border-b border-white/[0.08]">
						制作信息
					</h2>
					<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
						<div v-if="actorsText" class="flex flex-col gap-1.5">
							<span class="text-[0.8rem] text-[#71717a]">演员</span>
							<div class="text-[0.95rem] text-[#f4f4f5]">{{ actorsText }}</div>
						</div>
						<div v-if="metadata.series" class="flex flex-col gap-1.5">
							<span class="text-[0.8rem] text-[#71717a]">系列</span>
							<span class="text-[0.95rem] text-[#f4f4f5]">{{ metadata.series }}</span>
						</div>
						<div v-if="metadata.director" class="flex flex-col gap-1.5">
							<span class="text-[0.8rem] text-[#71717a]">导演</span>
							<span class="text-[0.95rem] text-[#f4f4f5]">{{ metadata.director }}</span>
						</div>
						<div v-if="metadata.studio" class="flex flex-col gap-1.5">
							<span class="text-[0.8rem] text-[#71717a]">制作商</span>
							<span class="text-[0.95rem] text-[#f4f4f5]">{{ metadata.studio }}</span>
						</div>
						<div v-if="metadata.label" class="flex flex-col gap-1.5">
							<span class="text-[0.8rem] text-[#71717a]">发行商</span>
							<span class="text-[0.95rem] text-[#f4f4f5]">{{ metadata.label }}</span>
						</div>
						<div v-if="genresText" class="flex flex-col gap-1.5">
							<span class="text-[0.8rem] text-[#71717a]">类别</span>
							<span class="text-[0.95rem] text-[#f4f4f5]">{{ genresText }}</span>
						</div>
					</div>
				</section>
			</div>
		</template>

		<!-- 确认对话框 -->
		<ConfirmDialog
			v-model:show="showConfirmDialog"
			:title="pendingDeleteAction?.title || '确认操作'"
			:message="pendingDeleteAction?.message || ''"
			:type="'danger'"
			confirm-text="确认删除"
			cancel-text="取消"
			@confirm="confirmDelete"
			@cancel="cancelDelete"
		/>
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
</style>
