<script setup>
import { defineEmits } from 'vue'

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
			<span class="absolute left-4 top-1/2 -translate-y-1/2 text-[#71717a] text-[1.1rem]">⌕</span>
			<input
				:value="searchQuery"
				type="text"
				placeholder="搜索 AVID、标题、来源..."
				class="w-full py-3.5 px-4 pl-11 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-[0.95rem] transition-all duration-200 focus:outline-none focus:border-[#ff6b6b] focus:shadow-[0_0_0_3px_rgba(255,107,107,0.1)] placeholder:text-[#71717a]"
				@input="handleSearchInput"
			>
		</div>

		<!-- Filters -->
		<div class="flex gap-3">
			<select
				:value="filterStatus"
				class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b]"
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
				class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b]"
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
				class="py-3.5 px-4 bg-[rgba(18,18,28,0.8)] border border-white/[0.08] rounded-xl text-[#f4f4f5] text-sm cursor-pointer transition-all duration-200 focus:outline-none focus:border-[#ff6b6b] ml-2"
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
/* select样式 */
select option {
	background: #0d0d14;
	color: #f4f4f5;
}
</style>
