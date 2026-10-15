<script setup>
import { computed, onMounted, ref } from 'vue'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppInput from '../../../shared/ui/AppInput.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
import { usePersonalCredentials } from '../composables/usePersonalCredentials.js'

const emit = defineEmits(['close'])
const {
  sources,
  selected,
  credential,
  cookie,
  cookieError,
  userAgent,
  userAgentError,
  kind,
  loading,
  busy,
  action,
  error,
  message,
  load,
  save,
} = usePersonalCredentials()
const confirmRevoke = ref(false),
  confirmDiscard = ref(false)
const kinds = [
  { value: 'account', label: '个人账号 Cookie' },
  { value: 'clearance', label: '仅访问验证 Cookie' },
]
const stateLabel = computed(
  () =>
    ({ active: '已保存', revoked: '已撤销', quarantined: '待审核' })[credential.value?.state] ||
    '尚未设置'
)
const updated = computed(() => {
  const date = new Date(credential.value?.updated_at)
  return Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN') : '未记录'
})
function close() {
  if (busy.value) return
  if (cookie.value || userAgent.value) confirmDiscard.value = true
  else emit('close')
}
onMounted(load)
</script>
<template>
  <SettingsModal
    :show="true"
    title="个人来源凭证"
    max-width-class="max-w-2xl flex flex-col max-h-[calc(100dvh-2rem)]"
    content-class="min-h-0 flex-1 overflow-y-auto"
    :show-close="!busy"
    @close="close"
  >
    <p class="text-sm text-secondary mb-6">
      仅管理当前账号的来源 Cookie。保存后不会回显，也不会自动提升为公共凭证。
    </p>
    <PageLoad v-if="loading && !sources.length" variant="spinner" text="加载个人来源凭证" />
    <RequestError v-else-if="error && !sources.length" :message="error" compact @retry="load" />
    <EmptyState
      v-else-if="!sources.length"
      title="暂无可用来源"
      description="请先配置来源后再试"
      compact
    />
    <form v-else class="space-y-4" @submit.prevent="save()">
      <div>
        <label for="credential-source" class="block text-sm text-secondary mb-2">来源</label>
        <CustomSelect
          id="credential-source"
          v-model="selected"
          :options="sources"
          :disabled="busy || loading"
          full-width
        />
      </div>
      <dl
        class="rounded-xl bg-primary p-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm"
      >
        <dt class="text-muted">状态</dt>
        <dd class="text-primary">{{ stateLabel }}</dd>
        <dt class="text-muted">最近更新</dt>
        <dd class="text-primary break-words">{{ updated }}</dd>
        <dt class="text-muted">版本</dt>
        <dd class="text-primary">{{ credential?.version || '尚未保存' }}</dd>
      </dl>
      <div>
        <label for="credential-kind" class="block text-sm text-secondary mb-2">凭证类型</label>
        <CustomSelect
          id="credential-kind"
          v-model="kind"
          :options="kinds"
          :disabled="busy || loading"
          full-width
        />
      </div>
      <div>
        <label for="personal-cookie" class="block text-sm text-secondary mb-2">新的 Cookie</label>
        <AppInput
          id="personal-cookie"
          v-model="cookie"
          multiline
          :rows="5"
          autocomplete="off"
          spellcheck="false"
          placeholder="粘贴当前来源的 Cookie；已保存内容不会回显"
          :disabled="busy || loading"
          :error="cookieError"
        />
      </div>
      <div>
        <label for="personal-user-agent" class="block text-sm text-secondary mb-2"
          >配套 User-Agent</label
        >
        <AppInput
          id="personal-user-agent"
          v-model="userAgent"
          :error="userAgentError"
          autocomplete="off"
          placeholder="粘贴与 Cookie 配套的浏览器 User-Agent"
          :disabled="busy || loading"
        />
        <p class="text-xs text-muted mt-2">
          Cookie 与 User-Agent 必须配套填写。输入只保留在本次弹窗中，关闭后清空。
        </p>
      </div>
      <p v-if="error" role="alert" class="text-sm text-accent-danger">{{ error }}</p>
      <p v-if="message" role="status" class="text-sm text-secondary">{{ message }}</p>
      <div class="flex flex-wrap justify-between gap-3">
        <AppButton
          variant="neutral"
          :disabled="busy"
          :loading="loading"
          loading-text="加载中"
          @click="load"
          >重新加载</AppButton
        >
        <div class="flex flex-wrap gap-3">
          <AppButton
            variant="danger"
            :loading="busy && action === 'revoke'"
            loading-text="撤销中"
            :disabled="busy || loading || !credential || credential.state === 'revoked'"
            @click="confirmRevoke = true"
            >撤销</AppButton
          >
          <AppButton
            type="submit"
            :loading="busy && action === 'save'"
            loading-text="保存中"
            :disabled="busy || loading || !selected"
            >保存</AppButton
          >
        </div>
      </div>
    </form>
    <template #footer
      ><div class="flex justify-end">
        <AppButton variant="neutral" :disabled="busy" @click="close">关闭</AppButton>
      </div></template
    >
  </SettingsModal>
  <ConfirmDialog
    v-model:show="confirmRevoke"
    title="撤销个人凭证"
    message="撤销后，使用该凭证的旧请求与来源缓存将失效。确定撤销吗？"
    confirm-text="撤销"
    type="danger"
    @confirm="save(true)"
  />
  <ConfirmDialog
    v-model:show="confirmDiscard"
    title="尚未保存"
    message="当前输入尚未保存，关闭后将丢弃。"
    confirm-text="放弃并关闭"
    @confirm="emit('close')"
  />
</template>
