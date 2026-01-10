<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { actorApi, downloadApi, genreApi, resourceApi } from '../api'
import { useResourceStore } from '../stores/resource'
import { useToastStore } from '../stores/toast'
import { useSettingsStore } from '../stores/settings'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
const toastStore = useToastStore()
const settingsStore = useSettingsStore()

const avid = computed(() => route.params.avid)
const metadata = ref(null)
const loading = ref(true)
const error = ref(null)
const downloading = ref(false)
const refreshing = ref(false)
const showRefreshMenu = ref(false)
const showDeleteMenu = ref(false)
const showConfirmDialog = ref(false)
const pendingDeleteAction = ref(null)

// 刷新菜单选项
const refreshOptions = [
	{ text: '全部刷新', params: { refresh_m3u8: true, refresh_metadata: true, retranslate: false } },
	{ text: 'M3U8', params: { refresh_m3u8: true, refresh_metadata: false, retranslate: false } },
	{ text: '元数据', params: { refresh_m3u8: false, refresh_metadata: true, retranslate: false } },
	{ text: '翻译', params: { refresh_m3u8: false, refresh_metadata: false, retranslate: true } },
	{ text: '元数据+翻译', params: { refresh_m3u8: false, refresh_metadata: true, retranslate: true } }
]

// 删除菜单选项（根据文件是否存在动态计算）
const deleteOptions = computed(() => {
	if (metadata.value?.file_exists) {
		return [
			{ text: '删除视频', action: 'deleteFile', title: '删除视频文件', message: '确定要删除视频文件吗？元数据和封面将保留。' },
			{ text: '删除全部', action: 'delete', title: '删除全部数据', message: '确定要删除该资源的所有数据（包括视频、元数据、封面）吗？此操作不可恢复！' }
		]
	} else {
		return [
			{ text: '删除数据', action: 'delete', title: '删除数据', message: '确定要删除该资源的元数据和封面吗？此操作不可恢复！' }
		]
	}
})

const coverUrl = ref(null)

// 根据设置选择显示的标题
const displayedTitle = computed(() => {
	if (!metadata.value) return ''

	const titleField = settingsStore.displayTitle
	const resource = metadata.value

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
	return resource.source_title || resource.translated_title || resource.original_title || resource.title || resource.avid
})

async function loadCover() {
	if (!avid.value) return
	// For detail view prefer the original/full cover URL (no size)
	coverUrl.value = resourceApi.getCoverUrl(avid.value)
}

watch(avid, () => loadCover(), { immediate: true })

const fileSize = computed(() => {
	if (!metadata.value?.file_size) return null
	const bytes = metadata.value.file_size
	if (bytes < 1024) return `${bytes} B`
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
	if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
	return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
})

// 切换收藏状态
async function toggleFavorite() {
	if (!metadata.value) return
	try {
		const newValue = !metadata.value.is_favorite
		await resourceApi.updateStatus(avid.value, { is_favorite: newValue })
		metadata.value.is_favorite = newValue
		toastStore.success(newValue ? '已添加到收藏' : '已取消收藏')
	} catch (_err) {
		toastStore.error('更新收藏状态失败')
	}
}

// 切换观看状态
async function toggleWatched() {
	if (!metadata.value) return
	try {
		const newValue = !metadata.value.watched
		await resourceApi.updateStatus(avid.value, { watched: newValue })
		metadata.value.watched = newValue
		toastStore.success(newValue ? '已标记为已观看' : '已标记为未观看')
	} catch (_err) {
		toastStore.error('更新观看状态失败')
	}
}

// 点击外部关闭菜单
function closeMenuOnOutsideClick(event) {
	const menu = event.target.closest('.relative')
	if (!menu || !menu.querySelector('button:disabled')) {
		showRefreshMenu.value = false
		showDeleteMenu.value = false
	}
}

onMounted(async () => {
	await fetchMetadata()
	document.addEventListener('click', closeMenuOnOutsideClick)
})

