<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
	<div class="animate-[fadeIn_0.5s_ease] min-h-full flex flex-col relative overflow-hidden">
		<!-- Decorative Background Grid -->
		<div class="fixed inset-0 z-[-1] opacity-[0.03] pointer-events-none"
			style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 30px 30px;"/>

		<!-- Visual Shapes (Extended to full height) -->
		<div class="fixed inset-0 z-[-1] pointer-events-none opacity-60 overflow-hidden">
			<div
				class="absolute w-[500px] h-[500px] rounded-full opacity-40 blur-[80px] bg-[#ff6b6b] top-[-10%] right-[-5%]"/>
			<div
				class="absolute w-[400px] h-[400px] rounded-full opacity-40 blur-[80px] bg-[#ff9f43] top-[40%] right-[-10%]"/>
			<div
				class="absolute w-[600px] h-[600px] rounded-full opacity-40 blur-[80px] bg-[#4ecdc4] bottom-[-10%] right-[-5%]"/>
		</div>

		<!-- Hero Section -->
		<section class="relative z-10 py-20 px-4">
			<div class="relative max-w-7xl mx-auto">
				<div class="max-w-2xl">
					<h1 class="flex flex-col gap-3 mb-8">
						<span
							class="text-7xl font-bold bg-gradient-to-br from-[#ff6b6b] to-[#ff9f43] bg-clip-text text-transparent tracking-tight">NASSAV</span>
						<span class="text-3xl font-semibold text-[#a1a1aa] tracking-wide">视频资源管理系统</span>
					</h1>
					<p class="text-2xl text-[#aaaaaa] leading-relaxed mb-10 max-w-[500px]">
						打造您的私人影音库
						<br >
						<span class="text-xl opacity-90">高效管理 · 自动刮削 · 极速下载</span>
					</p>
					<div class="flex gap-5 flex-wrap">
						<RouterLink to="/add"
							class="inline-flex items-center gap-3 px-8 py-4 border-none rounded-xl text-lg font-medium no-underline cursor-pointer transition-all duration-300 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-[0_8px_20px_rgba(255,107,107,0.25)] hover:-translate-y-1 hover:shadow-[0_12px_25px_rgba(255,107,107,0.35)] active:translate-y-0 active:shadow-none">
							<span class="text-xl">⊕</span>
							添加资源
						</RouterLink>
						<RouterLink to="/resources"
							class="inline-flex items-center gap-3 px-8 py-4 border-none rounded-xl text-lg font-medium no-underline cursor-pointer transition-all duration-300 bg-white/[0.05] text-[#f4f4f5] border border-white/10 hover:bg-white/[0.1] hover:border-white/20 hover:-translate-y-1 backdrop-blur-sm">
							<span class="text-xl">▣</span>
							浏览资源库
						</RouterLink>
					</div>
				</div>
			</div>
		</section>

		<!-- Features Grid (Decorative) -->
		<section class="relative z-10 px-4 pb-20 max-w-7xl mx-auto w-full">
			<div class="grid grid-cols-1 md:grid-cols-3 gap-6">
				<!-- Card 1 -->
				<div
					class="p-8 rounded-2xl bg-white/[0.02] border border-white/[0.05] backdrop-blur-sm hover:bg-white/[0.04] transition-all duration-300 group hover:-translate-y-1">
					<div
						class="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500/10 to-indigo-500/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 border border-blue-500/10">
						<span class="text-3xl filter drop-shadow-lg">⚡</span>
					</div>
					<h3 class="text-xl font-semibold text-gray-200 mb-3">
						极速下载引擎
					</h3>
					<p class="text-gray-500 leading-relaxed text-sm">
						内置多线程下载器，支持断点续传与自动合并。智能队列管理，让资源获取更高效。
					</p>
				</div>

				<!-- Card 2 -->
				<div
					class="p-8 rounded-2xl bg-white/[0.02] border border-white/[0.05] backdrop-blur-sm hover:bg-white/[0.04] transition-all duration-300 group hover:-translate-y-1">
					<div
						class="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 border border-emerald-500/10">
						<span class="text-3xl filter drop-shadow-lg">🎯</span>
					</div>
					<h3 class="text-xl font-semibold text-gray-200 mb-3">
						智能元数据刮削
					</h3>
					<p class="text-gray-500 leading-relaxed text-sm">
						自动匹配影片信息，获取高清封面、演员阵容与标签分类。让您的媒体库井井有条。
					</p>
				</div>

				<!-- Card 3 -->
				<div
					class="p-8 rounded-2xl bg-white/[0.02] border border-white/[0.05] backdrop-blur-sm hover:bg-white/[0.04] transition-all duration-300 group hover:-translate-y-1">
					<div
						class="w-14 h-14 rounded-2xl bg-gradient-to-br from-orange-500/10 to-rose-500/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 border border-orange-500/10">
						<span class="text-3xl filter drop-shadow-lg">🎨</span>
					</div>
					<h3 class="text-xl font-semibold text-gray-200 mb-3">
						沉浸式体验
					</h3>
					<p class="text-gray-500 leading-relaxed text-sm">
						精心设计的现代化 UI，流畅的交互动画。支持深色模式，提供舒适的视觉享受。
					</p>
				</div>
			</div>
		</section>
	</div>
</template>

<style scoped>
@keyframes fadeIn {
	from {
		opacity: 0;
		transform: translateY(10px);
	}

	to {
		opacity: 1;
		transform: translateY(0);
	}
}
</style>
