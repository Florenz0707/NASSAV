<script setup>
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import AppInput from '../../../shared/ui/AppInput.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
defineProps({ admin: { type: Object, required: true } })
const reasons = [
  { value: 'maintenance', label: '系统维护' },
  { value: 'security', label: '安全处理' },
  { value: 'user_request', label: '用户请求' },
]
</script>
<template>
  <SettingsModal
    :show="Boolean(admin.editor)"
    :title="admin.editor?.revoke ? '撤销系统凭证' : '系统访问验证凭证'"
    :show-close="!admin.busy"
    max-width-class="max-w-2xl flex flex-col max-h-[calc(100dvh-2rem)]"
    content-class="min-h-0 flex-1 overflow-y-auto"
    @close="admin.close"
  >
    <form class="space-y-4" @submit.prevent="admin.prepare">
      <p class="text-secondary text-sm">
        仅允许访问验证 Cookie。账号、会员或付费权限 Cookie 应保存在个人凭证中，不能提升为公共访问。
      </p>
      <p v-if="admin.editor?.row" class="text-primary">
        {{ admin.editor.row.source_name }} · {{ admin.editor.row.origin_host }} · 版本
        {{ admin.editor.row.version }}
      </p>
      <div v-else class="space-y-2">
        <label for="system-credential-source" class="text-primary">来源</label>
        <CustomSelect
          id="system-credential-source"
          :model-value="admin.draft.source"
          :options="admin.sources"
          :disabled="admin.busy"
          full-width
          @update:model-value="admin.setField('source', $event)"
        />
        <p v-if="admin.errors.source" class="text-accent-danger text-sm">
          {{ admin.errors.source }}
        </p>
      </div>
      <template v-if="!admin.editor?.revoke">
        <AppInput
          label="新的访问验证 Cookie"
          :model-value="admin.draft.cookie"
          multiline
          :rows="5"
          :maxlength="32768"
          autocomplete="off"
          spellcheck="false"
          placeholder="仅填写 cf_clearance、__cf_bm 或 __cflb；已保存内容不回显"
          :disabled="admin.busy"
          :error="admin.errors.cookie"
          @update:model-value="admin.setField('cookie', $event)"
        />
        <AppInput
          label="配套 User-Agent"
          :model-value="admin.draft.userAgent"
          :maxlength="2048"
          autocomplete="off"
          placeholder="填写与验证 Cookie 配套的 User-Agent"
          :disabled="admin.busy"
          :error="admin.errors.userAgent"
          @update:model-value="admin.setField('userAgent', $event)"
        />
      </template>
      <p v-else class="text-secondary text-sm">
        撤销后，依赖此系统凭证的来源请求、缓存及播放授权将失效，不影响个人凭证的独立归属。
      </p>
      <div class="space-y-2">
        <label for="system-credential-reason" class="text-primary">操作原因</label>
        <CustomSelect
          id="system-credential-reason"
          :model-value="admin.draft.reason"
          :options="reasons"
          :disabled="admin.busy"
          full-width
          @update:model-value="admin.setField('reason', $event)"
        />
        <p v-if="admin.errors.reason" class="text-accent-danger text-sm">
          {{ admin.errors.reason }}
        </p>
      </div>
      <p v-if="admin.error" role="alert" class="text-accent-danger text-sm">{{ admin.error }}</p>
      <div class="flex justify-end gap-3">
        <AppButton variant="neutral" :disabled="admin.busy" @click="admin.close">关闭</AppButton>
        <AppButton type="submit" :loading="admin.busy" loading-text="处理中">下一步</AppButton>
      </div>
    </form>
  </SettingsModal>
  <ConfirmDialog
    :show="admin.confirming"
    :title="admin.editor?.revoke ? '确认撤销系统凭证' : '确认保存系统凭证'"
    :message="
      admin.editor?.revoke
        ? '依赖此凭证的公共来源操作会失效，确定撤销吗？'
        : '确认该内容仅用于访问验证，并作为系统凭证供公共来源操作使用？保存后不会回显。'
    "
    confirm-text="确认执行"
    :type="admin.editor?.revoke ? 'danger' : 'warning'"
    @update:show="admin.setConfirming"
    @confirm="admin.confirm"
  />
  <ConfirmDialog
    :show="admin.discarding"
    title="尚未保存"
    message="关闭会清空当前凭证输入，是否继续？"
    confirm-text="放弃输入"
    @update:show="admin.setDiscarding"
    @confirm="admin.clear"
  />
</template>
