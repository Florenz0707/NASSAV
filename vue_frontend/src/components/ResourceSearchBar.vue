<script setup>

defineProps({
	searchQuery: {
		type: String,
		default: ''
	},
	filterStatus: {
		type: String,
		default: 'all'
	},
	sortBy: {
		type: String,
		default: 'metadata_create_time'
	},
	sortOrder: {
		type: String,
		default: 'desc'
	},
	showFavoriteFilter: {
		type: Boolean,
		default: false
	},
	showWatchedFilter: {
		type: Boolean,
		default: false
	},
	showMetadataUpdateSort: {
		type: Boolean,
		default: false
	}
})

const emit = defineEmits(['update:searchQuery', 'update:filterStatus', 'update:sortBy', 'update:sortOrder', 'sortChange'])

function handleSearchInput(event) {
	emit('update:searchQuery', event.target.value)
}

function handleFilterChange(event) {
	emit('update:filterStatus', event.target.value)
}

function handleSortByChange(event) {
	emit('update:sortBy', event.target.value)
	emit('sortChange')
}

function handleSortOrderChange(event) {
	emit('update:sortOrder', event.target.value)
	emit('sortChange')
}
</script>

<template>
	<div class="flex gap-4 mb-6 flex-wrap">
		<!-- Search Box -->
		<div class="flex-1 min-w-[250px] relative">
			<svg class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5" style="color: var(--text-muted);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
			</svg>
			<input
				:value="searchQuery"
				type="text"
				placeholder="搜索标题..."
				class="search-input w-full py-3.5 px-4 pl-12 border rounded-xl text-[0.95rem] transition-all duration-200 focus:outline-none"
				@input="handleSearchInput"
			>
		</div>

		<!-- Filters -->
		<div class="flex gap-3">
			<select
				:value="filterStatus"
				class="filter-select py-3.5 px-4 border rounded-xl text-sm cursor-pointer transition-all duration-200 focus:outline-none"
				@change="handleFilterChange"
			>
				<option value="all">
					全部状态
				</option>
				<option value="downloaded">
					已下载
				</option>
				<option value="pending">
					未下载
				</option>
				<option v-if="showWatchedFilter" value="watched">
					已观看
				</option>
				<option v-if="showWatchedFilter" value="unwatched">
					未观看
				</option>
				<option v-if="showFavoriteFilter" value="favorite">
					已收藏
				</option>
			</select>

			<select
				:value="sortBy"
				class="filter-select py-3.5 px-4 border rounded-xl text-sm cursor-pointer transition-all duration-200 focus:outline-none"
				@change="handleSortByChange"
			>
				<option value="avid">
					按编号
				</option>
				<option value="metadata_create_time">
					按元数据创建时间
				</option>
				<option v-if="showMetadataUpdateSort" value="metadata_update_time">
					按元数据更新时间
				</option>
				<option value="video_create_time">
					按视频下载时间
				</option>
				<option value="source">
					按来源
				</option>
			</select>
			<select
				:value="sortOrder"
				class="filter-select py-3.5 px-4 border rounded-xl text-sm cursor-pointer transition-all duration-200 focus:outline-none ml-2"
				@change="handleSortOrderChange"
			>
				<option value="desc">
					降序
				</option>
				<option value="asc">
					升序
				</option>
			</select>
		</div>
	</div>
</template>

<style scoped>
.search-input {
	background: var(--bg-input);
	border-color: var(--border-color);
	color: var(--text-primary);
}
.search-input::placeholder {
	color: var(--text-muted);
}
.search-input:focus {
	border-color: var(--accent-primary);
	box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.1);
}

.filter-select {
	background: var(--bg-input);
	border-color: var(--border-color);
	color: var(--text-primary);
}
.filter-select:focus {
	border-color: var(--accent-primary);
}
.filter-select option {
	background: var(--bg-primary);
	color: var(--text-primary);
}
</style>
