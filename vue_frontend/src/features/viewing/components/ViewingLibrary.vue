<script setup>
import { computed, onActivated, onDeactivated, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { viewingApi } from '../../../api/viewing.js'
import { resourceApi } from '../../../api/resources.js'
import { useViewingStore } from '../stores/viewing.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { resolveResourceTitle } from '../../resources/lib/resourceTitle.js'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppCheckbox from '../../../shared/ui/AppCheckbox.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import ResourceCover from '../../../shared/ui/ResourceCover.vue'
import ResourcePagination from '../../../shared/ui/ResourcePagination.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
const props = defineProps({
  initialKind: {
    type: String,
    default: 'history',
    validator: (v) => ['history', 'watch-later'].includes(v),
  },
  embedded: Boolean,
})
const session = useSessionStore(),
  settings = useSettingsStore(),
  router = useRouter(),
  viewing = useViewingStore()
const kind = ref(props.initialKind),
  items = ref([]),
  loading = ref(false),
  error = ref(''),
  busy = ref('')
const pagination = ref({ page: 1, pages: 1, page_size: 15, total: 0 })
const batchMode = ref(false)
const selected = ref([]),
  confirmation = ref(null)
const allSelected = computed(
  () => items.value.length > 0 && selected.value.length === items.value.length
)
const guard = createRequestGuard()
let active = true
async function load(page = pagination.value.page, force = false) {
  if (!active || busy.value || session.status !== 'authenticated') return
  const ticket = guard.begin()
  loading.value = true
  error.value = ''
  try {
    const response = await viewing.list(kind.value, page, pagination.value.page_size, force)
    if (guard.current(ticket) && response) {
      const previous = new Map(items.value.map((item) => [item.avid, item.queue_time]))
      selected.value = selected.value.filter((id) =>
        response.data.some((item) => item.avid === id && previous.get(id) === item.queue_time)
      )
      items.value = response.data
      pagination.value = response.pagination
    }
  } catch (failure) {
    if (guard.current(ticket)) error.value = failure.message || '读取列表失败'
  } finally {
    if (guard.current(ticket)) loading.value = false
  }
  return guard.current(ticket)
}
watch(
  () => props.initialKind,
  (v) => {
    kind.value = v
  }
)
watch(
  () => [kind.value, session.status, session.identity],
  () => {
    guard.invalidate()
    items.value = []
    selected.value = []
    batchMode.value = false
    confirmation.value = null
    busy.value = ''
    error.value = ''
    loading.value = false
    pagination.value = { ...pagination.value, page: 1, pages: 1, total: 0 }
    void load(1)
  },
  { immediate: true }
)
watch(
  () => viewing.revision,
  () => {
    if (active && !busy.value) void load()
  }
)
function toggleBatch() {
  if (busy.value || loading.value) return
  batchMode.value = !batchMode.value
  selected.value = []
}
function select(avid, checked) {
  selected.value = checked
    ? [...new Set([...selected.value, avid])]
    : selected.value.filter((id) => id !== avid)
}
function confirmHistory(entries) {
  confirmation.value = {
    action: 'history',
    entries: entries.map(({ avid, queue_time }) => ({ avid, queue_time })),
    message: `删除这 ${entries.length} 条观看历史？资源、播放进度和个人状态会保留。`,
  }
}
async function execute() {
  const action = confirmation.value
  confirmation.value = null
  if (!action || busy.value) return
  await mutate('batch', async () => {
    if (action.action === 'watched') return viewingApi.removeWatched()
    const result = await viewingApi.removeHistory(action.entries)
    if (result.data.some((row) => row.status === 'conflict'))
      return '部分资源已再次观看，已保留最新历史，请重新确认。'
  })
}
async function mutate(id, operation) {
  if (busy.value) return
  const ticket = guard.begin()
  busy.value = id
  loading.value = false
  error.value = ''
  try {
    const message = await operation()
    if (guard.current(ticket)) {
      busy.value = ''
      const current = await load(pagination.value.page, true)
      if (current && typeof message === 'string') error.value = message
    }
  } catch (failure) {
    if (guard.current(ticket))
      error.value =
        failure.code === 409
          ? '资源状态已在其他页面更新，请刷新后重试'
          : failure.message || '操作失败'
  } finally {
    if (guard.current(ticket)) busy.value = ''
  }
}
function remove(item) {
  return mutate(item.avid, () =>
    resourceApi.updateStatus(item.avid, {
      watch_later: false,
      expected_version: item.state_version,
    })
  )
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
  if (active && document.visibilityState === 'visible') void load()
}
onActivated(() => {
  active = true
  void load()
})
onDeactivated(() => {
  active = false
  guard.invalidate()
  loading.value = false
  busy.value = ''
  confirmation.value = null
  batchMode.value = false
  selected.value = []
})
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
    :aria-busy="loading || !!busy"
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
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <AppButton
          v-if="kind === 'watch-later'"
          :loading="busy === 'batch'"
          variant="neutral"
          :disabled="!!busy || loading || !items.length"
          @click="
            confirmation = {
              action: 'watched',
              message: '确定要清除已观看资源吗？',
            }
          "
          >清除已观看资源</AppButton
        >
        <template v-else>
          <template v-if="batchMode">
            <div class="inline-flex items-center gap-3 text-sm text-secondary">
              <AppCheckbox
                :checked="allSelected"
                :indeterminate="!!selected.length && !allSelected"
                :disabled="!!busy || loading"
                label="选择本页全部历史"
                @change="selected = $event ? items.map((item) => item.avid) : []"
              />
              <span>已选择 {{ selected.length }} 项</span>
            </div>
            <AppButton
              variant="danger"
              :loading="busy === 'batch'"
              :disabled="!selected.length || !!busy || loading"
              @click="confirmHistory(items.filter((item) => selected.includes(item.avid)))"
              >清除所选</AppButton
            >
          </template>
          <AppButton
            variant="neutral"
            :disabled="!!busy || loading || (!items.length && !batchMode)"
            :aria-pressed="batchMode"
            @click="toggleBatch"
          >
            {{ batchMode ? '退出批量' : '批量操作' }}
          </AppButton>
        </template>
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
    <RequestError v-if="error" :message="error" @retry="load(pagination.page, true)" />
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
        class="viewing-card rounded-2xl bg-secondary border border-[var(--border-color)] overflow-hidden"
        :class="{ 'is-selected': batchMode && selected.includes(item.avid) }"
      >
        <div class="relative overflow-hidden">
          <div v-if="kind === 'history' && batchMode" class="absolute z-30 top-3 left-3">
            <AppCheckbox
              :checked="selected.includes(item.avid)"
              :disabled="!!busy || loading"
              :label="`选择资源 ${item.avid}`"
              @change="select(item.avid, $event)"
            />
          </div>
          <RouterLink
            class="block"
            :to="{ name: 'ResourceDetail', params: { avid: item.avid } }"
            :aria-label="`${item.avid} 资源详情`"
          >
            <ResourceCover
              :url="resourceApi.getCoverUrl(item.avid, 'medium')"
              :title="resolveResourceTitle(item, settings.displayTitle) || item.avid"
              class="aspect-video"
              square-bottom
            />
          </RouterLink>
        </div>
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
            <AppButton
              v-else
              variant="danger"
              :disabled="!!busy || loading"
              @click="confirmHistory([item])"
              >清除历史</AppButton
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
    <ConfirmDialog
      :show="!!confirmation"
      title="确认列表操作"
      :message="confirmation?.message || ''"
      @confirm="execute"
      @cancel="confirmation = null"
    />
  </section>
</template>

<style scoped>
.viewing-card {
  transition:
    transform 250ms ease,
    box-shadow 250ms ease,
    border-color 250ms ease;
}
@media (hover: hover) and (pointer: fine) {
  .viewing-card:hover {
    transform: translateY(-0.25rem);
    box-shadow: 0 12px 40px color-mix(in srgb, var(--shadow-color) 30%, transparent);
    border-color: color-mix(in srgb, var(--accent-primary) 35%, var(--border-color));
  }
}
.viewing-card:focus-within {
  border-color: var(--accent-primary);
}
.viewing-card.is-selected {
  border-color: color-mix(in srgb, var(--accent-primary) 75%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-primary) 20%, transparent);
}
@media (prefers-reduced-motion: reduce) {
  .viewing-card {
    transition: none;
  }
  .viewing-card:hover {
    transform: none;
  }
}
</style>
