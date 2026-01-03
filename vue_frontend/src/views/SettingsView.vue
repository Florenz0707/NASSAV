<script setup>
import { ref, onMounted } from 'vue'
import { sourceApi } from '../api'
import { useToastStore } from '../stores/toast'
import { useSettingsStore } from '../stores/settings'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const toastStore = useToastStore()
const settingsStore = useSettingsStore()

// 当前选中的设置菜单项
const activeMenu = ref('general')

// 设置菜单项
const menuItems = [
	{ id: 'general', name: '通用设置', icon: '⚙️' },
	{ id: 'cookies', name: 'Cookie 管理', icon: '🍪' }
]

// 下载源列表数据
const sources = ref([])
const loading = ref(true)

// 弹窗状态
const showViewModal = ref(false)
const showEditModal = ref(false)
const showDeleteConfirm = ref(false)
const currentSource = ref(null)
const editCookieValue = ref('')
const viewCookieValue = ref('')

// 选择菜单项
const selectMenu = (menuId) => {
	activeMenu.value = menuId
}

// 格式化时间
const formatTime = (isoString) => {
	if (!isoString) return null
	try {
		const date = new Date(isoString)
		return date.toLocaleString('zh-CN', {
			year: 'numeric',
			month: '2-digit',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
			hour12: false
		}).replace(/\//g, '-')
	} catch (_e) {
		return isoString
	}
}

// 加载数据
const loadData = async () => {
	loading.value = true
	try {
		// 1. 获取所有可用源列表
		const sourcesResponse = await sourceApi.getList()
		const availableSources = sourcesResponse.data || []

		// 2. 获取已设置的 Cookie 列表
		const cookiesResponse = await sourceApi.getCookies()
		const cookieData = cookiesResponse.data || []

		// 3. 构建 Cookie 映射表（source -> cookie info）
		const cookieMap = {}
		cookieData.forEach(item => {
			cookieMap[item.source] = {
				cookie: item.cookie,
				mtime: item.mtime
			}
		})

		// 4. 合并数据
		sources.value = availableSources.map(sourceName => {
			const cookieInfo = cookieMap[sourceName]
			return {
				name: sourceName,
				hasCookie: !!cookieInfo,
				lastUpdate: cookieInfo ? formatTime(cookieInfo.mtime) : null,
				cookie: cookieInfo ? cookieInfo.cookie : null
			}
		})
	} catch (err) {
		console.error('加载 Cookie 数据失败:', err)
		toastStore.error(err.message || '加载数据失败')
	} finally {
		loading.value = false
	}
}

// 查看 Cookie
const viewCookie = (source) => {
	currentSource.value = source
	viewCookieValue.value = source.cookie || ''
	showViewModal.value = true
}

// 打开编辑弹窗
const openEditModal = (source) => {
	currentSource.value = source
	editCookieValue.value = source.cookie || ''
	showEditModal.value = true
}

// 保存 Cookie
const saveCookie = async () => {
	if (!currentSource.value) return
	try {
		await sourceApi.setCookie({
			source: currentSource.value.name,
			cookie: editCookieValue.value
		})
		toastStore.success('Cookie 设置成功')
		showEditModal.value = false
		loadData()
	} catch (err) {
		toastStore.error(err.message || '设置失败')
	}
}

// 自动获取 Cookie
const autoFetchCookie = async (source) => {
	const targetSource = source || currentSource.value
	if (!targetSource) return

	try {
		await sourceApi.setCookie({
			source: targetSource.name,
			auto: true
		})
		toastStore.success('已触发自动获取 Cookie')
		showEditModal.value = false
		loadData()
	} catch (err) {
		toastStore.error(err.message || '自动获取失败')
	}
}

// 确认删除
const confirmDelete = (source) => {
	currentSource.value = source
	showDeleteConfirm.value = true
}

// 执行删除
const handleDelete = async () => {
	if (!currentSource.value) return
	try {
		await sourceApi.deleteCookie(currentSource.value.name)
		toastStore.success('Cookie 已清除')
		loadData()
	} catch (err) {
		toastStore.error(err.message || '清除失败')
	}
}

// 组件挂载时加载数据
onMounted(() => {
	loadData()
})
</script>

<template>
	<div class="settings-page">
		<!-- Header -->
		<div class="mb-8">
			<h1 class="text-[2rem] font-bold text-[#f4f4f5] mb-2">
				系统设置
			</h1>
			<p class="text-[#71717a] text-base">
				配置系统参数和管理 Cookie
			</p>
		</div>

		<!-- Main Content: Left Menu + Right Panel -->
		<div class="flex gap-6">
			<!-- Left Sidebar Menu -->
			<div class="w-64 flex-shrink-0">
				<div class="bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl p-2">
					<div
						v-for="item in menuItems"
						:key="item.id"
						class="flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-all duration-200"
						:class="{
							'bg-[#ff6b6b]/10 text-[#ff6b6b]': activeMenu === item.id,
							'text-[#a1a1aa] hover:text-[#f4f4f5] hover:bg-white/5': activeMenu !== item.id
						}"
						@click="selectMenu(item.id)"
					>
						<span class="text-xl">{{ item.icon }}</span>
						<span class="font-medium">{{ item.name }}</span>
					</div>
				</div>
			</div>

			<!-- Right Content Panel -->
			<div class="flex-1">
				<div class="bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl p-6">
					<!-- Cookie 管理面板 -->
					<div v-if="activeMenu === 'cookies'">
						<div class="mb-6">
							<h2 class="text-xl font-semibold text-[#f4f4f5] mb-2">
								Cookie 管理
							</h2>
							<p class="text-sm text-[#71717a]">
								管理各个下载源的 Cookie 配置，确保正常访问
							</p>
						</div>

						<!-- 加载状态 -->
						<div v-if="loading" class="text-center py-12">
							<div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[#ff6b6b]" />
							<p class="mt-3 text-[#71717a]">
								加载中...
							</p>
						</div>

						<!-- Cookie 列表表格 -->
						<div v-else-if="sources.length > 0" class="overflow-x-auto">
							<table class="w-full">
								<thead>
									<tr class="border-b border-white/[0.08]">
										<th class="text-left py-3 px-4 text-sm font-semibold text-[#a1a1aa]">
											下载源
										</th>
										<th class="text-left py-3 px-4 text-sm font-semibold text-[#a1a1aa]">
											Cookie 状态
										</th>
										<th class="text-left py-3 px-4 text-sm font-semibold text-[#a1a1aa]">
											更新时间
										</th>
										<th class="text-left py-3 px-4 text-sm font-semibold text-[#a1a1aa]">
											操作
										</th>
									</tr>
								</thead>
								<tbody>
									<tr
										v-for="source in sources"
										:key="source.name"
										class="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors"
									>
										<td class="py-4 px-4 text-[#f4f4f5] font-medium">
											{{ source.name }}
										</td>
										<td class="py-4 px-4">
											<span
												v-if="source.hasCookie"
												class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-green-500/10 text-green-400 text-sm"
											>
												<span>✓</span>
												<span>已设置</span>
											</span>
											<span
												v-else
												class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/10 text-red-400 text-sm"
											>
												<span>✗</span>
												<span>未设置</span>
											</span>
										</td>
										<td class="py-4 px-4 text-sm text-[#71717a]">
											{{ source.lastUpdate || '-' }}
										</td>
										<td class="py-4 px-4">
											<div class="flex gap-2">
												<button
													class="px-3 py-1.5 rounded-lg text-sm border transition-all"
													:class="[
														source.hasCookie
															? 'bg-white/5 text-[#a1a1aa] border-white/[0.08] hover:bg-white/10 hover:text-[#f4f4f5]'
															: 'bg-white/5 text-[#71717a] border-white/[0.04] cursor-not-allowed opacity-50'
													]"
													:disabled="!source.hasCookie"
													@click="viewCookie(source)"
												>
													查看
												</button>
												<button
													class="px-3 py-1.5 rounded-lg bg-[#ff6b6b]/10 text-[#ff6b6b] border-[#ff6b6b]/20 hover:bg-[#ff6b6b]/20 transition-all text-sm"
													@click="openEditModal(source)"
												>
													更新
												</button>
												<button
													class="px-3 py-1.5 rounded-lg bg-white/5 text-red-400 border border-white/[0.08] hover:bg-red-500/10 hover:border-red-500/20 transition-all text-sm"
													@click="confirmDelete(source)"
												>
													删除
												</button>
											</div>
										</td>
									</tr>
								</tbody>
							</table>
						</div>

						<!-- 空状态提示 -->
						<div v-else class="text-center py-12 text-[#71717a]">
							<div class="text-4xl mb-3">
								📭
							</div>
							<p>
								暂无可用的下载源
							</p>
						</div>

						<!-- 提示信息 -->
						<div v-if="sources.length > 0" class="mt-6 p-4 rounded-lg bg-[#4ecdc4]/5 border border-[#4ecdc4]/20">
							<div class="flex gap-3">
								<span class="text-[#4ecdc4] text-lg flex-shrink-0">ℹ️</span>
								<div class="text-sm text-[#a1a1aa]">
									<p class="mb-2">
										<span class="text-[#f4f4f5] font-medium">关于 Cookie：</span>
									</p>
									<ul class="list-disc list-inside space-y-1 text-[#71717a]">
										<li>Cookie 用于访问需要登录的下载源（如 MissAV）</li>
										<li>可以手动设置 Cookie，也可以使用"自动获取"功能</li>
										<li>Cookie 会定期失效，建议定期更新</li>
									</ul>
								</div>
							</div>
						</div>
					</div>

					<!-- 通用设置面板 -->
					<div v-else-if="activeMenu === 'general'">
						<div class="mb-6">
							<h2 class="text-xl font-semibold text-[#f4f4f5] mb-2">
								通用设置
							</h2>
							<p class="text-sm text-[#71717a]">
								配置系统的通用参数
							</p>
						</div>

						<div class="space-y-6">
							<!-- 显示设置 -->
							<div class="p-4 rounded-xl bg-white/[0.02] border border-white/[0.05]">
								<h3 class="text-sm font-medium text-[#a1a1aa] mb-4 uppercase tracking-wider">
									显示设置
								</h3>
								<div class="space-y-4">
									<!-- 女优头像开关 -->
									<div class="flex items-center justify-between">
										<div>
											<div class="text-[#f4f4f5] font-medium">
												显示女优头像
											</div>
											<div class="text-sm text-[#71717a]">
												在列表和详情页中渲染女优头像图片
											</div>
										</div>
										<button
											class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none"
											:class="settingsStore.showActorAvatar ? 'bg-[#ff6b6b]' : 'bg-[#27272a]'"
											@click="settingsStore.showActorAvatar = !settingsStore.showActorAvatar"
										>
											<span
												class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
												:class="settingsStore.showActorAvatar ? 'translate-x-6' : 'translate-x-1'"
											/>
										</button>
									</div>

									<!-- 标题显示字段 -->
									<div class="flex items-center justify-between pt-4 border-t border-white/[0.05]">
										<div>
											<div class="text-[#f4f4f5] font-medium">
												标题显示字段
											</div>
											<div class="text-sm text-[#71717a]">
												选择在资源列表中显示的标题类型
											</div>
										</div>
										<select
											v-model="settingsStore.displayTitle"
											class="px-4 py-2 bg-[#18181b] border border-white/10 rounded-lg text-[#f4f4f5] text-sm focus:outline-none focus:border-[#ff6b6b]/50 transition-all cursor-pointer"
										>
											<option value="translated_title">
												翻译标题
											</option>
											<option value="source_title">
												源站标题
											</option>
											<option value="original_title">
												原始标题
											</option>
										</select>
									</div>
								</div>
							</div>

							<!-- 更多设置占位 -->
							<div class="text-center py-8 text-[#71717a] border border-dashed border-white/10 rounded-xl">
								<p>更多设置项正在开发中...</p>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- 查看 Cookie 弹窗 -->
		<div v-if="showViewModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
			<div class="bg-[#18181b] border border-white/10 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl">
				<div class="p-6 border-b border-white/5 flex justify-between items-center">
					<h3 class="text-xl font-bold text-[#f4f4f5]">
						查看 Cookie - {{ currentSource?.name }}
					</h3>
					<button class="text-[#71717a] hover:text-[#f4f4f5]" @click="showViewModal = false">
						✕
					</button>
				</div>
				<div class="p-6">
					<div class="bg-black/40 rounded-xl p-4 font-mono text-sm text-[#a1a1aa] break-all max-h-[400px] overflow-y-auto border border-white/5">
						{{ viewCookieValue || '无内容' }}
					</div>
				</div>
				<div class="p-6 border-t border-white/5 flex justify-end">
					<button
						class="px-6 py-2 rounded-xl bg-white/5 text-[#f4f4f5] font-medium hover:bg-white/10 transition-all"
						@click="showViewModal = false"
					>
						关闭
					</button>
				</div>
			</div>
		</div>

		<!-- 编辑 Cookie 弹窗 -->
		<div v-if="showEditModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
			<div class="bg-[#18181b] border border-white/10 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl">
				<div class="p-6 border-b border-white/5 flex justify-between items-center">
					<h3 class="text-xl font-bold text-[#f4f4f5]">
						设置 Cookie - {{ currentSource?.name }}
					</h3>
					<button class="text-[#71717a] hover:text-[#f4f4f5]" @click="showEditModal = false">
						✕
					</button>
				</div>
				<div class="p-6">
					<p class="text-sm text-[#71717a] mb-4">
						请输入从浏览器获取的 Cookie 字符串。通常包含 PHPSESSID 等字段。
					</p>
					<textarea
						v-model="editCookieValue"
						class="w-full h-48 bg-black/40 border border-white/10 rounded-xl p-4 text-[#f4f4f5] font-mono text-sm focus:outline-none focus:border-[#ff6b6b]/50 transition-all resize-none"
						placeholder="粘贴 Cookie 字符串到这里..."
					/>
				</div>
				<div class="p-6 border-t border-white/5 flex justify-between items-center">
					<button
						class="px-4 py-2 rounded-xl bg-white/5 text-[#a1a1aa] text-sm border border-white/[0.08] hover:bg-white/10 hover:text-[#f4f4f5] transition-all"
						@click="autoFetchCookie()"
					>
						✨ 自动获取
					</button>
					<div class="flex gap-3">
						<button
							class="px-6 py-2 rounded-xl bg-white/5 text-[#f4f4f5] font-medium hover:bg-white/10 transition-all"
							@click="showEditModal = false"
						>
							取消
						</button>
						<button
							class="px-6 py-2 rounded-xl bg-[#ff6b6b] text-white font-medium hover:bg-[#ff5252] transition-all shadow-lg shadow-[#ff6b6b]/20"
							@click="saveCookie"
						>
							保存设置
						</button>
					</div>
				</div>
			</div>
		</div>

		<!-- 删除确认 -->
		<ConfirmDialog
			v-model:show="showDeleteConfirm"
			title="清除 Cookie"
			:message="`确定要清除 ${currentSource?.name} 的 Cookie 吗？清除后可能无法正常访问该源。`"
			confirm-text="确定清除"
			type="danger"
			@confirm="handleDelete"
		/>
	</div>
</template>

<style scoped>
.settings-page {
	animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
	from {
		opacity: 0;
		transform: translateY(20px);
	}
	to {
		opacity: 1;
		transform: translateY(0);
	}
}

/* 响应式布局 */
@media (max-width: 768px) {
	.flex {
		flex-direction: column;
	}

	.w-64 {
		width: 100%;
	}
}
</style>
