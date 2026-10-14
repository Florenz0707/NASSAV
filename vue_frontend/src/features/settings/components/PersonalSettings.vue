<script setup>
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { sourceApi } from '../../../api/index.js'
import { useToastStore } from '../../../shared/stores/toast.js'
import { useSettingsStore } from '../stores/settings.js'
import { AVAILABLE_FONTS } from '../config/fonts.js'
import PlaybackSettingsPanel from './PlaybackSettingsPanel.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import GeneralSettingsPanel from './GeneralSettingsPanel.vue'
const props = defineProps({ section: { type: String, default: 'all' }, embedded: Boolean })
let alive = true
onBeforeUnmount(() => {
  alive = false
})
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
  if (!alive) return
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
    if (props.section !== 'playback') settingsStore.fontFamily = previewFont.value
    const result = await settingsStore.saveSettings(props.section)
    if (!alive || !result.success) return
    toastStore.success('设置已保存')
  } catch (err) {
    if (alive) toastStore.error(err.message || '保存设置失败')
  } finally {
    saving.value = false
  }
}

// 组件挂载时加载数据
onMounted(async () => {
  void loadSettings()
  if (props.section !== 'playback') {
    try {
      const response = await sourceApi.getSearchCapabilities()
      if (!alive) return
      const enabled = new Set((response.data || []).map((item) => item.source))
      searchSourceOptions.value = searchSourceOptions.value.map((item) => ({
        ...item,
        label: enabled.has(item.value) ? item.label : `${item.label}（未启用）`,
      }))
    } catch {
      if (alive) toastStore.error('获取搜索源状态失败')
    }
  }
})
</script>
<template>
  <div class="settings-page">
    <div v-if="!embedded" class="mb-8">
      <h1 class="text-[2rem] font-bold text-primary mb-2">个人设置</h1>
      <p class="text-muted">当前账号的显示、搜索与播放偏好</p>
    </div>
    <h2 v-if="embedded" class="text-2xl font-semibold text-primary mb-6">
      {{ section === 'playback' ? '播放设置' : '通用设置' }}
    </h2>
    <PageLoad v-if="loading" variant="spinner" text="正在加载设置" />
    <RequestError v-else-if="loadError" :message="loadError" @retry="loadSettings" />
    <div v-else class="tw-surface-overlay rounded-xl p-6">
      <GeneralSettingsPanel
        v-if="section !== 'playback'"
        :show-save="false"
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
      <PlaybackSettingsPanel
        :heading-tag="embedded && section === 'playback' ? 'h2' : 'h3'"
        v-if="props.section !== 'general'"
        :model-value="settingsStore.playbackPreferences"
        @update:model-value="settingsStore.playbackPreferences = $event"
      />
      <div class="flex justify-end mt-6">
        <AppButton :loading="saving" loading-text="保存中" @click="handleSaveSettings"
          >保存设置</AppButton
        >
      </div>
    </div>
  </div>
</template>
