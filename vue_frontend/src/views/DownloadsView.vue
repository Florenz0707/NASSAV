<script setup>
import PageLoad from '../shared/ui/PageLoad.vue'
import RequestError from '../shared/ui/RequestError.vue'
import { useTaskJobsStore } from '../features/tasks/stores/taskJobs.js'
import { logger } from '../shared/lib/logger.js'
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import TaskDetailsPanel from '../features/tasks/components/TaskDetailsPanel.vue'
import ConfirmDialog from '../shared/ui/ConfirmDialog.vue'
import AppButton from '../shared/ui/AppButton.vue'
import { useResourceStore } from '../features/resources/stores/resource.js'
import { useWebSocketStore } from '../app/stores/websocket.js'
import { useDownloadQueueStore } from '../features/resources/stores/downloadQueue.js'
import { useSettingsStore } from '../features/settings/stores/settings.js'
import { resourceApi, taskApi } from '../api/index.js'
import { buildTaskDetails, resolveTaskFocus } from '../features/tasks/lib/taskDetails.js'
import { createTaskDebugData } from '../features/tasks/lib/taskDebugData.js'
import { SCRAPE_STAGE_LABELS } from '../features/tasks/stores/scrapeJobState.js'

// Set true to preview synthetic download/scrape tasks. Real queue data is never mixed in.
const DEBUG_MODE = false
const route = useRoute()
const debugTasks = ref(DEBUG_MODE ? createTaskDebugData() : [])
const resourceStore = useResourceStore(),
  wsStore = useWebSocketStore()
const queue = useDownloadQueueStore(),
  settings = useSettingsStore()
const taskJobs = useTaskJobsStore()
const queueError = ref('')
const tasks = computed(() =>
  DEBUG_MODE
    ? debugTasks.value
    : buildTaskDetails({
        jobs: taskJobs.visible,
        active: queue.activeTasks.filter(queue.isTracked),
        pending: queue.pendingTasks.filter(queue.isTracked),
        scrapeJobs: resourceStore.visibleScrapeJobs,
        resources: resourceStore.resources,
        metadataCache: queue.titleCache,
        preferredTitle: settings.displayTitle,
        coverUrlFor: (avid) => resourceApi.getCoverUrl(avid, 'medium'),
      })
)
const showDismiss = ref(false),
  dismissIds = ref([])
function requestDismiss(ids) {
  dismissIds.value = ids
  showDismiss.value = true
}
function dismiss() {
  if (DEBUG_MODE)
    debugTasks.value = debugTasks.value.filter((task) => !dismissIds.value.includes(task.id))
  else {
    for (const task of tasks.value.filter((task) => dismissIds.value.includes(task.id))) {
      if (task.jobId) taskJobs.hide([task.jobId])
      else if (task.type === 'scrape') resourceStore.dismissScrapeJob(task.taskId)
      else queue.dismissTasks([task.taskId || task.avid])
    }
  }
  dismissIds.value = []
}
const controlAction = ref(''),
  controlIds = ref([]),
  showCancel = ref(false)
const debugBusy = ref(new Set()),
  debugTimers = new Set()
