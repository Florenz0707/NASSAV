import {defineStore} from 'pinia'
import {ref} from 'vue'
import {resourceApi} from '../api'
import {useSettingsStore} from './settings'
import {useToastStore} from './toast'
import {useResourceStore} from './resource'

export const useWebSocketStore = defineStore('websocket', () => {
    const ws = ref(null)
    const connected = ref(false)
    const connectionFailed = ref(false)  // 标记是否发生过连接失败或超时
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

    // 缓存已获取的标题数据，避免重复请求和标题闪烁
    // Map<avid, { title: string, timestamp: number }>
    const titleCache = ref(new Map())

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
            wsUrl = 'ws://localhost:9790/nassav/ws/tasks/'
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
                    connectionFailed.value = true  // 标记连接失败
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
                connectionFailed.value = true  // 标记连接失败
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
                connectionFailed.value = true  // 标记连接失败
                // 清除连接超时定时器
                if (connectionTimer.value) {
                    clearTimeout(connectionTimer.value)
                    connectionTimer.value = null
                }
            }
        } catch (error) {
            console.error('[WebSocket] 创建连接失败:', error)
            connected.value = false
            connectionFailed.value = true  // 标记连接失败
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
        if (cleanupTimer) {
            clearInterval(cleanupTimer)
            cleanupTimer = null
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
        const toastStore = useToastStore()
        const resourceStore = useResourceStore()

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
                // 任务开始
                if (message.data) {
                    const avid = message.data.avid
                    if (avid) {
                        toastStore.info(`开始下载: ${avid}`)
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
                    }
                    updateTaskData(message.data)
                }
                break

            default:
                console.log('[WebSocket] 未知消息类型:', message.type)
        }
    }

    // 更新任务数据
    function updateTaskData(data) {
        // 更新任务列表时，先从缓存应用标题
        activeTasks.value = (data.active_tasks || []).map(task => {
            const cachedTitle = titleCache.value.get(task.avid)?.title
            const finalTitle = task.title || cachedTitle || null
            console.log(`[WebSocket] 更新任务 ${task.avid}:`, {
                taskTitle: task.title,
                cachedTitle,
                finalTitle
            })
            return {
                ...task,
                title: finalTitle
            }
        })

        pendingTasks.value = (data.pending_tasks || []).map(task => {
            const cachedTitle = titleCache.value.get(task.avid)?.title
            const finalTitle = task.title || cachedTitle || null
            return {
                ...task,
                title: finalTitle
            }
        })

        activeCount.value = data.active_count || 0
        pendingCount.value = data.pending_count || 0
        totalCount.value = data.total_count || 0

        // 检查并补充缺失的元数据
        fetchMissingMetadata()
    }

    // 正在获取元数据的 AVID 集合（避免重复请求）
    const fetchingMetadata = ref(new Set())

    // 获取缺失的元数据
    async function fetchMissingMetadata() {
        const allTasks = [...activeTasks.value, ...pendingTasks.value]
        const settingsStore = useSettingsStore()

        for (const task of allTasks) {
            // 如果任务没有 title 且缓存中也没有，且当前没有正在获取
            if (!task.title && task.avid && !titleCache.value.has(task.avid) && !fetchingMetadata.value.has(task.avid)) {
                // 标记为正在获取
                fetchingMetadata.value.add(task.avid)

                try {
                    console.log(`[WebSocket] 获取元数据: ${task.avid}`)
                    const response = await resourceApi.getMetadata(task.avid)

                    if (response.data) {
                        const data = response.data
                        const titleField = settingsStore.displayTitle

                        console.log(`[WebSocket] 收到元数据响应 (${task.avid}):`, {
                            original_title: data.original_title,
                            source_title: data.source_title,
                            translated_title: data.translated_title,
                            titleField
                        })

                        // 根据设置获取标题
                        let displayTitle = ''
                        if (titleField === 'original_title' && data.original_title) {
                            displayTitle = data.original_title
                        } else if (titleField === 'source_title' && data.source_title) {
                            displayTitle = data.source_title
                        } else if (titleField === 'translated_title' && data.translated_title) {
                            displayTitle = data.translated_title
                        } else {
                            // 降级逻辑
                            displayTitle = data.translated_title || data.source_title || data.original_title || data.title || task.avid
                        }

                        console.log(`[WebSocket] 选择的标题 (${task.avid}): ${displayTitle}`)

                        // 存入缓存
                        titleCache.value.set(task.avid, {
                            title: displayTitle,
                            timestamp: Date.now()
                        })

                        // 立即更新当前任务列表
                        updateTaskTitle(task.avid, displayTitle)
                    }
                } catch (error) {
                    console.error(`[WebSocket] 获取元数据失败 (${task.avid}):`, error)
                    // 失败后不存入缓存，允许下次重试
                } finally {
                    // 移除正在获取标记
                    fetchingMetadata.value.delete(task.avid)
                }
            }
        }
    }

    // 辅助函数：更新指定 AVID 的标题
    function updateTaskTitle(avid, title) {
        const activeIndex = activeTasks.value.findIndex(t => t.avid === avid)
        if (activeIndex !== -1) {
            activeTasks.value[activeIndex].title = title
        }

        const pendingIndex = pendingTasks.value.findIndex(t => t.avid === avid)
        if (pendingIndex !== -1) {
            pendingTasks.value[pendingIndex].title = title
        }
    }

    // 定期清理过期缓存（超过 1 小时的条目）
    function cleanupCache() {
        const now = Date.now()
        const maxAge = 60 * 60 * 1000 // 1 小时

        for (const [avid, data] of titleCache.value.entries()) {
            if (now - data.timestamp > maxAge) {
                titleCache.value.delete(avid)
            }
        }
    }

    // 每 10 分钟清理一次过期缓存
    let cleanupTimer = setInterval(cleanupCache, 10 * 60 * 1000)

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
        updateTaskData
    }
})
