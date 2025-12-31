import {defineStore} from 'pinia'
import {ref} from 'vue'
import {resourceApi} from '../api'

export const useWebSocketStore = defineStore('websocket', () => {
    const ws = ref(null)
    const connected = ref(false)
    const reconnectTimer = ref(null)
    const connectionTimer = ref(null)

    const WS_RECONNECT_INTERVAL = 3000  // WebSocket 重连间隔
    const WS_CONNECTION_TIMEOUT = 5000  // WebSocket 连接超时时间

    // 任务状态数据
    const activeTasks = ref([])
    const pendingTasks = ref([])
    const activeCount = ref(0)
    const pendingCount = ref(0)
    const totalCount = ref(0)

    // 缓存已获取元数据的 avid，避免重复请求
    const metadataCache = ref(new Set())

    // 连接 WebSocket
    function connect() {
        // 如果已连接，不重复连接
        if (ws.value && connected.value) {
            return
        }

        // 如果有正在连接的 WebSocket，先关闭
        if (ws.value) {
            ws.value.close()
            ws.value = null
        }

        // 构建 WebSocket URL
        // 开发环境直接连接后端，生产环境使用当前域名
        let wsUrl
        if (import.meta.env.DEV) {
            // 开发环境：直接连接后端服务
            wsUrl = 'ws://localhost:8000/nassav/ws/tasks/'
        } else {
            // 生产环境：使用当前域名
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
            wsUrl = `${protocol}//${window.location.host}/nassav/ws/tasks/`
        }

        console.log('[WebSocket] 正在连接:', wsUrl)

        try {
            ws.value = new WebSocket(wsUrl)

            // 设置连接超时
            connectionTimer.value = setTimeout(() => {
                if (ws.value && ws.value.readyState === WebSocket.CONNECTING) {
                    console.warn('[WebSocket] 连接超时，关闭连接')
                    ws.value.close()
                    ws.value = null
                    connected.value = false
                    scheduleReconnect()
                }
            }, WS_CONNECTION_TIMEOUT)

            ws.value.onopen = () => {
                console.log('[WebSocket] 连接成功')
                connected.value = true
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

            ws.value.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data)
                    handleMessage(message)
                } catch (error) {
                    console.error('[WebSocket] 解析消息失败:', error)
                }
            }

            ws.value.onclose = (event) => {
                console.log('[WebSocket] 连接关闭:', event.code, event.reason)
                connected.value = false
                ws.value = null
                // 清除连接超时定时器
                if (connectionTimer.value) {
                    clearTimeout(connectionTimer.value)
                    connectionTimer.value = null
                }
                // 尝试重连
                scheduleReconnect()
            }

            ws.value.onerror = (error) => {
                console.error('[WebSocket] 错误:', error)
                connected.value = false
                // 清除连接超时定时器
                if (connectionTimer.value) {
                    clearTimeout(connectionTimer.value)
                    connectionTimer.value = null
                }
            }
        } catch (error) {
            console.error('[WebSocket] 创建连接失败:', error)
            connected.value = false
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
        if (connectionTimer.value) {
            clearTimeout(connectionTimer.value)
            connectionTimer.value = null
        }
        if (reconnectTimer.value) {
            clearTimeout(reconnectTimer.value)
            reconnectTimer.value = null
        }
        if (ws.value) {
            ws.value.close()
            ws.value = null
            connected.value = false
        }
    }

    // 计划 WebSocket 重连
    function scheduleReconnect() {
        if (reconnectTimer.value) {
            return  // 已有重连计划
        }

        reconnectTimer.value = setTimeout(() => {
            reconnectTimer.value = null
            console.log('[WebSocket] 尝试重新连接...')
            connect()
        }, WS_RECONNECT_INTERVAL)
    }

    // 处理 WebSocket 消息
    function handleMessage(message) {
        switch (message.type) {
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
                    const taskIndex = activeTasks.value.findIndex(t => t.task_id === taskId)
                    if (taskIndex !== -1) {
                        activeTasks.value[taskIndex].progress = {
                            percent: message.data.percent,
                            speed: message.data.speed
                        }
                    }
                }
                break

            case 'task_started':
            case 'task_completed':
            case 'task_failed':
                // 任务状态变化，数据通常包含完整队列状态
                if (message.data) {
                    updateTaskData(message.data)
                }
                break

            default:
                console.log('[WebSocket] 未知消息类型:', message.type)
        }
    }

    // 更新任务数据
    function updateTaskData(data) {
        activeTasks.value = data.active_tasks || []
        pendingTasks.value = data.pending_tasks || []
        activeCount.value = data.active_count || 0
        pendingCount.value = data.pending_count || 0
        totalCount.value = data.total_count || 0

        // 检查并补充缺失的元数据
        fetchMissingMetadata()
    }

    // 获取缺失的元数据
    async function fetchMissingMetadata() {
        const allTasks = [...activeTasks.value, ...pendingTasks.value]

        for (const task of allTasks) {
            // 如果任务没有 title 且还未获取过元数据
            if (!task.title && task.avid && !metadataCache.value.has(task.avid)) {
                // 标记为正在获取，避免重复请求
                metadataCache.value.add(task.avid)

                try {
                    console.log(`[WebSocket] 获取元数据: ${task.avid}`)
                    const response = await resourceApi.getMetadata(task.avid)
                    if (response.data && response.data.title) {
                        // 更新 activeTasks 中的任务
                        const activeIndex = activeTasks.value.findIndex(t => t.avid === task.avid)
                        if (activeIndex !== -1) {
                            activeTasks.value[activeIndex].title = response.data.title
                        }

                        // 更新 pendingTasks 中的任务
                        const pendingIndex = pendingTasks.value.findIndex(t => t.avid === task.avid)
                        if (pendingIndex !== -1) {
                            pendingTasks.value[pendingIndex].title = response.data.title
                        }
                    }
                } catch (error) {
                    console.error(`[WebSocket] 获取元数据失败 (${task.avid}):`, error)
                    // 失败后从缓存中移除，允许下次重试
                    metadataCache.value.delete(task.avid)
                }
            }
        }
    }

    return {
        // 连接状态
        connected,

        // 任务数据
        activeTasks,
        pendingTasks,
        activeCount,
        pendingCount,
        totalCount,

        // 方法
        connect,
        disconnect,
        updateTaskData
    }
})