function requestControl(action, ids) {
  controlAction.value = action
  controlIds.value = ids
  if (action === 'cancel') showCancel.value = true
  else executeControl()
}
async function executeControl() {
  const action = controlAction.value
  const selected = tasks.value.filter((task) => controlIds.value.includes(task.id))
  if (!DEBUG_MODE) {
    for (let start = 0; start < selected.length; start += 100)
      await taskJobs.control(
        action,
        selected.slice(start, start + 100).map((task) => task.jobId)
      )
    return
  }
  for (const task of selected) {
    debugBusy.value = new Set([...debugBusy.value, task.id])
    task.state =
      action === 'pause'
        ? 'pausing'
        : action === 'cancel'
          ? 'cancelling'
          : action === 'resume'
            ? 'queued'
            : task.state
    const timer = setTimeout(() => {
      debugTimers.delete(timer)
      if (action === 'pause') task.state = 'paused'
      if (action === 'cancel') {
        task.state = 'cancelled'
        task.cleanupState = 'completed'
      }
      if (action === 'cleanup_retry') task.cleanupState = 'completed'
      task.allowedActions =
        task.state === 'paused'
          ? ['resume', 'cancel']
          : ['queued', 'running'].includes(task.state)
            ? ['pause', 'cancel']
            : []
      task.timeline.push({
        label:
          action === 'cleanup_retry'
            ? '清理完成'
            : task.state === 'paused'
              ? '已暂停'
              : task.state === 'cancelled'
                ? '已终止'
                : '任务已排队',
        at: Date.now() / 1000,
      })
      debugBusy.value = new Set([...debugBusy.value].filter((id) => id !== task.id))
    }, 600)
    debugTimers.add(timer)
  }
}
onBeforeUnmount(() => {
  for (const timer of debugTimers) clearTimeout(timer)
})
const pollingTimer = ref(null)
let pollingGeneration = 0,
  pendingQueueGeneration = null
const POLLING_INTERVAL = 1000
onBeforeUnmount(stopPolling)
onMounted(() => {
  if (!DEBUG_MODE) {
    fetchQueueStatus()
    taskJobs.load()
  }
})
watch(
  [() => wsStore.connected, () => wsStore.connectionFailed],
  ([connected, failed]) => {
    if (DEBUG_MODE || connected) stopPolling()
    else if (failed) startPolling()
  },
  { immediate: true }
)
function advance(task) {
  if (!DEBUG_MODE) return
  if (task.type === 'scrape') task.translation = undefined
  if (task.state === 'failed' || task.state === 'succeeded') {
    task.timeline = []
    Object.assign(task, { state: 'queued', error: '', percent: 0, stage: 'source_lookup' })
  } else if (task.state === 'queued') task.state = 'running'
  else if (task.type === 'download') {
    task.percent = Math.min(100, (task.percent || 0) + 20)
    if (task.percent === 100) task.state = 'succeeded'
  } else {
    const stages = [
      'source_lookup',
      'metadata',
      'cover',
      'saving',
      'translation_queued',
      'translation_translating',
      'translation_completed',
    ]
    const index = stages.indexOf(task.stage)
    task.stage = stages[Math.min(index + 1, stages.length - 1)]
    if (task.stage === 'translation_completed') task.state = 'succeeded'
  }
  task.timeline = [
    ...(task.timeline || []),
    {
      label:
        task.state === 'failed'
          ? '失败'
          : task.state === 'succeeded'
            ? task.type === 'scrape'
              ? '翻译完成'
              : '下载完成'
            : task.state === 'queued'
              ? '任务已排队'
              : task.type === 'scrape'
                ? SCRAPE_STAGE_LABELS[task.stage] || task.stage
                : '下载状态更新',
      at: Date.now() / 1000,
    },
  ]
}
async function fetchQueueStatus() {
  if (pendingQueueGeneration === pollingGeneration || DEBUG_MODE) return
  const generation = pollingGeneration
  pendingQueueGeneration = generation
  try {
    const response = await taskApi.getQueueStatus()
    const data = response.data
    if (data && generation === pollingGeneration) {
      // 通过 store 更新数据
      queue.updateTaskData(data)
      queueError.value = ''
    }
  } catch (error) {
    if (generation === pollingGeneration) {
      queueError.value = '无法更新下载队列，已显示的数据可能过期。'
      logger.debug('[DownloadsView] 队列读取失败', error.message)
    }
  } finally {
    if (pendingQueueGeneration === generation) pendingQueueGeneration = null
  }
}

