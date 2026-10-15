import { logger } from '../../shared/lib/logger.js'
import { defineStore, storeToRefs } from 'pinia'
import { useDownloadQueueStore } from '../../features/resources/stores/downloadQueue.js'
import { ref, shallowRef } from 'vue'
import { useToastStore } from '../../shared/stores/toast.js'
import { useUserOperationsStore } from '../../features/tasks/stores/userOperations.js'
import { useTaskJobsStore } from '../../features/tasks/stores/taskJobs.js'
import { useResourceStore } from '../../features/resources/stores/resource.js'
import { useSessionStore } from '../../features/auth/stores/session.js'
import { notifySearchJobUpdate } from '../../features/external-search/composables/searchJobEvents.js'

export function taskWebSocketUrl(location) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/nassav/ws/tasks/`
}

export const useWebSocketStore = defineStore('websocket', () => {
  const ws = shallowRef(null)
  const connected = ref(false)
  const connectionFailed = ref(false) // 标记是否发生过连接失败或超时
  const reconnectTimer = ref(null)
  const connectionTimer = ref(null)
  const shouldReconnect = ref(false)

  const WS_RECONNECT_INTERVAL = 3000 // WebSocket 重连间隔
  const WS_CONNECTION_TIMEOUT = 5000 // WebSocket 连接超时时间

  const queue = useDownloadQueueStore()
  const { activeTasks, pendingTasks, activeCount, pendingCount, totalCount, titleCache } =
    storeToRefs(queue)
  const updateTaskData = queue.updateTaskData

  // 连接 WebSocket
  function connect() {
    if (useSessionStore().status !== 'authenticated') return
    if (!useSessionStore().capabilities.shared_library) queue.startTracking()
    shouldReconnect.value = true
    // 如果已连接，不重复连接
    if (ws.value && (connected.value || ws.value.readyState === WebSocket.CONNECTING)) {
      return
    }

    // 如果有正在连接的 WebSocket，先关闭
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }

    // The page host is also the WebSocket origin in development and production.
    const wsUrl = taskWebSocketUrl(window.location)

    logger.debug('[WebSocket] 正在连接:', wsUrl)

    try {
      const session = useSessionStore()
      const socket = session.capabilities.ordinary_login
        ? new WebSocket(wsUrl, ['nassav.tasks.v1', `nassav.context.${session.identity}`])
        : new WebSocket(wsUrl)
      ws.value = socket

      // 设置连接超时
      connectionTimer.value = setTimeout(() => {
        if (ws.value === socket && socket.readyState === WebSocket.CONNECTING) {
          console.warn('[WebSocket] 连接超时，关闭连接')
          socket.close()
          ws.value = null
          connected.value = false
          connectionFailed.value = true // 标记连接失败
          scheduleReconnect()
        }
      }, WS_CONNECTION_TIMEOUT)

      socket.onopen = () => {
        if (ws.value !== socket) return
        logger.debug('[WebSocket] 连接成功')
        connected.value = true
        connectionFailed.value = false
        if (useSessionStore().capabilities.shared_library) {
          useUserOperationsStore().poll(true)
          useUserOperationsStore().load()
        } else {
          useResourceStore().refreshPendingScrapeJobs()
          useTaskJobsStore().poll(true)
          useTaskJobsStore().load()
        }
        // 清除连接超时定时器
        if (connectionTimer.value) {
          clearTimeout(connectionTimer.value)
          connectionTimer.value = null
        }
        // 清除重连定时器
        if (reconnectTimer.value) {
          clearTimeout(reconnectTimer.value)
          reconnectTimer.value = null
        }
      }

      socket.onmessage = (event) => {
        if (ws.value !== socket) return
        try {
          const message = JSON.parse(event.data)
          handleMessage(message)
        } catch (error) {
          console.error('[WebSocket] 解析消息失败:', error)
        }
      }

      socket.onclose = async (event) => {
        if (ws.value !== socket) return
        logger.debug('[WebSocket] 连接关闭:', event.code, event.reason)
        connected.value = false
        connectionFailed.value = true // 标记连接失败
        ws.value = null
        // 清除连接超时定时器
        if (connectionTimer.value) {
          clearTimeout(connectionTimer.value)
          connectionTimer.value = null
        }
        if (event.code === 4401) {
          shouldReconnect.value = false
          const session = useSessionStore(),
            identity = session.identity
          if (session.capabilities.ordinary_login) {
            if (await session.recheck()) {
              shouldReconnect.value = true
              if (!ws.value) scheduleReconnect()
            } else if (session.identity === identity) session.expire()
          } else session.expire()
        } else if (event.code === 4403) {
          shouldReconnect.value = false
        } else if (await useSessionStore().recheck()) {
          // Failed handshakes often appear as 1006, so verify the HTTP session.
          if (!ws.value) scheduleReconnect()
        }
      }

      socket.onerror = (error) => {
        if (ws.value !== socket) return
        console.error('[WebSocket] 错误:', error)
        connected.value = false
        connectionFailed.value = true // 标记连接失败
        // Keep the connection timeout: some browsers do not deliver onclose promptly.
      }
    } catch (error) {
      console.error('[WebSocket] 创建连接失败:', error)
      connected.value = false
      connectionFailed.value = true // 标记连接失败
      // 清除连接超时定时器
      if (connectionTimer.value) {
        clearTimeout(connectionTimer.value)
        connectionTimer.value = null
      }
      // 尝试重连
      scheduleReconnect()
    }
  }

  // 断开 WebSocket
  function disconnect() {
    shouldReconnect.value = false
    if (connectionTimer.value) {
      clearTimeout(connectionTimer.value)
      connectionTimer.value = null
    }
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value)
      reconnectTimer.value = null
    }
    queue.stopTracking()
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    connected.value = false
    connectionFailed.value = false
  }

  // 计划 WebSocket 重连
  function scheduleReconnect() {
    if (!shouldReconnect.value || useSessionStore().status !== 'authenticated') return
    if (reconnectTimer.value) {
      return // 已有重连计划
    }

    reconnectTimer.value = setTimeout(() => {
      reconnectTimer.value = null
      logger.debug('[WebSocket] 尝试重新连接...')
      connect()
    }, WS_RECONNECT_INTERVAL)
  }

  // 处理 WebSocket 消息
  function handleMessage(message) {
    const toastStore = useToastStore()
    const resourceStore = useResourceStore()

    if (message.type === 'user_operation_update') {
      if (useSessionStore().capabilities.shared_library) useUserOperationsStore().hint(message.data)
      return
    }
    if (useSessionStore().capabilities.shared_library && message.type !== 'external_search_update')
      return
    switch (message.type) {
      case 'external_search_update':
        notifySearchJobUpdate(message.data)
        break
      case 'task_job_update':
        useTaskJobsStore().hint(message.data)
        break
      case 'scrape_job_update':
        resourceStore.handleScrapeJobEvent(message.data)
        break
      case 'queue_status':
        // 队列状态更新
        if (message.data) {
          updateTaskData(message.data)
        }
        break

      case 'progress_update':
        // 进度更新 - 更新对应任务的进度
        if (message.data) {
          const taskId = message.data.task_id
          const taskIndex = activeTasks.value.findIndex((t) => t.task_id === taskId)
          if (taskIndex !== -1) {
            activeTasks.value[taskIndex].progress = {
              percent: message.data.percent,
              speed: message.data.speed,
              downloaded: message.data.downloaded,
              total: message.data.total,
            }
          }
        }
        break

      case 'task_started':
        // 任务开始
        if (message.data) {
          const avid = message.data.avid
          if (avid) {
            toastStore.info(`开始下载: ${avid}`)
            resourceStore.setDownloadState(avid, 'downloading')
          }
          updateTaskData(message.data)
        }
        break

      case 'task_completed':
        // 任务完成
        if (message.data) {
          const avid = message.data.avid
          if (avid) {
            toastStore.success(`下载完成: ${avid}`)
            // 立即更新资源的下载状态
            resourceStore.updateResourceDownloadStatus(avid, true)
          }
          updateTaskData(message.data)
        }
        break

      case 'task_failed':
        // 任务失败
        if (message.data) {
          const avid = message.data.avid
          const error = message.data.error || '未知错误'
          if (avid) {
            toastStore.error(`下载失败: ${avid} - ${error}`)
            resourceStore.clearDownloadState(avid)
          }
          updateTaskData(message.data)
        }
        break

      default:
        logger.debug('[WebSocket] 未知消息类型:', message.type)
    }
  }

  return {
    // 连接状态
    connected,
    connectionFailed,

    // 任务数据
    activeTasks,
    pendingTasks,
    activeCount,
    pendingCount,
    totalCount,

    // 缓存（供调试）
    titleCache,

    // 方法
    connect,
    disconnect,
    updateTaskData,
  }
})
