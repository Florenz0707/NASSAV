<template>
	<div class="genres-page">
		<div class="mb-8">
			<h1 class="text-[2rem] font-bold text-[#f4f4f5] mb-2">类别库</h1>
			<p class="text-[#71717a] text-base">查看所有类别信息</p>
		</div>

		<!-- Controls: search + sort -->
		<div class="flex gap-4 mb-6 flex-wrap">
			<div class="flex-1 min-w-[250px] relative">
				<span class="absolute left-4 top-1/2 -translate-y-1/2 text-[#71717a] text-[1.1rem]">⌕</span>
				<input v-model="searchQuery" type="text" placeholder="搜索 类别 名称..."
					   class="w-full py-3.5 px-4 pl-11 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-[0.95rem]"/>
			</div>

			<div class="flex gap-3 items-center">
				<select v-model="sortBy" @change="onSortChange"
						class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer">
					<option value="name">按类别名称</option>
					<option value="count">按作品数</option>
				</select>

				<select v-model="sortOrder" @change="onSortChange"
						class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer">
					<option value="desc">降序</option>
					<option value="asc">升序</option>
				</select>
			</div>
		</div>

		<div class="grid">
			<GenreGroupCard v-for="g in store.groups" :key="g.id" :genre="g" @click="openGenre(g)"/>
		</div>

		<div v-if="(store.pagination && store.pagination.pages) > 1" class="mt-8 w-full">
			<div class="flex items-center justify-center gap-3 mb-3">
				<button @click="loadPage(1)" :disabled="page === 1"
						class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md transform transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0">
					跳转开头
				</button>
				<button @click="loadPage(page - 1)" :disabled="page === 1"
						class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md transform transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0">
					上一页
				</button>
				<div class="px-4 py-2 rounded-md bg-[rgba(255,255,255,0.03)] text-[#f4f4f5]">第 {{ page }} 页 / 共 {{
						store.pagination.pages
					}} 页
				</div>
				<button @click="loadPage(page + 1)" :disabled="page === store.pagination.pages"
						class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md transform transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0">
					下一页
				</button>
				<button @click="loadPage(store.pagination.pages)" :disabled="page === store.pagination.pages"
						class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md transform transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0">
					跳转末尾
				</button>
			</div>
			<div class="flex items-center justify-center gap-4">
				<div class="flex items-center gap-2">
					<button
						class="px-3 py-1 rounded-md bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md"
						@click="loadPage(page)">跳转至第
					</button>
					<input v-model.number="page" @keydown.enter="loadPage(page)" type="number" min="1"
						   :max="store.pagination.pages"
						   class="w-20 px-3 py-1 rounded-md bg-[#1b1b26] text-[#f4f4f5] border border-white/[0.06] focus:outline-none text-center"/>
					<label class="text-sm text-[#bcbcbc]">页</label>

				</div>
				<div class="flex items-center gap-2">
					<label class="text-sm text-[#bcbcbc]">每页显示</label>
					<input v-model.number="pageSize" @change="onPageSizeChange" type="number" min="1"
						   class="w-20 px-3 py-1 rounded-md bg-[#1b1b26] text-[#f4f4f5] border border-white/[0.06] focus:outline-none text-center"/>
					<label class="text-sm text-[#bcbcbc]">个类别卡</label>
				</div>
			</div>
		</div>
	</div>
</template>

<script>
import GenreGroupCard from '../components/GenreGroupCard.vue'
import {useGenreGroupsStore} from '../stores/genreGroups'
import {onMounted, ref, watch} from 'vue'

export default {
	name: 'GenresView',
	components: {GenreGroupCard},
	setup() {
		const store = useGenreGroupsStore()
		const pageSizeOptions = [18, 24, 30]
		const pageSize = ref(18)
		const page = ref(1)
		const searchQuery = ref('')
		const sortBy = ref('count')
		const sortOrder = ref('desc')

		async function loadPage(p = 1) {
			// ensure we pass plain numbers
			const ps = Number(pageSize.value || 18)
			const pg = Number(p || 1)
			page.value = pg
			await store.load({
				page: pg,
				page_size: ps,
				order_by: sortBy.value || 'count',
				order: sortOrder.value || 'desc',
				search: searchQuery.value || undefined
			})
			// NOTE: Genres page intentionally does NOT fetch resource lists here.
			// Thumbnails/sample resources should be fetched on GenreDetail to avoid extra load.
		}

		function openGenre(g) {
			// SPA navigation to genre resource list
			window.location.href = `/genres/${g.id}`
		}

		function prev() {
			const p = Math.max(1, (store.pagination && store.pagination.page) ? store.pagination.page - 1 : page.value - 1)
			loadPage(p)
		}

		function next() {
			const p = Math.min((store.pagination && store.pagination.pages) ? store.pagination.pages : page.value + 1, (store.pagination && store.pagination.page) ? store.pagination.page + 1 : page.value + 1)
			loadPage(p)
		}

		function onPageSizeChange() {
			loadPage(1)
		}

		function onSortChange() {
			page.value = 1
			loadPage(1)
		}

		// debounce search input
		let _searchTimer = null
		watch(searchQuery, (val) => {
			if (_searchTimer) clearTimeout(_searchTimer)
			_searchTimer = setTimeout(() => {
				page.value = 1
				loadPage(1)
			}, 300)
		})

		onMounted(() => loadPage(1))

		return {
			store,
			openGenre,
			prev,
			next,
			page,
			pageSize,
			pageSizeOptions,
			onPageSizeChange,
			loadPage,
			searchQuery,
			sortBy,
			sortOrder,
			onSortChange
		}
	}
}
</script>

<style scoped>
.header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 12px
}

.grid {
	display: grid;
	grid-template-columns: repeat(6, 1fr);
	row-gap: 1rem;
	column-gap: 3rem;
}

.pagination {
	display: flex;
	gap: 8px;
	align-items: center;
	margin-top: 12px
}

.error {
	color: #ef4444
}

.controls select {
	background: #111827;
	color: #fff;
	padding: 6px;
	border-radius: 6px;
	border: 1px solid rgba(255, 255, 255, 0.06)
}
</style>
