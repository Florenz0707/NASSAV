import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { resourceApi } from '../api/index.js'
import { useResourceStore } from './resource.js'
import { useSettingsStore } from './settings.js'
import { resolveResourceTitle } from '../utils/resourceTitle.js'

export const useDownloadQueueStore = defineStore('downloadQueue', () => {
  const activeTasks = ref([]),
    pendingTasks = ref([])
  const activeCount = ref(0),
    pendingCount = ref(0),
    totalCount = ref(0)
  const ignoredTaskIds = ref(new Set())
  const IGNORED_KEY = 'nassav:ignored-download-tasks:v1'
  try {
    const saved = JSON.parse(globalThis.localStorage?.getItem(IGNORED_KEY) || '[]')
    if (Array.isArray(saved))
      ignoredTaskIds.value = new Set(saved.filter((id) => typeof id === 'string').slice(-500))
  } catch {
    /* Ignore invalid browser state. */
  }
  function isTracked(task) {
    return !ignoredTaskIds.value.has(task.task_id || task.avid)
  }
  function dismissTasks(ids) {
    ignoredTaskIds.value = new Set([...ignoredTaskIds.value, ...ids].slice(-500))
    globalThis.localStorage?.setItem(IGNORED_KEY, JSON.stringify([...ignoredTaskIds.value]))
  }
  const titleCache = ref(new Map())
  const settings = useSettingsStore()
  let metadataGeneration = 0
  function cachedTitleFor(avid) {
    const entry = titleCache.value.get(avid)
    return entry ? resolveResourceTitle(entry.metadata, settings.displayTitle) : null
  }
  watch(
    () => settings.displayTitle,
    () => fetchMissingMetadata()
  )
  // 更新任务数据
  function updateTaskData(data) {
    if (
      !data ||
      (!Array.isArray(data.active_tasks) &&
        !Array.isArray(data.pending_tasks) &&
        typeof data.active_count === 'undefined' &&
        typeof data.pending_count === 'undefined' &&
        typeof data.total_count === 'undefined')
    ) {
      return
    }

    const resourceStore = useResourceStore()
    // 更新任务列表时，先从缓存应用标题
    activeTasks.value = (data.active_tasks || []).map((task) => {
      const cachedTitle = cachedTitleFor(task.avid)
      const finalTitle = cachedTitle || task.title || null
      return {
        ...task,
        title: finalTitle,
      }
    })

    pendingTasks.value = (data.pending_tasks || []).map((task) => {
      const cachedTitle = cachedTitleFor(task.avid)
      const finalTitle = cachedTitle || task.title || null
      return {
        ...task,
        title: finalTitle,
      }
    })

    activeCount.value = data.active_count || 0
    pendingCount.value = data.pending_count || 0
    totalCount.value = data.total_count || 0

    resourceStore.syncDownloadingAvids([
      ...activeTasks.value.map((task) => task.avid),
      ...pendingTasks.value.map((task) => task.avid),
    ])

    // 检查并补充缺失的元数据
    fetchMissingMetadata()
  }

  // 正在获取元数据的 AVID 集合（避免重复请求）
  const fetchingMetadata = ref(new Set())

  // 获取缺失的元数据
  async function fetchMissingMetadata() {
    const generation = metadataGeneration
    const allTasks = [...activeTasks.value, ...pendingTasks.value]
    for (const task of allTasks) {
      if (!task.avid || fetchingMetadata.value.has(task.avid)) continue
      const cached = titleCache.value.get(task.avid)
      if (cached) {
        updateTaskTitle(task.avid, cachedTitleFor(task.avid))
        continue
      }

      fetchingMetadata.value.add(task.avid)
      try {
        const response = await resourceApi.getMetadata(task.avid)
        if (generation !== metadataGeneration || !response.data) return
        titleCache.value.set(task.avid, { metadata: response.data, timestamp: Date.now() })
        updateTaskTitle(task.avid, cachedTitleFor(task.avid))
      } catch {
        /* The next queue snapshot can retry metadata. */
      } finally {
        fetchingMetadata.value.delete(task.avid)
      }
    }
  }

  // 辅助函数：更新指定 AVID 的标题
  function updateTaskTitle(avid, title) {
    const activeIndex = activeTasks.value.findIndex((t) => t.avid === avid)
    if (activeIndex !== -1) {
      activeTasks.value[activeIndex].title = title
    }

    const pendingIndex = pendingTasks.value.findIndex((t) => t.avid === avid)
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

  // 仅在连接生命周期内清理缓存；退出登录后停止定时器。
  let cleanupTimer = null
  function startTracking() {
    if (!cleanupTimer) cleanupTimer = setInterval(cleanupCache, 10 * 60 * 1000)
  }
  function stopTracking() {
    metadataGeneration++
    if (cleanupTimer) clearInterval(cleanupTimer)
    cleanupTimer = null
  }

  return {
    activeTasks,
    pendingTasks,
    activeCount,
    pendingCount,
    totalCount,
    titleCache,
    isTracked,
    dismissTasks,
    updateTaskData,
    fetchMissingMetadata,
    startTracking,
    stopTracking,
  }
})
