<script setup>
import {onMounted, computed, ref, watch, onBeforeUnmount} from 'vue'
import {useResourceStore} from '../stores/resource'
import {RouterLink} from 'vue-router'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import { resourceApi } from '../api'

const resourceStore = useResourceStore()

onMounted(async () => {
	await resourceStore.fetchResources()
	await resourceStore.fetchDownloads()
})

const recentResources = computed(() => {
	const raw = resourceStore.resources && resourceStore.resources.value !== undefined ? resourceStore.resources.value : resourceStore.resources
	const arr = Array.isArray(raw) ? raw : []
	return arr.slice(0, 6)
})

// cover object URLs map: { [avid]: string }
const coverMap = ref({})

// track created blob URLs so we can revoke them
const createdBlobUrls = new Set()

// single shared IntersectionObserver for list lazy-loading
let observer = null
function ensureObserver() {
	if (observer) return observer
	observer = new IntersectionObserver(async (entries) => {
		for (const ent of entries) {
			if (!ent.isIntersecting) continue
			const avid = ent.target.dataset?.avid
			if (!avid) {
				observer.unobserve(ent.target)
				continue
			}
			// if already loaded, just unobserve
			if (coverMap.value[avid]) {
				observer.unobserve(ent.target)
				continue
			}
			try {
				const obj = await resourceApi.getCoverObjectUrl(avid)
				coverMap.value = { ...coverMap.value, [avid]: obj }
				if (typeof obj === 'string' && obj.startsWith('blob:')) createdBlobUrls.add(obj)
			} catch (e) {
				coverMap.value = { ...coverMap.value, [avid]: resourceApi.getCoverUrl(avid) }
			}
			observer.unobserve(ent.target)
		}
	}, { rootMargin: '200px' })
	return observer
}

function registerObserver(el, avid) {
	if (!el) return
	el.dataset.avid = avid
	ensureObserver().observe(el)
}

onBeforeUnmount(() => {
	if (observer) {
		observer.disconnect()
		observer = null
	}
	for (const url of createdBlobUrls) try { URL.revokeObjectURL(url) } catch (e) {}
	createdBlobUrls.clear()
})
</script>

<template>
	<div class="animate-[fadeIn_0.5s_ease]">
		<!-- Hero Section -->
		<section class="relative py-16 mb-12 overflow-hidden">
			<div class="relative z-10">
				<h1 class="flex flex-col gap-2 mb-6">
					<span class="text-6xl font-bold bg-gradient-to-br from-[#ff6b6b] to-[#ff9f43] bg-clip-text text-transparent tracking-wider">NASSAV</span>
					<span class="text-2xl font-normal text-[#a1a1aa]">视频资源管理系统</span>
				</h1>
				<p class="text-lg text-[#71717a] max-w-[500px] leading-relaxed mb-8">
					高效管理您的视频资源，支持多下载源、自动刮削元数据
				</p>
				<div class="flex gap-4 flex-wrap">
					<RouterLink
						to="/add"
						class="inline-flex items-center gap-2 px-8 py-4 border-none rounded-[10px] text-base font-medium no-underline cursor-pointer transition-all duration-200 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-[0_4px_15px_rgba(255,107,107,0.3)] hover:-translate-y-0.5 hover:shadow-[0_6px_20px_rgba(255,107,107,0.4)]"
					>
						<span class="text-[1.2rem]">⊕</span>
						添加资源
					</RouterLink>
					<RouterLink
						to="/resources"
						class="inline-flex items-center gap-2 px-8 py-4 border-none rounded-[10px] text-base font-medium no-underline cursor-pointer transition-all duration-200 bg-white/[0.08] text-[#f4f4f5] border border-white/10 hover:bg-white/[0.12] hover:border-white/20"
					>
						<span class="text-[1.2rem]">▣</span>
						浏览资源库
					</RouterLink>
				</div>
			</div>

			<!-- Visual Shapes -->
			<div class="absolute right-0 top-1/2 -translate-y-1/2 w-[400px] h-[400px] pointer-events-none hidden md:block">
				<div class="absolute w-[300px] h-[300px] rounded-full opacity-50 blur-[60px] bg-[#ff6b6b] top-0 right-0 animate-[float1_8s_ease-in-out_infinite]"></div>
				<div class="absolute w-[200px] h-[200px] rounded-full opacity-50 blur-[60px] bg-[#ff9f43] bottom-[20%] right-[20%] animate-[float2_6s_ease-in-out_infinite]"></div>
				<div class="absolute w-[150px] h-[150px] rounded-full opacity-50 blur-[60px] bg-[#4ecdc4] top-[30%] right-[30%] animate-[float3_7s_ease-in-out_infinite]"></div>
			</div>
		</section>

		<!-- Stats Section -->
		<section class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-6 mb-12">
			<div class="flex items-center gap-4 p-6 bg-[rgba(18,18,28,0.8)] rounded-2xl border border-white/[0.08] transition-all duration-300 hover:-translate-y-0.5 hover:border-white/15">
				<div class="w-12 h-12 flex items-center justify-center bg-[#ff6b6b]/10 rounded-xl text-xl text-[#ff6b6b]">▣</div>
				<div>
					<div class="text-[2rem] font-bold text-[#f4f4f5] font-['JetBrains_Mono',monospace]">{{ resourceStore.stats.total }}</div>
					<div class="text-sm text-[#71717a]">总资源数</div>
				</div>
			</div>
			<div class="flex items-center gap-4 p-6 bg-[rgba(18,18,28,0.8)] rounded-2xl border border-white/[0.08] transition-all duration-300 hover:-translate-y-0.5 hover:border-white/15">
				<div class="w-12 h-12 flex items-center justify-center bg-[#2ed573]/10 rounded-xl text-xl text-[#2ed573]">✓</div>
				<div>
					<div class="text-[2rem] font-bold text-[#f4f4f5] font-['JetBrains_Mono',monospace]">{{ resourceStore.stats.downloaded }}</div>
					<div class="text-sm text-[#71717a]">已下载</div>
				</div>
			</div>
			<div class="flex items-center gap-4 p-6 bg-[rgba(18,18,28,0.8)] rounded-2xl border border-white/[0.08] transition-all duration-300 hover:-translate-y-0.5 hover:border-white/15">
				<div class="w-12 h-12 flex items-center justify-center bg-[#ffc107]/10 rounded-xl text-xl text-[#ffc107]">◷</div>
				<div>
					<div class="text-[2rem] font-bold text-[#f4f4f5] font-['JetBrains_Mono',monospace]">{{ resourceStore.stats.pending }}</div>
					<div class="text-sm text-[#71717a]">待下载</div>
				</div>
			</div>
		</section>

		<LoadingSpinner v-if="resourceStore.loading" text="加载中..."/>
	</div>
</template>

<style scoped>
/* 自定义动画 */
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

@keyframes float1 {
	0%, 100% { transform: translate(0, 0); }
	50% { transform: translate(-20px, 20px); }
}

@keyframes float2 {
	0%, 100% { transform: translate(0, 0); }
	50% { transform: translate(15px, -15px); }
}

@keyframes float3 {
	0%, 100% { transform: translate(0, 0); }
	50% { transform: translate(-10px, -20px); }
}
</style>
