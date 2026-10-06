<script setup>
// Presentation only: task snapshots are supplied by DownloadsView.
import { computed, ref, watch } from 'vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppIcon from '../../../shared/ui/AppIcon.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
import ResourceCover from '../../../shared/ui/ResourceCover.vue'
import TaskCheckbox from './TaskCheckbox.vue'
import TaskTimeline from './TaskTimeline.vue'
import { TASK_STAGE_LABELS, isFinishedTask, sortTaskDetails } from '../lib/taskDetails.js'
const emit = defineEmits(['dismiss', 'control', 'sort'])
const props = defineProps({
  tasks: { type: Array, required: true },
  debug: Boolean,
  ordering: { type: String, default: '-created_at' },
  busy: { type: Set, default: () => new Set() },
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
const labels = {
  queued: '等待中',
  running: '执行中',
  pausing: '暂停中',
  paused: '已暂停',
  cancelling: '终止中',
  cancelled: '已终止',
  succeeded: '已完成',
  failed: '失败',
}
const canControl = (task, action) =>
  task.allowedActions?.includes(action) && !props.busy.has(task.jobId || task.id)
const selectedFor = (action) =>
  props.tasks
    .filter((task) => checkedIds.value.has(task.id) && canControl(task, action))
    .map((task) => task.id)
const hideFinished = (task) =>
  isFinishedTask(task) && !['pending', 'running', 'failed'].includes(task.cleanupState)
const cleanupLabels = {
  pending: '等待清理',
  running: '正在清理',
  completed: '清理完成',
  failed: '清理失败',
  not_required: '无需清理',
}
const stageLabels = TASK_STAGE_LABELS
const typeTasks = computed(() =>
  props.tasks.filter((t) => type.value === 'all' || t.type === type.value)
)
const visible = computed(() =>
  sortTaskDetails(
    typeTasks.value.filter((t) => state.value === 'all' || t.state === state.value),
    props.ordering
  )
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
  ['paused', 'pausing', 'cancelling', 'cancelled'].includes(task.state)
    ? labels[task.state]
    : task.state === 'failed'
      ? task.stage === 'translation_failed'
        ? '翻译失败'
        : '失败'
      : task.state === 'queued'
        ? '尚未开始'
        : task.type === 'download'
          ? task.percent === null
            ? '等待进度'
            : `${task.percent}%`
          : task.state === 'succeeded'
            ? stageLabels[task.stage] || '已完成'
            : stageLabels[task.stage] || '阶段待获取'
</script>
<template>
  <div class="min-w-0" :class="visible.length ? 'pb-24' : 'flex flex-col flex-1'">
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
        v-for="(label, key) in Object.fromEntries(
          Object.entries(labels).filter(([key]) =>
            ['queued', 'running', 'succeeded', 'failed'].includes(key)
          )
        )"
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
        class="min-w-[8rem] shrink-0"
        aria-label="任务状态"
        :options="[
          { value: 'all', label: '全部状态' },
          ...Object.entries(labels).map(([value, label]) => ({ value, label })),
        ]"
      />
      <CustomSelect
        :model-value="ordering"
        @update:model-value="emit('sort', $event)"
        aria-label="任务排序"
        class="min-w-[12rem] shrink-0"
        :options="[
          { value: '-created_at', label: '最近创建' },
          { value: '-updated_at', label: '最近更新' },
        ]"
      />
    </div>
    <div class="flex flex-wrap items-center gap-3 mb-4">
      <AppButton
        variant="neutral"
        :disabled="checkedIds.size === 0"
        @click="emit('dismiss', [...checkedIds])"
        >不再跟踪所选</AppButton
      >
      <AppButton
        variant="neutral"
        :disabled="!visible.some((task) => hideFinished(task))"
        @click="
          emit(
            'dismiss',
            visible.filter((task) => hideFinished(task)).map((task) => task.id)
          )
        "
        >不再跟踪已结束任务</AppButton
      >
      <AppButton
        variant="neutral"
        :disabled="!selectedFor('pause').length"
        @click="emit('control', 'pause', selectedFor('pause'))"
        >暂停所选</AppButton
      >
      <AppButton
        variant="neutral"
        :disabled="!selectedFor('resume').length"
        @click="emit('control', 'resume', selectedFor('resume'))"
        >恢复所选</AppButton
      >
      <AppButton
        variant="danger"
        :disabled="!selectedFor('cancel').length"
        @click="emit('control', 'cancel', selectedFor('cancel'))"
        >结束所选任务</AppButton
      >
    </div>
    <div
      v-if="!visible.length"
      class="flex-1 flex items-center justify-center"
      aria-label="任务列表空白区域"
    >
      <EmptyState compact title="暂无任务" />
    </div>
    <div v-else class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-6 items-start">
      <div
        class="overflow-x-auto bg-secondary border rounded-xl min-w-0 border-[var(--border-color)]"
      >
        <table class="w-full text-sm">
          <caption class="text-left p-4 text-secondary">
            {{
              visible.length
            }}
            个任务 · 点击任务查看明细
          </caption>
          <thead>
            <tr class="border-b text-secondary border-[var(--border-color)]">
              <th class="p-4 w-24 text-left align-middle">
                <div class="flex items-center gap-2">
                  <TaskCheckbox
                    :checked="allChecked"
                    label="选择当前列表全部任务"
                    :indeterminate="!allChecked && visible.some((task) => checkedIds.has(task.id))"
                    @change="checkAll"
                  />
                  <span
                    role="status"
                    :aria-label="'已选择 ' + checkedIds.size + ' 个任务'"
                    class="w-6 shrink-0 text-muted text-xs font-medium tabular-nums"
                    >{{ checkedIds.size }}</span
                  >
                </div>
              </th>
              <th class="p-4 text-left">任务</th>
              <th v-if="type === 'all'" class="p-4 text-center">类型</th>
              <th class="p-4 text-left">状态</th>
              <th class="p-4 text-left">阶段</th>
              <th class="p-4 text-center whitespace-nowrap">不再跟踪</th>
              <th class="p-4 text-center whitespace-nowrap">暂停/恢复</th>
              <th class="p-4 text-center whitespace-nowrap">结束任务</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="task in visible"
              :key="task.id"
              class="border-b hover:bg-surface-subtle/5 border-[var(--border-color)]"
              :class="selected?.id === task.id ? 'bg-accent-primary/10' : ''"
            >
              <td class="p-4 w-24 text-left align-middle">
                <TaskCheckbox
                  :checked="checkedIds.has(task.id)"
                  :label="'选择任务 ' + task.avid"
                  @change="check(task.id, $event)"
                />
              </td>
              <td class="p-4">
                <button
                  class="flex items-center gap-3 w-full text-primary text-left min-w-[50px]"
                  :aria-label="resourceName(task) + '，查看任务明细'"
                  :aria-pressed="selected?.id === task.id"
                  @click="selectedId = task.id"
                >
                  <span class="min-w-0">
                    <span class="block font-medium">{{ task.avid }}</span>
                  </span>
                </button>
              </td>
              <td v-if="type === 'all'" class="p-4 text-center">
                <span
                  class="inline-flex items-center px-2.5 py-1 rounded-lg border text-xs font-medium text-primary"
                  :class="
                    task.type === 'scrape'
                      ? 'bg-accent-purple/20 border-accent-purple/50'
                      : 'bg-accent-info/20 border-accent-info/50'
                  "
                  >{{ task.type }}</span
                >
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
                  v-if="task.type === 'download' && task.state === 'running'"
                  class="text-muted text-xs"
                  >{{ task.speed }}</span
                >
              </td>
              <td class="p-4 text-center">
                <AppButton
                  size="sm"
                  variant="neutral"
                  class="w-9 h-9 p-0"
                  :aria-label="'不再跟踪任务 ' + task.avid"
                  title="不再跟踪此任务"
                  @click="emit('dismiss', [task.id])"
                  ><AppIcon name="eye-off"
                /></AppButton>
              </td>
              <td class="p-4 text-center">
                <AppButton
                  size="sm"
                  variant="neutral"
                  class="w-9 h-9 p-0"
                  :disabled="!canControl(task, task.state === 'paused' ? 'resume' : 'pause')"
                  :aria-label="(task.state === 'paused' ? '恢复任务 ' : '暂停任务 ') + task.avid"
                  :title="task.jobId || debug ? '暂停保留文件，恢复继续执行' : '历史任务不支持控制'"
                  @click="emit('control', task.state === 'paused' ? 'resume' : 'pause', [task.id])"
                  ><AppIcon :name="task.state === 'paused' ? 'play' : 'pause'"
                /></AppButton>
              </td>
              <td class="p-4 text-center">
                <AppButton
                  size="sm"
                  variant="danger"
                  class="w-9 h-9 p-0"
                  :disabled="!canControl(task, 'cancel')"
                  :aria-label="'结束任务 ' + task.avid"
                  :title="task.jobId || debug ? '终止执行并清理未提交文件' : '历史任务不支持控制'"
                  @click="emit('control', 'cancel', [task.id])"
                  ><AppIcon name="close"
                /></AppButton>
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
        <ResourceCover
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
        <TaskTimeline :events="selected.timeline || []" />
        <p v-if="selected.error" class="text-accent-danger text-sm mt-4" role="alert">
          {{ selected.error }}
        </p>
        <div v-if="selected.cleanupState" class="mt-4 text-sm text-secondary" role="status">
          {{ cleanupLabels[selected.cleanupState] || '清理状态未知' }}
          <p v-if="selected.cleanupMessage" class="text-accent-danger mt-2">
            {{ selected.cleanupMessage }}
          </p>
          <AppButton
            v-if="selected.allowedActions?.includes('cleanup_retry')"
            class="mt-3"
            size="sm"
            :disabled="!canControl(selected, 'cleanup_retry')"
            @click="emit('control', 'cleanup_retry', [selected.id])"
            >重试清理</AppButton
          >
        </div>
        <p
          v-if="['pausing', 'cancelling'].includes(selected.state)"
          class="text-muted text-sm mt-4"
        >
          正在等待执行器确认停止，文件暂不删除。
        </p>
        <p
          v-if="selected.errorCode === 'RESTART_REQUIRED'"
          class="text-accent-warning text-sm mt-4"
        >
          临时文件无法安全复用，请终止后重新创建任务。
        </p>
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