// 开始轮询（仅在下载页且 WebSocket 未连接时使用）
function startPolling() {
  // 如果 WebSocket 已连接，不启动轮询
  if (wsStore.connected || DEBUG_MODE) {
    logger.debug('[DownloadsView] WebSocket 已连接，跳过轮询')
    return
  }

  // 先停止之前的轮询
  stopPolling()
  logger.debug('[DownloadsView] 启动 API 轮询')
  // 立即获取一次
  fetchQueueStatus()
  // 定时轮询
  pollingTimer.value = setInterval(() => {
    // 再次检查 WebSocket 状态，如果已连接则停止轮询
    if (wsStore.connected || DEBUG_MODE) {
      stopPolling()
      return
    }
    fetchQueueStatus()
  }, POLLING_INTERVAL)
}

// 停止轮询
function stopPolling() {
  pollingGeneration++
  if (pollingTimer.value) {
    logger.debug('[DownloadsView] 停止轮询')
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}
</script>
<template>
  <div class="flex flex-col min-h-[calc(100dvh-6rem)] min-[641px]:min-h-[calc(100dvh-8rem)]">
    <p
      v-if="
        route.query.task &&
        !tasks.some((task) => task.taskId === route.query.task || task.jobId === route.query.task)
      "
      class="text-muted mb-4"
    >
      该任务未被本浏览器跟踪，或已移出当前队列。
    </p>
    <RequestError v-if="queueError" :message="queueError" compact @retry="fetchQueueStatus" />
    <RequestError
      v-if="!DEBUG_MODE && (taskJobs.error || taskJobs.listError)"
      :message="taskJobs.error || taskJobs.listError"
      compact
      @retry="taskJobs.load()"
    />
    <div v-if="!DEBUG_MODE" class="flex items-center gap-3 mb-4 text-muted text-sm">
      <span
        >已加载 {{ taskJobs.jobs.size }} /
        {{ taskJobs.total }} 个持久任务（筛选及批量操作针对已加载列表）</span
      >
      <AppButton
        v-if="taskJobs.hasMore"
        variant="neutral"
        size="sm"
        :loading="taskJobs.loading"
        @click="taskJobs.load(true)"
        >加载更多</AppButton
      >
      <AppButton variant="neutral" size="sm" :loading="taskJobs.loading" @click="taskJobs.load()"
        >刷新列表</AppButton
      >
    </div>
    <PageLoad
      v-if="!DEBUG_MODE && taskJobs.loading && !tasks.length"
      variant="spinner"
      text="正在加载任务"
    />
    <TaskDetailsPanel
      v-else
      :tasks="tasks"
      :debug="DEBUG_MODE"
      :ordering="taskJobs.ordering"
      @sort="taskJobs.setOrdering"
      :busy="DEBUG_MODE ? debugBusy : taskJobs.busy"
      @control="requestControl"
      :focus-task-id="resolveTaskFocus(tasks, route.query.task)"
      @dismiss="requestDismiss"
    >
      <template #details="{ task }">
        <template v-if="DEBUG_MODE">
          <AppButton class="mt-5" @click="advance(task)">{{
            task.state === 'failed' ? '演示重试' : '演示下一阶段'
          }}</AppButton>
          <p class="text-muted text-xs mt-3">仅改变模拟状态，不操作真实任务。</p>
        </template>
        <RouterLink
          v-else-if="task.hasResource"
          :to="'/resource/' + encodeURIComponent(task.avid)"
          class="inline-flex items-center justify-center mt-5 px-4 py-2.5 rounded-xl bg-accent-primary text-on-accent font-semibold transition-colors hover:bg-accent-primary/80"
          >查看资源</RouterLink
        >
      </template>
    </TaskDetailsPanel>
    <ConfirmDialog
      v-model:show="showCancel"
      title="结束任务"
      :message="`终止所选 ${controlIds.length} 个任务？执行器确认停止后删除未提交的分片、封面和头像；已保存资源、正式视频和共享头像保留。`"
      confirm-text="结束任务"
      @confirm="executeControl"
    />
    <ConfirmDialog
      v-model:show="showDismiss"
      title="不再跟踪任务"
      :message="`不再跟踪所选 ${dismissIds.length} 个任务？后台任务仍会继续，不会取消任务或删除资源。`"
      confirm-text="不再跟踪"
      @confirm="dismiss"
    />
  </div>
</template>
