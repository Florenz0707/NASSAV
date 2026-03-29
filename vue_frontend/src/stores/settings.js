import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settingsApi } from '../api'

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
  const loaded = ref(false)
  let loadPromise = null

  // 从后端加载设置（仅在应用启动时调用一次）
  async function loadSettings(force = false) {
    if (loaded.value && !force) {
      return { success: true, cached: true }
    }
    if (loadPromise && !force) {
      return loadPromise
    }

    loadPromise = (async () => {
      try {
        const response = await settingsApi.get()
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
        loaded.value = true
        return { success: true }
      } catch (err) {
        console.error('加载用户设置失败:', err)
        throw err
      } finally {
        loadPromise = null
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
    try {
      await settingsApi.update({
        enable_avatar: showActorAvatar.value ? 'true' : 'false',
        display_title: displayTitle.value,
        font_family: fontFamily.value,
        color_mode: colorMode.value,
        search_result_display_style: searchResultDisplayStyle.value,
      })
      return { success: true }
    } catch (err) {
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
    loaded,
    loadSettings,
    saveSettings,
  }
})
