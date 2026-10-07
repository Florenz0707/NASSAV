<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useActorGroupsStore } from '../stores/actorGroups.js'
import { useGenreGroupsStore } from '../stores/genreGroups.js'
import ActorGroupCard from './ActorGroupCard.vue'
import GenreGroupCard from './GenreGroupCard.vue'
import SearchInput from '../../../shared/ui/SearchInput.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
import ResourcePagination from '../../../shared/ui/ResourcePagination.vue'
import LoadingSpinner from '../../../shared/ui/LoadingSpinner.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'

const props = defineProps({
  entity: {
    type: String,
    required: true,
    validator: (value) => ['actor', 'genre'].includes(value),
  },
})
const actor = props.entity === 'actor'
const label = actor ? '演员' : '类别'
const defaultPageSize = 15
const store = actor ? useActorGroupsStore() : useGenreGroupsStore()
const route = useRoute(),
  router = useRouter()
const integer = (value, fallback, maximum = Number.MAX_SAFE_INTEGER) =>
  Math.max(1, Math.min(maximum, Number.parseInt(value, 10) || fallback))
const page = ref(integer(route.query.page, 1)),
  pageSize = ref(integer(route.query.pageSize, defaultPageSize, 200))
const search = ref(String(route.query.search || ''))
const sortBy = ref(route.query.sortBy === 'name' ? 'name' : 'count')
const order = ref(route.query.order === 'asc' ? 'asc' : 'desc')
const sorts = [
  { value: 'count', label: '按作品数' },
  { value: 'name', label: `按${label}名称` },
]
const orders = [
  { value: 'desc', label: '降序' },
  { value: 'asc', label: '升序' },
]
let searchTimer

function load() {
  const query = { page: page.value }
  if (pageSize.value !== defaultPageSize) query.pageSize = pageSize.value
  if (search.value) query.search = search.value
  if (sortBy.value !== 'count') query.sortBy = sortBy.value
  if (order.value !== 'desc') query.order = order.value
  router.replace({ query })
  store.load({
    page: page.value,
    page_size: pageSize.value,
    order_by: sortBy.value,
    order: order.value,
    search: search.value,
  })
}
function changePageSize(value) {
  pageSize.value = integer(value, defaultPageSize, 200)
  page.value = 1
}
function destination(item) {
  return {
    path: `/${actor ? 'actors' : 'genres'}/${item.id}`,
    query: { from: route.fullPath },
  }
}
watch([page, pageSize, sortBy, order], load, { immediate: true })
watch(search, () => {
  clearTimeout(searchTimer)
  store.cancel()
  searchTimer = setTimeout(() => {
    if (page.value !== 1) page.value = 1
    else load()
  }, 300)
})
watch(
  () => route.query,
  (query) => {
    page.value = integer(query.page, 1)
    pageSize.value = integer(query.pageSize, defaultPageSize, 200)
    search.value = String(query.search || '')
    sortBy.value = query.sortBy === 'name' ? 'name' : 'count'
    order.value = query.order === 'asc' ? 'asc' : 'desc'
  }
)
onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  store.cancel()
})
</script>
<template>
  <div>
    <header class="mb-8">
      <h1 class="text-3xl font-bold text-primary mb-2">{{ label }}库</h1>
      <p class="text-muted">共有 {{ store.pagination.total }} 个{{ label }}信息</p>
    </header>
    <div class="flex flex-wrap gap-3 mb-6">
      <SearchInput
        v-model="search"
        :placeholder="`搜索 ${label} 名称...`"
        class="basis-full sm:basis-auto"
      />
      <CustomSelect
        v-model="sortBy"
        :options="sorts"
        :aria-label="`${label}排序字段`"
        @update:model-value="page = 1"
      />
      <CustomSelect
        v-model="order"
        :options="orders"
        aria-label="排序方向"
        @update:model-value="page = 1"
      />
    </div>
    <p v-if="store.error" class="text-accent-danger mb-4" role="alert">{{ store.error }}</p>
    <LoadingSpinner v-if="store.loading" text="正在加载..." role="status" />
    <EmptyState v-else-if="!store.error && !store.groups.length" title="暂无匹配结果" />
    <div class="directory-grid library-grid">
      <component
        :is="actor ? ActorGroupCard : GenreGroupCard"
        v-for="item in store.groups"
        :key="item.id"
        v-bind="actor ? { actor: item } : { genre: item }"
        :to="destination(item)"
      />
    </div>
    <ResourcePagination
      v-if="store.pagination.pages > 1"
      :page="page"
      :pages="store.pagination.pages"
      :page-size="pageSize"
      :total="store.pagination.total"
      @change-page="page = $event"
      @change-page-size="changePageSize"
    />
  </div>
</template>
<style scoped>
.directory-grid {
  gap: 1rem;
}
</style>
