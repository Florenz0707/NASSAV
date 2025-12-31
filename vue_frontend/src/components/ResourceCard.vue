<script setup>
import {computed, ref, onMounted, onUnmounted, nextTick} from 'vue'
import {resourceApi, downloadApi} from '../api'
import {useToastStore} from '../stores/toast'
import {RouterLink} from 'vue-router'
import ConfirmDialog from './ConfirmDialog.vue'

const props = defineProps({
	resource: {
		type: Object,
		required: true
	}
	,
	selectable: {
		type: Boolean,
		default: false
	},
	selected: {
		type: Boolean,
		default: false
	}
})

const emit = defineEmits(['download', 'refresh', 'delete', 'deleteFile', 'toggle-select'])
// add toggle-select event if selectable
if (typeof emit === 'function') {
	// nothing, emit already available
}

const placeholder = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='
const coverUrl = ref(placeholder)
let observer = null
let imgEl = null

async function loadCover() {
	try {
		const obj = await resourceApi.getCoverObjectUrl(props.resource.avid)
		if (obj) coverUrl.value = obj
	} catch (e) {
		coverUrl.value = resourceApi.getCoverUrl(props.resource.avid)
	}
}

function ensureObserver() {
	if (observer) return observer
	observer = new IntersectionObserver((entries) => {
		for (const ent of entries) {
			if (ent.isIntersecting) {
				loadCover()
				if (imgEl) observer.unobserve(imgEl)
			}
		}
	}, { rootMargin: '200px' })
	return observer
}
const statusClass = computed(() => ({
	downloaded: props.resource.has_video,
	pending: !props.resource.has_video
}))

const toastStore = useToastStore()
const showDeleteMenu = ref(false)
const showConfirmDialog = ref(false)
const pendingDeleteOption = ref(null)

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

function handleDeleteOption(option) {
	pendingDeleteOption.value = option
	showConfirmDialog.value = true
	showDeleteMenu.value = false
}

// 确认删除操作
async function confirmDelete() {
	const option = pendingDeleteOption.value
	if (!option) return

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
	} catch (err) {
		toastStore.error(err.message || `删除${option.action === 'deleteFile' ? '视频' : '资源'}失败`)
	} finally {
		pendingDeleteOption.value = null
	}
}

// 取消删除操作
function cancelDelete() {
	pendingDeleteOption.value = null
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
	// wait for DOM
	nextTick(() => {
		imgEl = document.querySelector(`img[data-avid="${props.resource.avid}"]`)
		if (imgEl) ensureObserver().observe(imgEl)
	})
})
onUnmounted(() => {
	document.removeEventListener('click', closeMenuOnOutsideClick)
	if (observer && imgEl) observer.unobserve(imgEl)
})
</script>

