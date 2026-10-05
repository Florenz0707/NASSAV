<script setup>
import { logger } from '../utils/logger.js'
import { computed, defineAsyncComponent, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import TaskDetailsPanel from '../components/TaskDetailsPanel.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import AppButton from '../components/AppButton.vue'
import { useResourceStore } from '../stores/resource'
import { useWebSocketStore } from '../stores/websocket'
import { useDownloadQueueStore } from '../stores/downloadQueue'
import { useSettingsStore } from '../stores/settings'
import { resourceApi, taskApi } from '../api'
import { buildTaskDetails } from '../utils/taskDetails.js'
import { createTaskDebugData } from '../utils/taskDebugData.js'

// Set true to preview synthetic download/scrape tasks. Real queue data is never mixed in.
const DEBUG_MODE = false
const route = useRoute()
const notificationDemo = computed(() => import.meta.env.DEV && route.query.demo === 'notifications')
const NotificationsDemo = import.meta.env.DEV
  ? defineAsyncComponent(() => import('../components/NotificationsDemo.vue'))
  : null
const debugTasks = ref(DEBUG_MODE ? createTaskDebugData() : [])
const resourceStore = useResourceStore(),
  wsStore = useWebSocketStore()
const queue = useDownloadQueueStore(),
  settings = useSettingsStore()
const queueError = ref('')
const tasks = computed(() =>
  DEBUG_MODE
    ? debugTasks.value
    : buildTaskDetails({
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
      if (task.type === 'scrape') resourceStore.dismissScrapeJob(task.taskId)
      else queue.dismissTasks([task.taskId || task.avid])
    }
  }
  dismissIds.value = []
}
const pollingTimer = ref(null)
let pollingGeneration = 0,
  pendingQueueGeneration = null
const POLLING_INTERVAL = 1000
onBeforeUnmount(stopPolling)
onMounted(() => {
  if (!DEBUG_MODE && !notificationDemo.value) fetchQueueStatus()
})
watch(
  [() => wsStore.connected, () => wsStore.connectionFailed, () => notificationDemo.value],
  ([connected, failed]) => {
    if (DEBUG_MODE || notificationDemo.value || connected) stopPolling()
    else if (failed) startPolling()
  },
  { immediate: true }
)
watch(notificationDemo, (show) => {
  if (!show && !DEBUG_MODE) fetchQueueStatus()
})
function advance(task) {
  if (!DEBUG_MODE) return
  if (task.state === 'failed' || task.state === 'succeeded') {
    Object.assign(task, { state: 'queued', error: '', percent: 0, stage: 'source_lookup' })
  } else if (task.state === 'queued') task.state = 'running'
  else if (task.type === 'download') {
    task.percent = Math.min(100, (task.percent || 0) + 20)
    if (task.percent === 100) task.state = 'succeeded'
  } else {
    const stages = ['source_lookup', 'metadata', 'cover', 'saving', 'translation_queued']
    const index = stages.indexOf(task.stage)
    if (index === stages.length - 1) task.state = 'succeeded'
    else task.stage = stages[index + 1]
  }
}
async function fetchQueueStatus() {
  if (pendingQueueGeneration === pollingGeneration || DEBUG_MODE || notificationDemo.value) return
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
  if (wsStore.connected || DEBUG_MODE || notificationDemo.value) {
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
    if (wsStore.connected || DEBUG_MODE || notificationDemo.value) {
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
  <NotificationsDemo v-if="notificationDemo" />
  <div v-else>
    <p v-if="queueError" class="text-accent-danger mb-4" role="alert">{{ queueError }}</p>
    <TaskDetailsPanel :tasks="tasks" :debug="DEBUG_MODE" @dismiss="requestDismiss">
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
          class="inline-flex mt-5 text-accent-primary"
          >查看资源</RouterLink
        >
      </template>
    </TaskDetailsPanel>
    <ConfirmDialog
      v-model:show="showDismiss"
      title="不再跟踪任务"
      :message="`不再跟踪所选 ${dismissIds.length} 个任务？后台任务仍会继续，不会取消任务或删除资源。`"
      confirm-text="不再跟踪"
      @confirm="dismiss"
    />
  </div>
</template>
