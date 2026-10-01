import { computed, ref } from 'vue'
import { sourceApi } from '../api/index.js'
import { useSettingsStore } from '../stores/settings.js'

export function useExternalSearchSources(entityType, settings = useSettingsStore()) {
  const externalSource = ref(settings.defaultExternalSearchSource || 'jable')
  const capabilities = ref([])
  const sourcesReady = ref(false)
  const sourcesError = ref('')
  const sourceOptions = computed(() =>
    capabilities.value
      .filter((item) => item[entityType])
      .map((item) => ({ value: item.source, label: item.label }))
  )
  const selectedCapability = computed(() =>
    capabilities.value.find((item) => item.source === externalSource.value)
  )
  async function loadSearchSources() {
    sourcesError.value = ''
    try {
      const loaded = await settings.loadSettings()
      if (loaded?.success === false) throw new Error('加载默认搜索源失败，请重试')
      externalSource.value = settings.defaultExternalSearchSource || 'jable'
      const response = await sourceApi.getSearchCapabilities()
      capabilities.value = response.data || []
      if (!sourceOptions.value.some((item) => item.value === externalSource.value)) {
        externalSource.value = sourceOptions.value[0]?.value || ''
        if (externalSource.value) sourcesError.value = '默认搜索源不可用，已切换到可用源'
      }
      sourcesReady.value = true
      if (!sourceOptions.value.length) sourcesError.value = '没有启用支持此搜索的外部源'
    } catch (error) {
      sourcesError.value = error.message || '加载搜索源失败'
    }
  }
  return {
    externalSource,
    sourceOptions,
    selectedCapability,
    sourcesReady,
    sourcesError,
    loadSearchSources,
  }
}

export function createSearchRequestGuard() {
  let version = 0
  return {
    begin: () => ++version,
    current: (request) => request === version,
    invalidate: () => {
      version++
    },
  }
}
