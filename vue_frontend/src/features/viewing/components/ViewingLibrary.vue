<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { viewingApi } from '../../../api/viewing.js'
import { resourceApi } from '../../../api/resources.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { resolveResourceTitle } from '../../resources/lib/resourceTitle.js'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import ResourceCover from '../../../shared/ui/ResourceCover.vue'
import ResourcePagination from '../../../shared/ui/ResourcePagination.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
const props = defineProps({
  initialKind: {
    type: String,
    default: 'history',
    validator: (value) => ['history', 'watch-later'].includes(value),
  },
  embedded: Boolean,
})
const session = useSessionStore(),
  settings = useSettingsStore(),
  router = useRouter()
const kind = ref(props.initialKind),
  items = ref([]),
  loading = ref(false),
  error = ref(''),
  busy = ref('')
const pagination = ref({ page: 1, pages: 1, page_size: 15, total: 0 })
const guard = createRequestGuard()
async function load(page = pagination.value.page) {
  if (busy.value || session.status !== 'authenticated') return
  const ticket = guard.begin()
  loading.value = true
  error.value = ''
  try {
    const response = await viewingApi.list(kind.value, page, pagination.value.page_size)
    if (guard.current(ticket)) {
      items.value = response.data
      pagination.value = response.pagination
    }
  } catch (failure) {
    if (guard.current(ticket)) error.value = failure.message || '读取列表失败'
  } finally {
    if (guard.current(ticket)) loading.value = false
  }
}
watch(
  () => props.initialKind,
  (value) => {
    kind.value = value
  }
)
function reset() {
  guard.invalidate()
  items.value = []
  busy.value = ''
  error.value = ''
  loading.value = false
  pagination.value = { ...pagination.value, page: 1, pages: 1, total: 0 }
  if (session.status === 'authenticated') void load(1)
}
watch(() => [kind.value, session.status, session.username], reset, { immediate: true })
async function remove(item) {
  if (busy.value) return
  const ticket = guard.begin()
  busy.value = item.avid
  loading.value = false
  error.value = ''
  try {
    await resourceApi.updateStatus(item.avid, {
      watch_later: false,
      expected_version: item.state_version,
    })
    if (guard.current(ticket)) {
      busy.value = ''
      await load()
    }
  } catch (failure) {
    if (guard.current(ticket))
      error.value =
        failure.code === 409
          ? '资源状态已在其他页面更新，请刷新后重试'
          : failure.message || '移除失败'
  } finally {
    if (busy.value === item.avid && guard.current(ticket)) busy.value = ''
  }
}
function play(item) {
  window.open(
    router.resolve({ name: 'Playback', params: { avid: item.avid } }).href,
    '_blank',
    'noopener,noreferrer'
  )
}
function date(value) {
  return new Date(value).toLocaleString()
}
function size(value) {
  pagination.value.page_size = value
  void load(1)
}
function visible() {
  if (document.visibilityState === 'visible') void load()
}
onMounted(() => {
  window.addEventListener('focus', visible)
  document.addEventListener('visibilitychange', visible)
})
onBeforeUnmount(() => {
  guard.invalidate()
  window.removeEventListener('focus', visible)
  document.removeEventListener('visibilitychange', visible)
})
</script>
<template>
  <section
    aria-labelledby="viewing-title"
    :class="embedded ? 'min-w-0' : 'max-w-7xl mx-auto px-4 py-8'"
  >
    <header class="flex flex-wrap items-center justify-between gap-4 mb-6">
      <div>
        <component
          :is="embedded ? 'h2' : 'h1'"
          id="viewing-title"
          class="text-2xl font-semibold text-primary"
          >{{ embedded ? (kind === 'history' ? '观看历史' : '稍后再看') : '我的观看' }}</component
        >
        <p class="text-muted text-sm mt-2">
          观看历史按最近播放排序，同一资源只保留一条；稍后再看手动管理。
        </p>
      </div>
    </header>
    <div v-if="!embedded" class="flex flex-wrap gap-3 mb-6" role="group" aria-label="观看列表">
      <AppButton
        :variant="kind === 'history' ? 'primary' : 'neutral'"
        :aria-pressed="kind === 'history'"
        @click="kind = 'history'"
        >观看历史</AppButton
      >
      <AppButton
        :variant="kind === 'watch-later' ? 'primary' : 'neutral'"
        :aria-pressed="kind === 'watch-later'"
        @click="kind = 'watch-later'"
        >稍后再看</AppButton
      >
    </div>
    <PageLoad v-if="loading && !items.length" text="正在读取观看列表" />
    <RequestError v-if="error" :message="error" @retry="load()" />
    <EmptyState
      v-if="!loading && !error && !items.length"
      icon="empty"
      :title="kind === 'history' ? '暂无观看历史' : '暂无稍后再看资源'"
      :description="
        kind === 'history' ? '视频实际开始播放后会自动记录。' : '在资源详情中点击稍后再看即可加入。'
      "
    />
    <ul v-if="items.length" class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <li
        v-for="item in items"
        :key="item.avid"
        class="rounded-2xl bg-secondary border border-[var(--border-color)] overflow-hidden"
      >
        <RouterLink
          :to="{ name: 'ResourceDetail', params: { avid: item.avid } }"
          :aria-label="`${item.avid} 资源详情`"
          ><ResourceCover
            :url="resourceApi.getCoverUrl(item.avid, 'medium')"
            :title="resolveResourceTitle(item, settings.displayTitle) || item.avid"
            class="aspect-video rounded-none"
        /></RouterLink>
        <div class="p-4 space-y-3">
          <h2 class="text-primary font-medium line-clamp-2">
            {{ resolveResourceTitle(item, settings.displayTitle) || item.avid }}
          </h2>
          <p class="text-muted text-xs">
            {{ kind === 'history' ? '最近观看' : '加入时间' }}：<time :datetime="item.queue_time">{{
              date(item.queue_time)
            }}</time>
          </p>
          <div class="flex flex-wrap gap-2">
            <AppButton class="flex-1" @click="play(item)">播放</AppButton>
            <AppButton
              v-if="kind === 'watch-later'"
              variant="neutral"
              :disabled="!!busy || loading"
              :loading="busy === item.avid"
              @click="remove(item)"
              >移除</AppButton
            >
          </div>
        </div>
      </li>
    </ul>
    <ResourcePagination
      v-if="items.length"
      :page="pagination.page"
      :pages="pagination.pages"
      :page-size="pagination.page_size"
      :total="pagination.total"
      @change-page="load"
      @change-page-size="size"
    />
  </section>
</template>
