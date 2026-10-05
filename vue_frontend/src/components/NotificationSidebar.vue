<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useNotificationsStore } from '../stores/notifications.js'
import { useDialog } from '../composables/useDialog.js'
import AppButton from './AppButton.vue'
import AppIcon from './AppIcon.vue'
import EmptyState from './EmptyState.vue'
import NotificationTimeline from './NotificationTimeline.vue'
const notifications = useNotificationsStore(),
  route = useRoute()
const root = ref(null),
  filter = ref('all'),
  selectedId = ref(''),
  samples = ref([])
const preview = computed(() => import.meta.env.DEV && route.query.demo === 'notifications')
let previewVersion = 0
watch(
  preview,
  async (show) => {
    const version = ++previewVersion
    selectedId.value = ''
    filter.value = 'all'
    samples.value = []
    if (show && import.meta.env.DEV) {
      const module = await import('../utils/notificationDebugData.js')
      if (version !== previewVersion) return
      samples.value = module.notificationDebugData()
      notifications.show()
    }
  },
  { immediate: true }
)
onBeforeUnmount(() => {
  previewVersion++
})
const opened = computed(() => notifications.opened)
const { titleId } = useDialog(opened, root, notifications.close)
const events = computed(() =>
  preview.value
    ? samples.value
    : notifications.events.map((event) => {
        const date = new Date(event.timestamp)
        return {
          ...event,
          day: date.toLocaleDateString('zh-CN'),
          time: date.toLocaleTimeString('zh-CN', { hour12: false }),
        }
      })
)
const unread = computed(() => events.value.filter((event) => event.unread).length)
const visible = computed(() =>
  events.value.filter(
    (event) =>
      filter.value === 'all' ||
      (filter.value === 'unread' ? event.unread : event.severity === 'danger')
  )
)
const selected = computed(() => events.value.find((event) => event.id === selectedId.value))
function markRead(event) {
  if (preview.value) {
    const sample = samples.value.find((item) => item.id === event.id)
    if (sample) sample.unread = false
  } else notifications.markRead(event.id)
}
function select(event) {
  selectedId.value = event.id
  markRead(event)
}
function readAll() {
  if (preview.value)
    samples.value.forEach((event) => {
      event.unread = false
    })
  else notifications.readAll()
}
</script>
<template>
  <Teleport to="body">
    <div v-if="opened" class="fixed inset-0 z-[10000] bg-overlay" @click.self="notifications.close">
      <section
        ref="root"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
        class="absolute inset-y-0 right-0 w-full sm:w-[440px] bg-secondary shadow-lg overflow-y-auto p-5"
      >
        <header class="flex items-center justify-between gap-3 mb-4">
          <h2 :id="titleId" class="text-primary text-xl font-semibold">
            {{ preview ? '通知预览' : '通知' }}
          </h2>
          <AppButton variant="neutral" aria-label="关闭通知" @click="notifications.close"
            ><AppIcon name="close"
          /></AppButton>
        </header>
        <p class="text-muted text-xs mb-4">
          {{
            preview
              ? '独立模拟消息，不操作真实任务。'
              : '当前登录会话的最近事件，最多 100 条；已读不表示问题已解决。'
          }}
        </p>
        <div class="flex flex-wrap gap-2 mb-4">
          <AppButton
            v-for="option in [
              { value: 'all', label: '全部' },
              { value: 'unread', label: '未读' },
              { value: 'attention', label: '需要处理' },
            ]"
            :key="option.value"
            size="sm"
            :variant="filter === option.value ? 'primary' : 'neutral'"
            :aria-pressed="filter === option.value"
            @click="filter = option.value"
            >{{ option.label }}</AppButton
          >
        </div>
        <div class="flex items-center justify-between gap-3 mb-4">
          <span class="text-muted text-sm">{{ unread }} 条未读</span
          ><AppButton variant="neutral" size="sm" @click="readAll">全部标为已读</AppButton>
        </div>
        <NotificationTimeline
          v-if="visible.length"
          :events="visible"
          :selected-id="selectedId"
          @select="select"
          @read="markRead"
        />
        <EmptyState v-else title="暂无此类通知" />
        <section
          v-if="selected"
          class="border rounded-lg p-4 mt-4 border-[var(--border-color)]"
          aria-label="通知详情"
        >
          <h3 class="text-primary font-semibold">{{ selected.title }}</h3>
          <p class="text-secondary text-sm mt-2">{{ selected.message }}</p>
          <RouterLink
            v-if="!preview && selected.target"
            :to="selected.target"
            class="inline-flex text-accent-primary mt-3"
            @click="notifications.close"
            >{{ selected.targetLabel }}</RouterLink
          >
          <p v-else class="text-muted text-xs mt-3">仅演示关联详情，不跳转或重试真实任务。</p>
        </section>
        <details v-if="preview" class="mt-4 text-muted text-xs">
          <summary class="cursor-pointer">模拟通知数据</summary>
          <pre class="overflow-x-auto mt-2">{{ JSON.stringify(samples, null, 2) }}</pre>
        </details>
      </section>
    </div>
  </Teleport>
</template>
