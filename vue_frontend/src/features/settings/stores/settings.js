import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settingsApi } from '../../../api/index.js'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'

export const useSettingsStore = defineStore('settings', () => {
  // 是否显示女优头像
  const showActorAvatar = ref(true)

  // 显示哪个标题字段：original_title | source_title | translated_title
  const displayTitle = ref('source_title')

  // 字体样式：Mplus2 | TheWriteRight | ZenKakuGothicNew
  const fontFamily = ref('Mplus2')

  // 主题模式：light | dark
  const colorMode = ref('dark')

  // 推荐搜索结果展示样式：grid | masonry
  const searchResultDisplayStyle = ref('grid')
  const defaultExternalSearchSource = ref('jable')
  const recommendationPreferences = ref({
    type_preference: 'balanced',
    actor_preference: 'balanced',
    genre_preference: 'balanced',
    limit: 12,
  })
  const loaded = ref(false)
  let loadPromise = null
  let sessionEpoch = 0
  const loadGuard = createRequestGuard()
  const saveGuard = createRequestGuard()
  let savedValues = settingsPayload()

  function settingsPayload() {
    return {
      ...Object.fromEntries(
        Object.entries(recommendationPreferences.value).map(([key, value]) => [
          `recommendation_${key}`,
          value,
        ])
      ),
      enable_avatar: showActorAvatar.value ? 'true' : 'false',
      display_title: displayTitle.value,
      font_family: fontFamily.value,
      color_mode: colorMode.value,
      search_result_display_style: searchResultDisplayStyle.value,
      default_external_search_source: defaultExternalSearchSource.value,
    }
  }

  function reset() {
    sessionEpoch++
    loadGuard.invalidate()
    saveGuard.invalidate()
    loadPromise = null
    loaded.value = false
    recommendationPreferences.value = {
      type_preference: 'balanced',
      actor_preference: 'balanced',
      genre_preference: 'balanced',
      limit: 12,
    }
    showActorAvatar.value = true
    displayTitle.value = 'source_title'
    fontFamily.value = 'Mplus2'
    colorMode.value = 'dark'
    searchResultDisplayStyle.value = 'grid'
    defaultExternalSearchSource.value = 'jable'
    savedValues = settingsPayload()
  }

  // 从后端加载设置（仅在应用启动时调用一次）
  async function loadSettings(force = false) {
    if (loaded.value && !force) {
      return { success: true, cached: true }
    }
    if (loadPromise && !force) {
      return loadPromise
    }

    const ticket = loadGuard.begin()
    loadPromise = (async () => {
      try {
        const response = await settingsApi.get()
        if (!loadGuard.current(ticket)) return { success: false, ignored: true }
        const data = response.data || {}

        // 后端返回的 enable_avatar 是字符串 "true"/"false"
        if (data.enable_avatar !== undefined) {
          showActorAvatar.value = data.enable_avatar === 'true'
        }
        if (data.display_title !== undefined) {
          displayTitle.value = data.display_title
        }
        if (data.font_family !== undefined) {
          fontFamily.value = data.font_family
        }
        if (data.color_mode !== undefined) {
          colorMode.value = data.color_mode
        }
        if (data.search_result_display_style !== undefined) {
          searchResultDisplayStyle.value = data.search_result_display_style
        }
        if (data.default_external_search_source !== undefined) {
          defaultExternalSearchSource.value = data.default_external_search_source
        }
        for (const key of Object.keys(recommendationPreferences.value)) {
          if (data[`recommendation_${key}`] !== undefined)
            recommendationPreferences.value[key] = data[`recommendation_${key}`]
        }
        savedValues = settingsPayload()
        loaded.value = true
        return { success: true }
      } catch (err) {
        if (!loadGuard.current(ticket)) return { success: false, ignored: true }
        console.error('加载用户设置失败:', err)
        return { success: false, error: err }
      } finally {
        if (loadGuard.current(ticket)) loadPromise = null
      }
    })()

    try {
      return await loadPromise
    } catch (err) {
      return { success: false, error: err }
    }
  }

  // 保存设置到后端（仅在用户手动点击保存按钮时调用）
  async function saveSettings() {
    const epoch = sessionEpoch
    const current = settingsPayload()
    const changes = Object.fromEntries(
      Object.entries(current).filter(([key, value]) => value !== savedValues[key])
    )
    if (!Object.keys(changes).length) return { success: true, unchanged: true }
    const ticket = saveGuard.begin()
    try {
      await settingsApi.update(changes)
      if (epoch !== sessionEpoch || !saveGuard.current(ticket))
        return { success: false, ignored: true }
      savedValues = { ...savedValues, ...changes }
      return { success: true }
    } catch (err) {
      if (epoch !== sessionEpoch || !saveGuard.current(ticket))
        return { success: false, ignored: true }
      console.error('保存用户设置失败:', err)
      throw err
    }
  }

  return {
    showActorAvatar,
    displayTitle,
    fontFamily,
    colorMode,
    searchResultDisplayStyle,
    defaultExternalSearchSource,
    recommendationPreferences,
    loaded,
    reset,
    loadSettings,
    saveSettings,
  }
})
