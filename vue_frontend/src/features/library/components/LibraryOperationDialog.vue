<script setup>
import { computed, onScopeDispose, ref, watch } from 'vue'
import { sourceApi } from '../../../api/sources.js'
import { useLibraryCommandsStore } from '../stores/commands.js'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'

const commands = useLibraryCommandsStore()
const source = ref(''),
  mode = ref('public'),
  sources = ref([]),
  loading = ref(false),
  loadError = ref('')
const labels = { add: '添加资源', refresh: '刷新资源', download: '下载视频' }
const title = computed(() => labels[commands.intent?.action] || '资源操作')
let revision = 0
onScopeDispose(() => revision++)
async function loadSources() {
  const current = ++revision
  loading.value = true
  loadError.value = ''
  try {
    const response = await sourceApi.getList()
    if (current !== revision || !commands.intent) return
    sources.value = (response.data || []).map((item) => ({
      value: item.toLowerCase(),
      label: item,
    }))
    if (!sources.value.some((item) => item.value === source.value))
      source.value = sources.value[0]?.value || ''
  } catch (error) {
    if (current === revision) loadError.value = error.message || '无法加载来源'
  } finally {
    if (current === revision) loading.value = false
  }
}
watch(
  () => commands.intent,
  (value) => {
    revision++
    if (!value) return
    source.value = value.source?.toLowerCase() || ''
    mode.value = 'public'
    loadSources()
  },
  { immediate: true }
)
</script>
<template>
  <SettingsModal
    :show="Boolean(commands.intent)"
    :title="title"
    :show-close="!commands.busy"
    max-width-class="max-w-lg flex flex-col max-h-[calc(100dvh-2rem)]"
    content-class="min-h-0 flex-1 overflow-y-auto"
    @close="commands.close"
  >
    <p class="text-secondary mb-4 break-words">
      {{ commands.intent?.avids.slice(0, 3).join('、')
      }}{{
        (commands.intent?.avids.length || 0) > 3 ? ` 等 ${commands.intent.avids.length} 个资源` : ''
      }}
    </p>
    <PageLoad v-if="loading" variant="spinner" text="正在加载来源" />
    <RequestError v-else-if="loadError" :message="loadError" compact @retry="loadSources" />
    <form
      v-else
      class="space-y-4"
      @submit.prevent="commands.confirm({ source, credential_mode: mode })"
    >
      <div class="space-y-2">
        <label for="operation-source" class="text-primary">来源</label
        ><CustomSelect
          id="operation-source"
          v-model="source"
          :options="sources"
          :disabled="commands.busy"
          full-width
        />
      </div>
      <div class="space-y-2">
        <label for="operation-mode" class="text-primary">来源凭证</label
        ><CustomSelect
          id="operation-mode"
          v-model="mode"
          :options="[
            { value: 'public', label: '默认凭证' },
            { value: 'personal', label: '个人凭证' },
          ]"
          :disabled="commands.busy"
          full-width
        />
      </div>
      <p class="text-muted text-sm">选择用于访问来源网站的凭证。刷新会重新获取完整来源和元数据。</p>
      <p v-if="commands.error" role="alert" class="text-accent-danger text-sm">
        {{ commands.error }}
      </p>
      <div class="flex justify-end gap-3">
        <AppButton variant="neutral" :disabled="commands.busy" @click="commands.close"
          >取消</AppButton
        ><AppButton type="submit" :disabled="!source" :loading="commands.busy" loading-text="提交中"
          >确认提交</AppButton
        >
      </div>
    </form>
  </SettingsModal>
</template>
