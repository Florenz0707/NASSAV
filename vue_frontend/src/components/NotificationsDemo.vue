<script setup>
// PROTOTYPE: notification drawer / timeline / grouped feed on /downloads?demo=notifications.
// No API calls, subscriptions or persistence. Actions change only these samples.
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppButton from './AppButton.vue'
import AppIcon from './AppIcon.vue'
import EmptyState from './EmptyState.vue'
import PrototypeSwitcher from './PrototypeSwitcher.vue'
import NotificationDemoTimeline from './NotificationDemoTimeline.vue'
import { useDialog } from '../composables/useDialog.js'
const route = useRoute()
const variants = [
  { value: 'panel', label: 'A · 侧栏时间线' },
  { value: 'timeline', label: 'B · 通知中心' },
  { value: 'grouped', label: 'C · 事件分组' },
]
const variant = computed(() =>
  variants.some((v) => v.value === route.query.variant) ? route.query.variant : 'panel'
)
const samples = () => [
  {
    id: 'n1',
    day: '今天',
    time: '14:32',
    title: '下载失败 · 山间来信',
    message: '连接中断，已保留下载进度；可以在任务详情中处理。',
    avid: 'DEMO-003',
    severity: 'danger',
    unread: true,
    targetLabel: '查看任务',
  },
  {
    id: 'n2',
    day: '今天',
    time: '14:28',
    title: '批量添加结束',
    message: '12 项资源：成功 10、失败 2。',
    severity: 'danger',
    unread: true,
    targetLabel: '查看批次',
    failures: ['DEMO-007 · 来源超时', 'DEMO-008 · 未找到资源'],
  },
  {
    id: 'n3',
    day: '今天',
    time: '14:20',
    title: '下载完成 · 雨后森林的清晨',
    message: '1 GB · 资源已就绪。',
    avid: 'DEMO-001',
    severity: 'success',
    unread: false,
    targetLabel: '查看资源',
  },
  {
    id: 'n4',
    day: '昨天',
    time: '18:05',
    title: '刮削完成 · 海边的一日',
    message: '已保存元数据和封面，翻译仍在排队。',
    avid: 'DEMO-006',
    severity: 'success',
    unread: true,
    targetLabel: '查看资源',
  },
]
const events = ref(samples()),
  filter = ref('all'),
  selectedId = ref('')
const unread = computed(() => events.value.filter((e) => e.unread).length)
const visible = computed(() =>
  events.value.filter(
    (e) =>
      filter.value === 'all' || (filter.value === 'unread' ? e.unread : e.severity === 'danger')
  )
)
const selected = computed(() => events.value.find((e) => e.id === selectedId.value))
const days = computed(() => [...new Set(visible.value.map((e) => e.day))])
const drawerOpen = ref(false),
  drawerRoot = ref(null)
