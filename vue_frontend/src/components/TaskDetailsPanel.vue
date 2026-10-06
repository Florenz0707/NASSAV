<script setup>
// Presentation only: task snapshots are supplied by DownloadsView.
import { computed, ref, watch } from 'vue'
import AppButton from './AppButton.vue'
import AppIcon from './AppIcon.vue'
import CustomSelect from './CustomSelect.vue'
import EmptyState from './EmptyState.vue'
import TaskResourceCover from './TaskResourceCover.vue'
import { SCRAPE_STAGE_LABELS } from '../stores/scrapeJobState.js'
const emit = defineEmits(['dismiss'])
const props = defineProps({
  tasks: { type: Array, required: true },
  debug: Boolean,
  focusTaskId: { type: String, default: '' },
})
const type = ref('all'),
  state = ref('all'),
  selectedId = ref(null)
watch(
  () => props.focusTaskId,
  (id) => {
    if (id) {
      selectedId.value = id
      type.value = 'all'
      state.value = 'all'
    }
  },
  { immediate: true }
)
const labels = { queued: '等待中', running: '执行中', succeeded: '已完成', failed: '失败' }
const stageLabels = SCRAPE_STAGE_LABELS
const translationLabels = {
  queued: '翻译已排队',
  translating: '正在翻译',
  completed: '翻译成功',
  failed: '翻译失败',
  skipped: '翻译已跳过',
  not_requested: '未请求翻译',
  unavailable: '翻译结果未记录或已过期',
  unknown: '翻译状态暂不可用',
}
const typeTasks = computed(() =>
  props.tasks.filter((t) => type.value === 'all' || t.type === type.value)
)
const visible = computed(() =>
  typeTasks.value.filter((t) => state.value === 'all' || t.state === state.value)
)
const checkedIds = ref(new Set())
watch(
  () => props.tasks.map((task) => task.id),
  (ids) => {
    checkedIds.value = new Set([...checkedIds.value].filter((id) => ids.includes(id)))
  }
)
const allChecked = computed(
  () => visible.value.length > 0 && visible.value.every((task) => checkedIds.value.has(task.id))
)
function check(taskId, value) {
  const next = new Set(checkedIds.value)
  if (value) next.add(taskId)
  else next.delete(taskId)
  checkedIds.value = next
}
function checkAll(value) {
  visible.value.forEach((task) => check(task.id, value))
}
const selected = computed(
  () => visible.value.find((t) => t.id === selectedId.value) || visible.value[0]
)
const count = (s) => typeTasks.value.filter((t) => t.state === s).length
const resourceName = (task) => task.title || task.avid
const taskType = (task) =>
  task.type === 'download' ? '下载' : task.action === 'refresh' ? '刷新资源' : '新增资源'
const progress = (task) =>
  task.state === 'failed'
    ? '失败'
    : task.state === 'queued'
      ? '尚未开始'
      : task.type === 'download'
        ? task.percent === null
          ? '等待进度'
          : `${task.percent}%`
        : task.state === 'succeeded'
          ? '已完成'
          : stageLabels[task.stage] || '阶段待获取'
</script>
<template>
  <div class="pb-24 min-w-0">
    <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <div>
        <h1 class="text-3xl font-bold text-primary">任务详情</h1>
        <p class="text-secondary mt-2">统一查看下载与刮削的状态、进度和失败原因</p>
      </div>
      <span
        v-if="debug"
        class="text-accent-warning border border-accent-warning/30 rounded-lg px-3 py-2 text-sm"
        >DEBUG · 模拟数据</span
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
    <div class="flex flex-wrap items-center gap-3 mb-4">
      <AppButton
        variant="neutral"
        :disabled="checkedIds.size === 0"
        @click="emit('dismiss', [...checkedIds])"
        >不再跟踪所选 ({{ checkedIds.size }})</AppButton
      >
      <AppButton
        variant="neutral"
        :disabled="!visible.some((task) => ['succeeded', 'failed'].includes(task.state))"
        @click="
          emit(
            'dismiss',
            visible
              .filter((task) => ['succeeded', 'failed'].includes(task.state))
              .map((task) => task.id)
          )
        "
        >不再跟踪当前列表已结束任务</AppButton
      >
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
              <th class="p-4">
                <input
                  type="checkbox"
                  :checked="allChecked"
                  aria-label="选择当前列表全部任务"
                  @change="checkAll($event.target.checked)"
                />
              </th>
              <th class="p-4 text-left">任务</th>
              <th class="p-4 text-left">状态</th>
              <th class="p-4 text-left">阶段</th>
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
                <input
                  type="checkbox"
                  :checked="checkedIds.has(task.id)"
                  :aria-label="'选择任务 ' + task.avid"
                  @change="check(task.id, $event.target.checked)"
                />
              </td>
              <td class="p-4">
                <button
                  class="flex items-center gap-3 w-full text-primary text-left min-w-[240px]"
                  :aria-label="resourceName(task) + '，查看任务明细'"
                  :aria-pressed="selected?.id === task.id"
                  @click="selectedId = task.id"
                >
                  <TaskResourceCover
                    :url="task.coverUrl"
                    :scene="debug ? task.coverScene : ''"
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
                {{ labels[task.state] || '状态未知' }}
              </td>
              <td class="p-4 text-secondary whitespace-nowrap">
                <span class="block">{{ progress(task) }}</span>
                <span
                  v-if="task.translation"
                  class="block text-xs mt-1"
                  :class="task.translation.state === 'failed' ? 'text-accent-danger' : 'text-muted'"
                  >{{ translationLabels[task.translation.state] }}</span
                >
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
        <TaskResourceCover
          :url="selected.coverUrl"
          :scene="debug ? selected.coverScene : ''"
          :title="resourceName(selected)"
          class="w-full aspect-video mb-4"
        />
        <h3 class="text-primary font-medium break-words">{{ resourceName(selected) }}</h3>
        <p class="text-muted text-sm mt-2">
          {{ selected.avid }} · {{ taskType(selected) }} ·
          {{ labels[selected.state] || '状态未知' }}
        </p>
        <template v-if="selected.type === 'download'"
          ><progress
            v-if="selected.percent !== null"
            :value="selected.percent"
            max="100"
            class="w-full mt-5"
            aria-label="下载进度"
          />
          <p class="text-secondary text-sm mt-2">
            {{ progress(selected) }} · {{ selected.speed || '—' }}
          </p>
          <p class="text-muted text-xs mt-2">
            {{ selected.downloaded || '0 MB' }} / {{ selected.total || '体积待获取' }}
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
        <div
          v-if="selected.translation"
          class="mt-4 text-sm"
          :class="selected.translation.state === 'failed' ? 'text-accent-danger' : 'text-secondary'"
        >
          <p>{{ translationLabels[selected.translation.state] }}</p>
          <p v-if="selected.translation.message" class="text-xs mt-1">
            {{ selected.translation.message }}
          </p>
        </div>
        <AppButton variant="neutral" class="mt-5" @click="emit('dismiss', [selected.id])"
          >不再跟踪此任务</AppButton
        >
        <slot name="details" :task="selected" />
      </aside>
    </div>
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
