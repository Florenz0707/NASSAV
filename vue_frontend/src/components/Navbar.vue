<script setup>
import {RouterLink, useRoute} from 'vue-router'

const route = useRoute()

const navItems = [
	{path: '/', name: '首页', icon: '◈'},
	{path: '/resources', name: '资源库', icon: '▣'},
	{path: '/add', name: '添加资源', icon: '⊕'},
	{path: '/downloads', name: '下载管理', icon: '⬇'}
]

const isActive = (path) => {
	if (path === '/') return route.path === '/'
	return route.path.startsWith(path)
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
				<RouterLink
					v-for="item in navItems"
					:key="item.path"
					:to="item.path"
					class="flex items-center gap-2 py-2.5 px-4 rounded-lg no-underline text-[#a1a1aa] text-sm font-medium transition-all duration-200 hover:text-[#f4f4f5] hover:bg-white/5"
					:class="{ 'text-[#ff6b6b] bg-[#ff6b6b]/10': isActive(item.path) }"
				>
					<span class="text-base"
						  :class="{ 'opacity-100': isActive(item.path), 'opacity-80': !isActive(item.path) }">{{
							item.icon
						}}</span>
					<span class="hidden md:inline">{{ item.name }}</span>
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
