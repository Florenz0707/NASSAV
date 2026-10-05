<script setup>
// PROTOTYPE: selected list/detail layout on /downloads?demo=tasks.
// All task state is synthetic and memory-only; no backend mutations.
import { computed, ref } from 'vue'
import AppButton from './AppButton.vue'
import AppIcon from './AppIcon.vue'
import CustomSelect from './CustomSelect.vue'
import EmptyState from './EmptyState.vue'
import DemoResourceCover from './DemoResourceCover.vue'
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
    title: '雨后森林的清晨',
    coverScene: 'forest',
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
    title: '',
    coverScene: '',
    state: 'running',
    action: 'add',
    stage: 'metadata',
    updated: '14:31:48',
  },
  {
    id: 'd2',
    type: 'download',
    avid: 'DEMO-003',
    title: '山间来信：沿着溪流走向远方',
    coverScene: 'mountain',
    state: 'queued',
    percent: 0,
    updated: '14:31:20',
  },
  {
    id: 's2',
    type: 'scrape',
    avid: 'DEMO-004',
    title: '暮色中的海岸',
    coverScene: 'coast',
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
    title: '城市夜行：最后一班列车',
    coverScene: 'city',
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
    title: '海边的一日',
    coverScene: 'coast',
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
const resourceName = (task) => task.title || task.avid
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
    <div v-else class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-6 items-start">
      <div
        class="overflow-x-auto bg-secondary border rounded-xl min-w-0 border-[var(--border-color)]"
      >
        <table class="w-full text-sm">
          <caption class="text-left p-4 text-secondary">
            {{
              visible.length
            }}
            个任务 · 点击资源查看明细
          </caption>
          <thead>
            <tr class="border-b text-secondary border-[var(--border-color)]">
              <th class="p-4 text-left">资源 / 任务</th>
              <th class="p-4 text-left">状态</th>
              <th class="p-4 text-left">进度 / 阶段</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="task in visible"
              :key="task.id"
              class="border-b hover:bg-surface-subtle/5 border-[var(--border-color)]"
              :class="selected?.id === task.id ? 'bg-accent-primary/10' : ''"
            >
              <td class="p-4">
                <button
                  class="flex items-center gap-3 w-full text-primary text-left min-w-[240px]"
                  :aria-label="resourceName(task) + '，查看任务明细'"
                  :aria-pressed="selected?.id === task.id"
                  @click="selectedId = task.id"
                >
                  <DemoResourceCover
                    :scene="task.coverScene"
                    :title="resourceName(task)"
                    class="w-24 h-16 shrink-0"
                  />
                  <span class="min-w-0">
                    <span class="block font-medium line-clamp-2">{{ resourceName(task) }}</span>
                    <span class="block text-muted text-xs mt-1"
                      >{{ task.avid }} · {{ taskType(task) }}</span
                    >
                    <span v-if="!task.title" class="block text-muted text-xs mt-1"
                      >资源名称尚未获取</span
                    >
                  </span>
                </button>
              </td>
              <td
                class="p-4 whitespace-nowrap"
                :class="task.state === 'failed' ? 'text-accent-danger' : 'text-secondary'"
              >
                {{ labels[task.state] }}
              </td>
              <td class="p-4 text-secondary whitespace-nowrap">
                <span class="block">{{ progress(task) }}</span>
                <span
                  v-if="task.type === 'download' && task.state === 'running'"
                  class="text-muted text-xs"
                  >{{ task.speed }}</span
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <aside
        v-if="selected"
        class="bg-secondary border rounded-xl p-5 min-w-0 border-[var(--border-color)]"
        aria-label="任务明细"
      >
        <div class="flex items-center gap-2 text-primary mb-4">
          <AppIcon :name="selected.type === 'download' ? 'download' : 'bolt'" />
          <h2 class="font-semibold">任务明细</h2>
        </div>
        <DemoResourceCover
          :scene="selected.coverScene"
          :title="resourceName(selected)"
          class="w-full aspect-video mb-4"
        />
        <h3 class="text-primary font-medium break-words">{{ resourceName(selected) }}</h3>
        <p v-if="!selected.title" class="text-muted text-xs mt-2">
          正在获取资源信息，暂以 AVID 标识任务。
        </p>
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
        <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm mt-5">
          <dt class="text-muted">任务编号</dt>
          <dd class="text-secondary">{{ selected.id }}</dd>
          <dt class="text-muted">最近更新</dt>
          <dd class="text-secondary">{{ selected.updated }}</dd>
        </dl>
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
        JSON.stringify({ type, state, selected, tasks }, null, 2)
      }}</pre>
    </details>
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