<template>
	<div
		class="relative bg-[rgba(18,18,28,0.8)] rounded-2xl overflow-hidden border border-white/[0.08] transition-all duration-300 hover:-translate-y-1 hover:border-[rgba(255,107,107,0.3)] hover:shadow-[0_12px_40px_rgba(0,0,0,0.3)]"
		:class="statusClass"
	>
		<!-- 选择复选框（可选） -> 放到封面内以保证可见性 -->
		<!-- 封面图 -->
		<div class="relative aspect-video overflow-hidden bg-black/30 group">
			<!-- checkbox placed over cover for visibility -->
			<template v-if="selectable">
				<label class="absolute z-30 top-3 left-3 inline-flex items-center cursor-pointer" aria-label="选择资源">
					<input
						type="checkbox"
						class="sr-only"
						:checked="selected"
						@change.stop="$emit('toggle-select', resource.avid, $event.target.checked)"
					/>
					<span :class="['w-6 h-6 flex items-center justify-center rounded-md transition border-2', selected ? 'bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] border-white shadow-lg' : 'bg-[rgba(128,128,128,0.6)] border-white text-white']">
						<svg v-if="selected" class="w-3 h-3 text-white" viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
							<path fill-rule="evenodd" clip-rule="evenodd" d="M16.707 5.293a1 1 0 00-1.414-1.414L7 12.172l-2.293-2.293A1 1 0 003.293 11.293l3 3a1 1 0 001.414 0l9-9z" />
						</svg>
					</span>
				</label>
			</template>
			<img
				:data-avid="resource.avid"
				:src="coverUrl"
				:alt="resource.title"
				loading="lazy"
				class="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
			/>
			<div class="absolute inset-0 bg-black/60 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300">
				<RouterLink
					:to="`/resource/${resource.avid}`"
					class="px-6 py-3 bg-[#ff6b6b] text-white rounded-lg font-medium text-sm transition-transform hover:scale-105"
				>
					查看详情
				</RouterLink>
			</div>
		</div>

		<!-- 卡片内容 -->
		<div class="p-5 relative">
			<!-- 元数据头部 -->
			<div class="flex gap-4 mb-2.5 items-center">
				<div class="font-['JetBrains_Mono',monospace] text-[0.85rem] text-[#ff6b6b] font-semibold bg-[#ff6b6b]/15 rounded-md w-fit px-2 py-1">
					{{ resource.avid }}
				</div>
				<div
					class="font-['JetBrains_Mono',monospace] text-[0.85rem] font-semibold rounded-md w-fit px-2 py-1"
					:class="resource.has_video ? 'text-[#ff6b6b] bg-[#ff6b6b]/15' : 'text-[#ff9f43] bg-[#ff6b6b]/15'"
				>
					{{ resource.has_video ? '已下载' : '未下载' }}
				</div>
			</div>

			<!-- 标题 -->
			<h3
				class="text-base font-medium text-[#f4f4f5] leading-[1.4] mb-3 line-clamp-2 min-h-[2.8em]"
				:title="resource.title"
			>
				{{ resource.title }}
			</h3>

			<!-- 元信息 -->
			<div class="flex flex-wrap gap-8 mb-4">
				<span class="flex items-center gap-1.5 text-[0.8rem] text-[#71717a]">
					<span class="text-[0.7rem] opacity-70">◉</span>
					{{ resource.source }}
				</span>
				<span
					v-if="resource.release_date"
					class="flex items-center gap-1.5 text-[0.8rem] text-[#71717a]"
				>
					<span class="text-[0.7rem] opacity-70">◷</span>
					{{ resource.release_date }}
				</span>
			</div>

			<!-- 操作按钮 -->
			<div class="flex gap-2 justify-between items-center relative">
				<button
					class="inline-flex items-center justify-center px-3.5 py-2 rounded-lg text-[0.9rem] font-medium cursor-pointer transition-all duration-200 bg-white/[0.08] text-[#a1a1aa] hover:bg-white/[0.12] hover:text-[#f4f4f5]"
					@click="emit('refresh', resource.avid)"
				>
					刷新
				</button>

				<button
					v-if="!resource.has_video"
					class="inline-flex items-center justify-center px-3.5 py-2 rounded-lg text-[0.9rem] font-medium cursor-pointer transition-all duration-200 bg-[#ff6b6b] text-white hover:bg-[#ff5252] hover:-translate-y-0.5"
					@click="emit('download', resource.avid)"
				>
					下载
				</button>

				<!-- 删除按钮容器 -->
				<div class="relative" @click.stop>
					<button
						class="inline-flex items-center justify-center px-3.5 py-2 rounded-lg text-[0.9rem] font-medium cursor-pointer transition-all duration-200 bg-[#ef476f]/10 text-[#ef476f] border border-[#ef476f]/20 hover:bg-[#ef476f]/20 hover:text-[#ff5252]"
						:data-avid="resource.avid"
						@click="showDeleteMenu = !showDeleteMenu"
						title="删除"
					>
						删除
					</button>

					<!-- 下拉菜单 -->
					<div
						v-if="showDeleteMenu"
						:data-avid="resource.avid"
						class="absolute bottom-[calc(100%+0.5rem)] right-0 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-lg shadow-[0_4px_12px_rgba(0,0,0,0.2)] min-w-[85px] z-[100] overflow-hidden max-h-[calc(100vh-20px)] overflow-y-auto"
					>
						<button
							v-for="option in deleteOptions"
							:key="option.action"
							class="w-full px-4 py-2.5 text-center bg-[#ef476f]/20 border-none text-[#ef476f] text-[0.8rem] cursor-pointer transition-colors duration-200 hover:bg-[#ef476f]/10"
							@click="handleDeleteOption(option)"
						>
							{{ option.text }}
						</button>
					</div>
				</div>
			</div>
		</div>

		<!-- 确认对话框 -->
		<ConfirmDialog
			v-model:show="showConfirmDialog"
			:title="pendingDeleteOption?.action === 'deleteFile' ? '删除视频文件' : '删除资源'"
			:message="pendingDeleteOption?.confirm || ''"
			:type="'danger'"
			confirm-text="确认删除"
			cancel-text="取消"
			@confirm="confirmDelete"
			@cancel="cancelDelete"
		/>
	</div>
</template>

<style scoped>
/* 响应式调整 - 仅保留必要的媒体查询 */
@media (max-width: 480px) {
	.card-actions button span:not(:first-child) {
		display: none;
	}

	.card-actions button {
		padding: 0.5rem;
	}
}
</style>