onUnmounted(() => {
	document.removeEventListener('click', closeMenuOnOutsideClick)
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

async function handleRefresh(params = null) {
	showRefreshMenu.value = false
	refreshing.value = true
	try {
		await resourceStore.refreshResource(avid.value, params)
		await fetchMetadata()
		toastStore.success('刷新成功')
	} catch (err) {
		toastStore.error(err.message || '刷新失败')
	} finally {
		refreshing.value = false
	}
}

function handleRefreshOption(option) {
	handleRefresh(option.params)
}

function goBack() {
	const fromPath = route.query.from
	if (fromPath) {
		// 如果有来源页面，直接跳转回去（保留所有 query 参数）
		router.push(fromPath)
	} else {
		// 否则使用浏览器后退
		router.back()
	}
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

// 处理删除菜单选项
function handleDeleteOption(option) {
	showDeleteMenu.value = false
	pendingDeleteAction.value = option
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

// 跳转到演员详情页
async function navigateToActor(actorName) {
	if (!actorName) return
	try {
		// 通过名称查询演员 ID
		const response = await actorApi.getList({ search: actorName, page_size: 1 })
		if (response?.data?.length > 0) {
			const actorId = response.data[0].id
			router.push(`/actors/${actorId}`)
		} else {
			toastStore.warning(`未找到演员：${actorName}`)
		}
	} catch (err) {
		toastStore.error('跳转失败')
		console.error('Navigate to actor failed:', err)
	}
}

// 跳转到类别详情页
async function navigateToGenre(genreName) {
	if (!genreName) return
	try {
		// 通过名称查询类别 ID
		const response = await genreApi.getList({ search: genreName, page_size: 1 })
		if (response?.data?.length > 0) {
			const genreId = response.data[0].id
			router.push(`/genres/${genreId}`)
		} else {
			toastStore.warning(`未找到类别：${genreName}`)
		}
	} catch (err) {
		toastStore.error('跳转失败')
		console.error('Navigate to genre failed:', err)
	}
}
</script>

<template>
	<div class="animate-[fadeIn_0.5s_ease]">
		<!-- 返回按钮 -->
		<button
			class="inline-flex items-center gap-2 px-4 py-2.5 bg-transparent border border-white/[0] rounded-lg text-[#a1a1aa] text-sm cursor-pointer transition-all duration-200 mb-8 hover:bg-white/5 hover:text-[#f4f4f5]"
			@click="goBack">
			<span class="text-[1.1rem]">←</span>
			返回
		</button>

		<!-- 加载状态 -->
		<LoadingSpinner v-if="loading" size="large" text="加载详情中..." />

		<!-- 错误状态 -->
		<div v-else-if="error" class="text-center py-16 px-8">
			<div
				class="w-16 h-16 mx-auto mb-6 bg-[#ff6b6b]/10 rounded-full flex items-center justify-center text-2xl text-[#ff6b6b]">
				✕
			</div>
			<h2 class="text-xl text-[#f4f4f5] mb-2">
				加载失败
			</h2>
			<p class="text-[#71717a] mb-6">
				{{ error }}
			</p>
			<button
				class="inline-flex items-center gap-2 px-6 py-3.5 border-none rounded-[10px] text-[0.95rem] font-medium cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(255,107,107,0.3)]"
				@click="fetchMetadata">
				重试
			</button>
		</div>

		<!-- 详情内容 -->
		<template v-else-if="metadata">
			<!-- 头部信息 -->
			<div class="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-10 mb-12">
				<!-- 封面和状态按钮 -->
				<div class="flex flex-col gap-4">
					<div
						class="relative h-[310px] rounded-2xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.1)] flex justify-center items-center">
						<img :src="coverUrl" :alt="displayedTitle" class="h-full aspect-auto object-cover block" >
					</div>

					<!-- 收藏和观看按钮 -->
					<div class="flex justify-between gap-3">
						<button
							class="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl transition-all duration-200 hover:bg-white/5 border border-white/[0.08]"
							:class="metadata.is_favorite ? 'bg-[#ff6b6b]/10 border-[#ff6b6b]/30' : ''"
							:title="metadata.is_favorite ? '取消收藏' : '添加到收藏'"
							@click="toggleFavorite">
							<svg v-if="metadata.is_favorite" class="w-5 h-5 text-[#ff6b6b]" fill="currentColor" viewBox="0 0 24 24">
								<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
							</svg>
							<svg v-else class="w-5 h-5 text-[#71717a]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/>
							</svg>
							<span class="text-sm font-medium" :class="metadata.is_favorite ? 'text-[#ff6b6b]' : 'text-[#a1a1aa]'">
								{{ metadata.is_favorite ? '已收藏' : '收藏' }}
							</span>
						</button>

						<button
							class="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl transition-all duration-200 hover:bg-white/5 border border-white/[0.08]"
							:class="metadata.watched ? 'bg-[#10b981]/10 border-[#10b981]/30' : ''"
							:title="metadata.watched ? '标记为未观看' : '标记为已观看'"
							@click="toggleWatched">
							<svg v-if="metadata.watched" class="w-5 h-5 text-[#10b981]" fill="currentColor" viewBox="0 0 24 24">
								<path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
							</svg>
							<svg v-else class="w-5 h-5 text-[#71717a]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
							</svg>
							<span class="text-sm font-medium" :class="metadata.watched ? 'text-[#10b981]' : 'text-[#a1a1aa]'">
								{{ metadata.watched ? '已观看' : '标记观看' }}
							</span>
						</button>
					</div>
				</div>

				<!-- 右侧信息 -->
				<div class="flex flex-col justify-center">
					<!-- AVID 和状态 -->
					<div class="grid grid-cols-2 gap-4 mb-2.5">
						<div
							class="inline-block px-3.5 py-1.5 bg-[#ff6b6b]/15 rounded-md font-['JetBrains_Mono',monospace] text-[0.9rem] font-semibold text-[#ff6b6b] w-fit">
							{{ metadata.avid }}
						</div>
						<div class="inline-block px-3.5 py-1.5 bg-[#ff6b6b]/15 rounded-md font-['JetBrains_Mono',monospace] text-[0.9rem] font-semibold w-fit"
							:class="metadata.file_exists ? 'text-[#ff6b6b]' : 'text-[#ff9f43]'">
							{{ metadata.file_exists ? '已下载' : '未下载' }}
						</div>
					</div>

					<!-- 标题 -->
					<h1 class="text-[1.75rem] font-semibold text-[#f4f4f5] leading-[1.4] mb-6">
						{{ displayedTitle }}
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
						<button v-if="!metadata.file_exists"
							class="inline-flex items-center justify-center px-6 py-3.5 border-none rounded-[10px] text-[0.95rem] font-medium cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(255,107,107,0.3)] disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:translate-y-0"
							:disabled="downloading" @click="handleDownload">
							{{ downloading ? '提交中...' : '下载视频' }}
						</button>
						<button v-if="metadata.file_exists"
							class="inline-flex items-center gap-2 px-6 py-3.5 border-none rounded-[10px] text-[1.0rem] font-normal cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(255,107,107,0.3)]"
							@click="jumpPlay">
							<span class="text-[1.1rem]">▶</span>
							点击播放
						</button>

						<!-- 刷新按钮容器 -->
						<div class="relative" @click.stop>
							<button
								class="inline-flex items-center justify-center px-6 py-3.5 border-none rounded-[10px] text-[1.0rem] font-medium cursor-pointer transition-all duration-200 bg-white/[0.08] text-[#f4f4f5] border border-white/[0.08] hover:bg-white/[0.12] min-w-[120px] disabled:opacity-60 disabled:cursor-not-allowed"
								:disabled="refreshing" @click="showRefreshMenu = !showRefreshMenu">
								{{ refreshing ? '刷新中' : '刷新信息' }}
							</button>

							<!-- 刷新下拉菜单 -->
							<div v-if="showRefreshMenu && !refreshing"
								class="absolute bottom-[calc(100%+0.3rem)] left-0 bg-[rgba(18,18,28,0.95)] border border-white/[0.08] rounded-lg shadow-[0_4px_12px_rgba(0,0,0,0.2)] min-w-[120px] z-[80] overflow-hidden">
								<button v-for="option in refreshOptions" :key="option.text"
									class="w-full px-4 py-2.5 text-center bg-transparent border-none text-[#a1a1aa] text-[0.8rem] cursor-pointer transition-colors duration-200 hover:bg-white/[0.08] hover:text-[#f4f4f5]"
									@click="handleRefreshOption(option)">
									{{ option.text }}
								</button>
							</div>
						</div>

						<!-- 删除按钮容器 -->
						<div class="relative" @click.stop>
							<button
								class="inline-flex items-center justify-center px-6 py-3.5 border-none rounded-[10px] text-[0.95rem] font-medium cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ef476f] to-[#dc3558] text-white hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(239,71,111,0.3)] min-w-[120px]"
								@click="showDeleteMenu = !showDeleteMenu">
								删除数据
							</button>

							<!-- 删除下拉菜单 -->
							<div v-if="showDeleteMenu"
								class="absolute bottom-[calc(100%+0.3rem)] left-0 bg-[rgba(18,18,28,0.95)] border border-white/[0.08] rounded-lg shadow-[0_4px_12px_rgba(0,0,0,0.2)] min-w-[120px] z-[80] overflow-hidden">
								<button v-for="option in deleteOptions" :key="option.text"
									class="w-full px-4 py-2.5 text-center bg-transparent border-none text-[#ef476f] text-[0.8rem] cursor-pointer transition-colors duration-200 hover:bg-[#ef476f]/10 min-w-[120px]"
									@click="handleDeleteOption(option)">
									{{ option.text }}
								</button>
							</div>
						</div>
					</div>
				</div>
			</div>

			<!-- 详细信息区域 -->
			<div class="flex flex-col gap-8">
				<section
					v-if="metadata.director || metadata.studio || metadata.label || metadata.actors?.length || metadata.series || metadata.genres?.length"
					class="bg-[rgba(18,18,28,0.8)] rounded-2xl border border-white/[0.08] p-6">
					<h2 class="text-[1.1rem] font-semibold text-[#f4f4f5] mb-5 pb-3 border-b border-white/[0.08]">
						制作信息
					</h2>
					<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
						<div v-if="metadata.actors?.length" class="flex flex-col gap-1.5">
							<span class="text-[0.8rem] text-[#71717a]">演员</span>
							<div class="text-[0.95rem] text-[#f4f4f5] flex flex-wrap gap-2">
								<button
									v-for="(actor, index) in metadata.actors"
									:key="index"
									class="text-[#f4f4f5] hover:text-[#ff9f43] cursor-pointer transition-colors duration-200 bg-transparent border-none p-0 font-inherit"
									@click="navigateToActor(actor)"
								>
									{{ actor }}<span v-if="index < metadata.actors.length - 1" class="text-[#a1a1aa] ml-1">,</span>
								</button>
							</div>
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
						<div v-if="metadata.genres?.length" class="flex flex-col gap-1.5">
							<span class="text-[0.8rem] text-[#71717a]">类别</span>
							<div class="text-[0.95rem] text-[#f4f4f5] flex flex-wrap gap-2">
								<button
									v-for="(genre, index) in metadata.genres"
									:key="index"
									class="text-[#f4f4f5] hover:text-[#ff9f43] cursor-pointer transition-colors duration-200 bg-transparent border-none p-0 font-inherit"
									@click="navigateToGenre(genre)"
								>
									{{ genre }}<span v-if="index < metadata.genres.length - 1" class="text-[#a1a1aa] ml-1">,</span>
								</button>
							</div>
						</div>
					</div>
				</section>
			</div>
		</template>

		<!-- 确认对话框 -->
		<ConfirmDialog v-model:show="showConfirmDialog" :title="pendingDeleteAction?.title || '确认操作'"
			:message="pendingDeleteAction?.message || ''" :type="'danger'" confirm-text="确认删除" cancel-text="取消"
			@confirm="confirmDelete" @cancel="cancelDelete" />
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
