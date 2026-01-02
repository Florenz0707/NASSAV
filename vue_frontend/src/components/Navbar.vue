<script setup>
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const showResourcesMenu = ref(false)

// 资源库子菜单
const resourcesMenuItems = [
	{ path: '/resources', name: '全部资源', icon: '▣' },
	{ path: '/resources/actors', name: '按演员', icon: '⨀' },
	{ path: '/resources/genres', name: '按类别', icon: '⨀' }
]

const isActive = (path) => {
	if (path === '/') return route.path === '/'
	return route.path.startsWith(path)
}

const isResourcesActive = () => {
	return route.path.startsWith('/resources') || route.path.startsWith('/actors') || route.path.startsWith('/genres')
}

const goToResources = () => {
	router.push('/resources')
}
</script>

<template>
	<nav class="bg-[rgba(18,18,24,0.85)] backdrop-blur-xl border-b border-white/[0.06] sticky top-0 z-[100]">
		<div class="max-w-[1400px] mx-auto px-8 h-16 flex items-center justify-between">
			<RouterLink to="/"
				class="flex items-center gap-3 no-underline text-[#f4f4f5] font-semibold text-xl tracking-wide">
				<span
					class="w-9 h-9 bg-gradient-to-br from-[#ff6b6b] to-[#ff9f43] rounded-[10px] flex items-center justify-center text-base text-white shadow-[0_4px_12px_rgba(255,107,107,0.3)]">▶</span>
				<span class="bg-gradient-to-br from-[#ff6b6b] to-[#ff9f43] bg-clip-text text-transparent">NASSAV</span>
			</RouterLink>

			<div class="flex gap-2">
				<!-- 首页 -->
				<RouterLink to="/"
					class="flex items-center gap-2 py-2.5 px-4 rounded-lg no-underline text-[#a1a1aa] text-sm font-medium transition-all duration-200 hover:text-[#f4f4f5] hover:bg-white/5"
					:class="{ 'text-[#ff6b6b] bg-[#ff6b6b]/10': isActive('/') }">
					<span class="text-base"
						:class="{ 'opacity-100': isActive('/'), 'opacity-80': !isActive('/') }">◈</span>
					<span class="hidden md:inline">首页</span>
				</RouterLink>

				<!-- 资源库下拉菜单 -->
				<div class="relative" @mouseenter="showResourcesMenu = true" @mouseleave="showResourcesMenu = false">
					<button
						class="flex items-center gap-2 py-2.5 px-4 rounded-lg text-sm font-medium transition-all duration-200 hover:text-[#f4f4f5] hover:bg-white/5 cursor-pointer border-none bg-transparent"
						:class="{ 'text-[#ff6b6b] bg-[#ff6b6b]/10': isResourcesActive(), 'text-[#a1a1aa]': !isResourcesActive() }"
						@click="goToResources">
						<span class="text-base"
							:class="{ 'opacity-100': isResourcesActive(), 'opacity-80': !isResourcesActive() }">▣</span>
						<span class="hidden md:inline">资源库</span>
						<span class="text-xs opacity-60">▼</span>
					</button>

					<!-- 下拉菜单 -->
					<div v-if="showResourcesMenu" class="absolute top-full left-0 pt-1 -mt-1">
						<div
							class="bg-[rgba(18,18,24,0.95)] backdrop-blur-xl border border-white/[0.08] rounded-lg shadow-[0_8px_24px_rgba(0,0,0,0.4)] min-w-[120px] overflow-hidden">
							<RouterLink v-for="item in resourcesMenuItems" :key="item.path" :to="item.path"
								class="flex items-center gap-3 py-2.5 px-4 no-underline text-[#a1a1aa] text-sm font-medium transition-all duration-200 hover:text-[#f4f4f5] hover:bg-white/5"
								:class="{ 'text-[#ff6b6b] bg-[#ff6b6b]/10': isActive(item.path) }">
								<span class="text-base">{{ item.icon }}</span>
								<span>{{ item.name }}</span>
							</RouterLink>
						</div>
					</div>
				</div>

				<!-- 添加资源 -->
				<RouterLink to="/add"
					class="flex items-center gap-2 py-2.5 px-4 rounded-lg no-underline text-[#a1a1aa] text-sm font-medium transition-all duration-200 hover:text-[#f4f4f5] hover:bg-white/5"
					:class="{ 'text-[#ff6b6b] bg-[#ff6b6b]/10': isActive('/add') }">
					<span class="text-base"
						:class="{ 'opacity-100': isActive('/add'), 'opacity-80': !isActive('/add') }">⊕</span>
					<span class="hidden md:inline">添加资源</span>
				</RouterLink>

				<!-- 下载管理 -->
				<RouterLink to="/downloads"
					class="flex items-center gap-2 py-2.5 px-4 rounded-lg no-underline text-[#a1a1aa] text-sm font-medium transition-all duration-200 hover:text-[#f4f4f5] hover:bg-white/5"
					:class="{ 'text-[#ff6b6b] bg-[#ff6b6b]/10': isActive('/downloads') }">
					<span class="text-base"
						:class="{ 'opacity-100': isActive('/downloads'), 'opacity-80': !isActive('/downloads') }">⬇</span>
					<span class="hidden md:inline">下载管理</span>
				</RouterLink>
			</div>
		</div>
	</nav>
</template>

<style scoped>
/* 仅保留必要的响应式样式 */
@media (max-width: 768px) {
	.navbar-inner {
		padding: 0 1rem;
	}
}
</style>
