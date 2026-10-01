import { computed, ref } from 'vue'
import { sourceApi } from '../api/index.js'

export function useExternalSearchSources(entityType, storage = globalThis.sessionStorage) {
  const preferenceKey = 'external_search_source'
  const externalSource = ref(storage?.getItem(preferenceKey) || 'jable')
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
      const response = await sourceApi.getSearchCapabilities()
      capabilities.value = response.data || []
      if (!sourceOptions.value.some((item) => item.value === externalSource.value)) {
        externalSource.value = sourceOptions.value[0]?.value || ''
      }
      sourcesReady.value = true
      if (!sourceOptions.value.length) sourcesError.value = '没有启用支持此搜索的外部源'
    } catch (error) {
      sourcesError.value = error.message || '加载搜索源失败'
    }
  }
  function rememberSource() {
    storage?.setItem(preferenceKey, externalSource.value)
  }
  return {
    externalSource,
    sourceOptions,
    selectedCapability,
    sourcesReady,
    sourcesError,
    loadSearchSources,
    rememberSource,
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
