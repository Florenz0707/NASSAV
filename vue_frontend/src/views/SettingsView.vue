<script setup>
import PageLoad from '../shared/ui/PageLoad.vue'
import RequestError from '../shared/ui/RequestError.vue'
import { ref, onMounted } from 'vue'
import { sourceApi } from '../api/index.js'
import { useToastStore } from '../shared/stores/toast.js'
import { useSettingsStore } from '../features/settings/stores/settings.js'
import { AVAILABLE_FONTS } from '../features/settings/config/fonts.js'
import GeneralSettingsPanel from '../features/settings/components/GeneralSettingsPanel.vue'
const toastStore = useToastStore()
const settingsStore = useSettingsStore()
// 字体预览（临时变量，用于预览效果）
const previewFont = ref('Mplus2')
const loading = ref(true),
  loadError = ref(''),
  saving = ref(false)
async function loadSettings() {
  loading.value = true
  loadError.value = ''
  const result = await settingsStore.loadSettings()
  if (result.success) previewFont.value = settingsStore.fontFamily
  else loadError.value = result.error?.message || '设置加载失败'
  loading.value = false
}
const displayTitleOptions = [
  { value: 'translated_title', label: '翻译标题' },
  { value: 'source_title', label: '源站标题' },
  { value: 'original_title', label: '原始标题' },
]
const searchResultDisplayOptions = [
  { value: 'grid', label: '标准网格' },
  { value: 'masonry', label: '两列瀑布流' },
]

const searchSourceOptions = ref([
  { value: 'jable', label: 'Jable' },
  { value: 'missav', label: 'MissAV' },
])
// 保存设置
const handleSaveSettings = async () => {
  if (saving.value) return
  saving.value = true
  try {
    // 应用预览字体到全局设置
    settingsStore.fontFamily = previewFont.value
    const result = await settingsStore.saveSettings()
    if (!result.success) return
    toastStore.success('设置已保存')
  } catch (err) {
    toastStore.error(err.message || '保存设置失败')
  } finally {
    saving.value = false
  }
}

// 组件挂载时加载数据
onMounted(async () => {
  try {
    const response = await sourceApi.getSearchCapabilities()
    const enabled = new Set((response.data || []).map((item) => item.source))
    searchSourceOptions.value = searchSourceOptions.value.map((item) => ({
      ...item,
      label: enabled.has(item.value) ? item.label : `${item.label}（未启用）`,
    }))
  } catch {
    toastStore.error('获取搜索源状态失败')
  }
  await loadSettings()
})
</script>
<template>
  <div class="settings-page">
    <div class="mb-8">
      <h1 class="text-[2rem] font-bold text-primary mb-2">个人设置</h1>
      <p class="text-muted">当前账号的显示、搜索与播放偏好</p>
    </div>
    <PageLoad v-if="loading" variant="spinner" text="正在加载设置" />
    <RequestError v-else-if="loadError" :message="loadError" @retry="loadSettings" />
    <div v-else class="tw-surface-overlay rounded-xl p-6">
      <GeneralSettingsPanel
        :settings="settingsStore"
        :saving="saving"
        :preview-font="previewFont"
        :display-title-options="displayTitleOptions"
        :search-result-display-options="searchResultDisplayOptions"
        :available-fonts="AVAILABLE_FONTS"
        :search-source-options="searchSourceOptions"
        @update-setting="(field, value) => (settingsStore[field] = value)"
        @update:preview-font="previewFont = $event"
        @save="handleSaveSettings"
      />
    </div>
  </div>
</template>
