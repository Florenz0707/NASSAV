<script setup>
// PROTOTYPE: three task-detail layouts on /downloads?demo=tasks&variant=list|board|timeline.
// All task state is synthetic and memory-only; no backend mutations.
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppButton from './AppButton.vue'
import AppIcon from './AppIcon.vue'
import CustomSelect from './CustomSelect.vue'
import EmptyState from './EmptyState.vue'
import PrototypeSwitcher from './PrototypeSwitcher.vue'
const route = useRoute()
const variants = [
  { value: 'list', label: 'A · 列表与详情' },
  { value: 'board', label: 'B · 状态看板' },
  { value: 'timeline', label: 'C · 活动时间线' },
]
const variant = computed(() =>
  variants.some((v) => v.value === route.query.variant) ? route.query.variant : 'list'
)
const type = ref('all'),
  state = ref('all'),
  selectedId = ref('d1')
const labels = { queued: '等待中', running: '执行中', succeeded: '已完成', failed: '失败' }
const stageLabels = {
  source_lookup: '查找资源',
  metadata: '获取元数据',
  cover: '下载封面',
  saving: '保存资源',
  translation_queued: '提交翻译',
}
const tasks = ref([
  {
    id: 'd1',
    type: 'download',
    avid: 'DEMO-001',
    title: '示例资源 · 正在下载',
    state: 'running',
    percent: 45,
    speed: '5.2 MB/s',
    downloaded: '452 MB',
    total: '1 GB',
    updated: '14:32:10',
  },
  {
    id: 's1',
    type: 'scrape',
    avid: 'DEMO-002',
    title: '新资源 · 获取元数据',
    state: 'running',
    action: 'add',
    stage: 'metadata',
    updated: '14:31:48',
  },
  {
    id: 'd2',
    type: 'download',
    avid: 'DEMO-003',
    title: '示例资源 · 等待下载',
    state: 'queued',
    percent: 0,
    updated: '14:31:20',
  },
  {
    id: 's2',
    type: 'scrape',
    avid: 'DEMO-004',
    title: '刷新资源 · 来源超时',
    state: 'failed',
    action: 'refresh',
    stage: 'metadata',
    error: '来源请求超时，已有资源未覆盖',
    updated: '14:30:12',
  },
  {
    id: 'd3',
    type: 'download',
    avid: 'DEMO-005',
    title: '示例资源 · 下载完成',
    state: 'succeeded',
    percent: 100,
    downloaded: '800 MB',
    total: '800 MB',
    updated: '14:29:03',
  },
  {
    id: 's3',
    type: 'scrape',
    avid: 'DEMO-006',
    title: '新资源 · 保存完成',
    state: 'succeeded',
    action: 'add',
    stage: 'translation_queued',
    updated: '14:28:51',
  },
])
const typeTasks = computed(() =>
  tasks.value.filter((t) => type.value === 'all' || t.type === type.value)
)
const visible = computed(() =>
  typeTasks.value.filter((t) => state.value === 'all' || t.state === state.value)
)
const selected = computed(
  () => visible.value.find((t) => t.id === selectedId.value) || visible.value[0]
)
const count = (s) => typeTasks.value.filter((t) => t.state === s).length
const taskType = (task) =>
  task.type === 'download' ? '下载' : task.action === 'refresh' ? '刷新刮削' : '新增刮削'
const progress = (task) =>
  task.type === 'download' ? `${task.percent || 0}%` : stageLabels[task.stage] || '尚未开始'