const drawerVisible = computed(() => variant.value === 'panel' && drawerOpen.value)
const close = () => {
  drawerOpen.value = false
}
const { titleId } = useDialog(drawerVisible, drawerRoot, close)
function select(event) {
  selectedId.value = event.id
  event.unread = false
}
function readAll() {
  events.value.forEach((event) => {
    event.unread = false
  })
}
function reset() {
  events.value = samples()
  selectedId.value = ''
  filter.value = 'all'
}
</script>
<template>
  <div class="pb-24 min-w-0">
    <header class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <div>
        <h1 class="text-3xl font-bold text-primary">通知设计预览</h1>
        <p class="text-secondary mt-2">事件时间线 · 模拟数据，仅用于比较展示方式</p>
      </div>
      <AppButton variant="neutral" @click="reset">重置演示</AppButton>
    </header>
    <div class="flex flex-wrap items-center gap-3 mb-6">
      <AppButton
        v-for="option in [
          { value: 'all', label: '全部' },
          { value: 'unread', label: '未读' },
          { value: 'attention', label: '需要处理' },
        ]"
        :key="option.value"
        :variant="filter === option.value ? 'primary' : 'neutral'"
        :aria-pressed="filter === option.value"
        @click="filter = option.value"
        >{{ option.label }}</AppButton
      >
      <AppButton variant="neutral" @click="readAll">全部标为已读</AppButton>
      <span class="text-muted text-sm">{{ unread }} 条未读</span>
    </div>
    <section
      v-if="variant === 'panel'"
      class="bg-secondary border rounded-xl p-6 border-[var(--border-color)]"
    >
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 class="text-primary font-semibold">在任务页随手查看事件</h2>
          <p class="text-secondary text-sm mt-2">
            铃铛打开侧栏，主页面保留上下文；手机使用全宽面板。
          </p>
        </div>
        <AppButton variant="neutral" aria-label="打开通知预览" @click="drawerOpen = true"
          ><AppIcon name="bell" /><span>{{ unread }} 条未读</span></AppButton
        >
      </div>
      <p class="text-muted text-sm mt-6">
        普通完成消息更新未读数量；失败消息提供任务入口。进度变化留在任务详情。
      </p>
    </section>
    <EmptyState v-else-if="!visible.length" title="暂无此类通知" />
    <div v-else-if="variant === 'timeline'" class="space-y-6 max-w-3xl">
      <section v-for="day in days" :key="day">
        <h2 class="text-primary font-semibold mb-4">{{ day }}</h2>
        <NotificationDemoTimeline
          :events="visible.filter((e) => e.day === day)"
          :selected-id="selectedId"
          @select="select"
          @read="(e) => (e.unread = false)"
        />
      </section>
    </div>
    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <section
        v-for="group in [
          { danger: true, label: '需要处理' },
          { danger: false, label: '完成消息' },
        ]"
        :key="group.label"
      >
        <h2 class="text-primary font-semibold mb-4">{{ group.label }}</h2>
        <NotificationDemoTimeline
          :events="visible.filter((e) => (e.severity === 'danger') === group.danger)"
          :selected-id="selectedId"
          @select="select"
          @read="(e) => (e.unread = false)"
        />
      </section>
    </div>
    <section
      v-if="selected"
      class="bg-secondary border rounded-xl p-5 mt-6 border-[var(--border-color)]"
      aria-label="模拟关联详情"
    >
      <h2 class="font-semibold text-primary">{{ selected.targetLabel }} · 关联详情演示</h2>
      <p class="text-secondary mt-2">{{ selected.title }}</p>
      <p class="text-muted text-sm mt-2">{{ selected.message }}</p>
      <p class="text-muted text-xs mt-3">
        已读只代表看过，失败事件仍属于“需要处理”。这里不跳转或重试真实任务。
      </p>
    </section>
    <details class="bg-secondary border rounded-lg p-4 mt-6 border-[var(--border-color)]">
      <summary class="text-muted cursor-pointer text-sm">模拟通知数据</summary>
      <pre class="overflow-x-auto text-secondary text-xs mt-3">{{
        JSON.stringify({ variant, filter, selectedId, events }, null, 2)
      }}</pre>
    </details>
    <Teleport to="body">
      <div v-if="drawerVisible" class="fixed inset-0 z-[10000] bg-overlay" @click.self="close">
        <section
          ref="drawerRoot"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          tabindex="-1"
          class="absolute right-0 inset-y-0 w-full sm:w-[440px] bg-secondary shadow-lg overflow-y-auto p-5"
        >
          <div class="flex items-center justify-between gap-3 mb-4">
            <h2 :id="titleId" class="text-primary text-xl font-semibold">通知预览</h2>
            <AppButton variant="neutral" aria-label="关闭通知预览" @click="close"
              ><AppIcon name="close"
            /></AppButton>
          </div>
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <span class="text-muted text-sm">{{ unread }} 条未读</span
            ><AppButton size="sm" variant="neutral" @click="readAll">全部标为已读</AppButton>
          </div>
          <NotificationDemoTimeline
            v-if="visible.length"
            :events="visible"
            :selected-id="selectedId"
            @select="select"
            @read="(e) => (e.unread = false)"
          />
          <EmptyState v-else title="暂无此类通知" />
          <p v-if="selected" class="text-secondary text-sm mt-4" role="status">
            已选择：{{ selected.title }}，关闭侧栏可查看关联详情演示。
          </p>
        </section>
      </div>
    </Teleport>
    <PrototypeSwitcher :variants="variants" :current="variant" />
  </div>
</template>
