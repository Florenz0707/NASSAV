<script setup>
import { computed } from 'vue'
import SearchInput from '../../../shared/ui/SearchInput.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'

const props = defineProps({
  searchQuery: {
    type: String,
    default: '',
  },
  filterStatus: {
    type: String,
    default: 'all',
  },
  sortBy: {
    type: String,
    default: 'metadata_create_time',
  },
  sortOrder: {
    type: String,
    default: 'desc',
  },
  showFavoriteFilter: {
    type: Boolean,
    default: false,
  },
  showWatchedFilter: {
    type: Boolean,
    default: false,
  },
  showMetadataUpdateSort: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits([
  'update:searchQuery',
  'update:filterStatus',
  'update:sortBy',
  'update:sortOrder',
  'sortChange',
])

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

const filterOptions = computed(() => {
  const options = [
    { value: 'all', label: '全部状态' },
    { value: 'downloaded', label: '已下载' },
    { value: 'pending', label: '未下载' },
  ]
  if (props.showWatchedFilter) {
    options.push({ value: 'watched', label: '已观看' })
    options.push({ value: 'unwatched', label: '未观看' })
  }
  if (props.showFavoriteFilter) {
    options.push({ value: 'favorite', label: '已收藏' })
  }
  return options
})

const sortByOptions = computed(() => {
  const options = [
    { value: 'avid', label: '按编号' },
    { value: 'metadata_create_time', label: '按元数据创建时间' },
  ]
  if (props.showMetadataUpdateSort) {
    options.push({ value: 'metadata_update_time', label: '按元数据更新时间' })
  }
  options.push({ value: 'video_create_time', label: '按视频下载时间' })
  options.push({ value: 'source', label: '按来源' })
  return options
})

const sortOrderOptions = [
  { value: 'desc', label: '降序' },
  { value: 'asc', label: '升序' },
]
</script>

<template>
  <div class="flex gap-4 mb-6 flex-wrap">
    <SearchInput
      :model-value="searchQuery"
      placeholder="搜索标题..."
      class="basis-full sm:basis-auto"
      @update:model-value="emit('update:searchQuery', $event)"
    />

    <!-- Filters -->
    <div class="flex gap-3 flex-wrap">
      <CustomSelect
        :model-value="filterStatus"
        :options="filterOptions"
        class="filter-select"
        @update:model-value="handleFilterChange({ target: { value: $event } })"
      />

      <CustomSelect
        :model-value="sortBy"
        :options="sortByOptions"
        class="filter-select"
        @update:model-value="handleSortByChange({ target: { value: $event } })"
      />

      <CustomSelect
        :model-value="sortOrder"
        :options="sortOrderOptions"
        class="filter-select ml-2"
        @update:model-value="handleSortOrderChange({ target: { value: $event } })"
      />
    </div>
  </div>
</template>

<style scoped>
.filter-select {
  min-width: 8.5rem;
}
.filter-select:focus {
  outline: none;
}
</style>