function advance() {
  const task = selected.value
  if (!task) return
  if (task.state === 'failed' || task.state === 'succeeded') {
    task.state = 'queued'
    task.error = ''
    task.percent = 0
    task.stage = 'source_lookup'
    return
  }
  if (task.state === 'queued') {
    task.state = 'running'
    return
  }
  if (task.type === 'download') {
    task.percent = Math.min(100, task.percent + 20)
    if (task.percent === 100) task.state = 'succeeded'
  } else {
    const stages = Object.keys(stageLabels),
      index = stages.indexOf(task.stage)
    if (index === stages.length - 1) task.state = 'succeeded'
    else task.stage = stages[index + 1]
  }
}
</script>
<template>
  <div class="pb-24 min-w-0">
    <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <div>
        <h1 class="text-3xl font-bold text-primary">任务详情</h1>
        <p class="text-secondary mt-2">统一查看下载与刮削的状态、进度和失败原因</p>
      </div>
      <span class="text-accent-warning border border-accent-warning/30 rounded-lg px-3 py-2 text-sm"
        >Demo · 模拟数据</span
      >
    </div>
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
      <div
        v-for="(label, key) in labels"
        :key="key"
        class="bg-secondary border rounded-xl p-4 border-[var(--border-color)]"
      >
        <span class="text-2xl font-bold text-primary">{{ count(key) }}</span>
        <p class="text-secondary text-sm mt-1">{{ label }}</p>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-3 mb-6">
      <AppButton
        v-for="option in [
          { value: 'all', label: '全部任务' },
          { value: 'download', label: '下载任务' },
          { value: 'scrape', label: '刮削任务' },
        ]"
        :key="option.value"
        :variant="type === option.value ? 'primary' : 'neutral'"
        :aria-pressed="type === option.value"
        @click="type = option.value"
        >{{ option.label }}</AppButton
      >
      <CustomSelect
        v-model="state"
        aria-label="任务状态"
        :options="[
          { value: 'all', label: '全部状态' },
          ...Object.entries(labels).map(([value, label]) => ({ value, label })),
        ]"
      />
    </div>
    <EmptyState v-if="!visible.length" title="暂无此类任务" />
    <div
      v-else
      class="grid gap-6"
      :class="
        variant === 'board' ? 'grid-cols-1' : 'grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px]'
      "
    >
      <div
        v-if="variant === 'list'"
        class="overflow-x-auto bg-secondary border rounded-xl min-w-0 border-[var(--border-color)]"
      >
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-secondary border-[var(--border-color)]">
              <th class="p-4 text-left">任务</th>
              <th class="p-4 text-left">状态</th>
              <th class="p-4 text-left">进度 / 阶段</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="task in visible"
              :key="task.id"
              class="border-b hover:bg-surface-subtle/5 border-[var(--border-color)]"
            >
              <td class="p-4">
                <button
                  class="text-primary text-left"
                  :aria-pressed="selected?.id === task.id"
                  @click="selectedId = task.id"
                >
                  <span class="block font-medium">{{ task.title }}</span
                  ><span class="text-muted text-xs">{{ task.avid }} · {{ taskType(task) }}</span>
                </button>
              </td>
              <td
                class="p-4 whitespace-nowrap"
                :class="task.state === 'failed' ? 'text-accent-danger' : 'text-secondary'"
              >
                {{ labels[task.state] }}
              </td>
              <td class="p-4 text-secondary whitespace-nowrap">{{ progress(task) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-else-if="variant === 'board'"
        class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4"
      >
        <section
          v-for="(label, key) in labels"
          :key="key"
          class="bg-secondary border rounded-xl p-4 border-[var(--border-color)]"
        >
          <h2 class="text-primary font-semibold mb-4">{{ label }}</h2>
          <div class="space-y-3">
            <button
              v-for="task in visible.filter((t) => t.state === key)"
              :key="task.id"
              class="w-full text-left bg-primary border rounded-lg p-3 hover:border-accent-primary"
              @click="selectedId = task.id"
            >
              <span class="text-muted text-xs">{{ taskType(task) }} · {{ task.avid }}</span
              ><span class="block text-primary my-2">{{ task.title }}</span
              ><span class="text-secondary text-sm">{{ progress(task) }}</span>
            </button>
            <p v-if="!visible.some((t) => t.state === key)" class="text-muted text-sm">暂无任务</p>
          </div>
        </section>
      </div>
      <ol v-else class="border-l pl-6 space-y-5 border-[var(--border-color)]">
        <li
          v-for="task in visible"
          :key="task.id"
          class="bg-secondary border rounded-xl p-4 border-[var(--border-color)]"
        >
          <time class="text-muted text-xs">{{ task.updated }}</time
          ><button
            class="block text-primary font-semibold my-2 text-left"
            @click="selectedId = task.id"
          >
            {{ task.title }}
          </button>
          <p class="text-secondary text-sm">
            {{ taskType(task) }} · {{ labels[task.state] }} · {{ progress(task) }}
          </p>
        </li>
      </ol>
      <aside
        v-if="selected"
        class="bg-secondary border rounded-xl p-5 min-w-0 border-[var(--border-color)]"
        aria-label="任务明细"
      >
        <div class="flex items-center gap-2 text-primary mb-4">
          <AppIcon :name="selected.type === 'download' ? 'download' : 'bolt'" />
          <h2 class="font-semibold">任务明细</h2>
        </div>
        <h3 class="text-primary font-medium">{{ selected.title }}</h3>
        <p class="text-muted text-sm mt-2">
          {{ selected.avid }} · {{ taskType(selected) }} · {{ labels[selected.state] }}
        </p>
        <template v-if="selected.type === 'download'"
          ><progress
            :value="selected.percent"
            max="100"
            class="w-full mt-5"
            aria-label="下载进度"
          />
          <p class="text-secondary text-sm mt-2">
            {{ progress(selected) }} · {{ selected.speed || '—' }}
          </p>
          <p class="text-muted text-xs mt-2">
            {{ selected.downloaded || '0 MB' }} / {{ selected.total || '大小待获取' }}
          </p></template
        >
        <ol v-else class="space-y-2 mt-5">
          <li
            v-for="(label, key) in stageLabels"
            :key="key"
            class="text-sm"
            :class="selected.stage === key ? 'text-accent-primary' : 'text-secondary'"
          >
            {{ selected.stage === key ? '→ ' : '' }}{{ label }}
          </li>
        </ol>
        <p v-if="selected.error" class="text-accent-danger text-sm mt-4" role="alert">
          {{ selected.error }}
        </p>
        <AppButton class="mt-5" @click="advance">{{
          selected.state === 'failed'
            ? '演示重试'
            : selected.state === 'succeeded'
              ? '重置演示'
              : '演示下一阶段'
        }}</AppButton>
        <p class="text-muted text-xs mt-3">仅改变本页模拟状态，不提交或取消真实任务。</p>
      </aside>
    </div>
    <details class="mt-6 bg-secondary border rounded-lg p-4 border-[var(--border-color)]">
      <summary class="cursor-pointer text-muted text-sm">模拟状态数据</summary>
      <pre class="overflow-x-auto text-secondary text-xs mt-3">{{
        JSON.stringify({ variant, type, state, selected, tasks }, null, 2)
      }}</pre>
    </details>
    <PrototypeSwitcher :variants="variants" :current="variant" />
  </div>
</template>
<style scoped>
progress {
  appearance: none;
  height: 0.5rem;
  border: 0;
  border-radius: 0.5rem;
  overflow: hidden;
}
progress::-webkit-progress-bar {
  background: var(--bg-white-10);
}
progress::-webkit-progress-value {
  background: var(--accent-primary);
}
progress::-moz-progress-bar {
  background: var(--accent-primary);
}
</style>
