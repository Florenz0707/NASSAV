<script setup>
import { computed } from 'vue'
import { gcBlockerLabel } from '../lib/resourceAdministration.js'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppInput from '../../../shared/ui/AppInput.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
const props = defineProps({ admin: { type: Object, required: true }, canGc: Boolean })
const title = computed(() => {
  const editor = props.admin.editor
  if (!editor) return '资源管理'
  return {
    preview: '回收预览',
    availability: editor.row.is_available ? '下架资源' : '恢复资源访问',
    retention: editor.row.retained ? '取消保留' : '保留资源',
    retry: '重试失败回收',
  }[editor.action]
})
const explanation = computed(() => {
  const editor = props.admin.editor
  if (editor?.action === 'availability')
    return editor.row.is_available
      ? '下架会立即拒绝后续访问并关闭对应播放会话，影响持有该资源的所有用户；文件不会直接删除。'
      : '恢复资源访问后，仍需有效持有与版本授权；不会为任何用户新增持有。'
  if (editor?.action === 'retention')
    return editor.row.retained
      ? '取消保留后仍须满足宽限、持有、任务、播放及资产保护条件，不会立即删除文件。'
      : '保留会阻止回收。已经开始删除的资源不能通过此操作恢复。'
  if (editor?.action === 'retry')
    return '确认已处理失败原因后重试原回收记录。后台会重新核查占用和文件证据，不会把残缺版本恢复为可用。'
  return '预览只反映当前保护条件。排队和实际删除前会再次核查，不以任务结束或占用过期推测写入者已停止。'
})
const reasons = [
  { value: 'maintenance', label: '系统维护' },
  { value: 'security', label: '安全处理' },
  { value: 'user_request', label: '用户请求' },
  { value: 'quota_adjustment', label: '配额调整' },
]
</script>
<template>
  <SettingsModal
    :show="Boolean(admin.editor)"
    :title="title"
    :show-close="!admin.busy"
    max-width-class="max-w-2xl flex flex-col max-h-[calc(100dvh-2rem)]"
    content-class="min-h-0 flex-1 overflow-y-auto"
    @close="admin.close"
  >
    <form class="space-y-4" @submit.prevent="admin.prepare">
      <p class="text-primary break-all">{{ admin.editor?.row.avid || admin.editor?.row.job_id }}</p>
      <p class="text-secondary text-sm leading-relaxed">{{ explanation }}</p>
      <template v-if="admin.editor?.action === 'preview'">
        <AppInput
          label="版本 UUID（可选）"
          :model-value="admin.versionId"
          placeholder="留空预览整池；指定版本仅回收该版本"
          :disabled="admin.busy"
          @update:model-value="admin.setVersion"
        />
        <AppButton
          variant="neutral"
          :loading="admin.previewLoading"
          :disabled="admin.busy"
          @click="admin.loadPreview"
          >更新预览</AppButton
        >
        <PageLoad v-if="admin.previewLoading" variant="spinner" text="正在核查保护条件" />
        <div v-else-if="admin.preview" class="rounded-xl bg-primary p-4 space-y-3 text-sm">
          <p class="text-primary">
            {{ admin.preview.eligible ? '当前未发现阻塞条件' : '当前不可回收' }}
          </p>
          <p class="text-muted break-all">
            范围：{{ admin.preview.version_id || '整池' }} · 池版本 {{ admin.preview.pool_version }}
          </p>
          <ul v-if="admin.preview.blockers.length" class="list-disc pl-5 text-secondary space-y-1">
            <li v-for="blocker in admin.preview.blockers" :key="blocker">
              {{ gcBlockerLabel(blocker) }}
            </li>
          </ul>
        </div>
      </template>
      <p
        v-if="['preview', 'retry'].includes(admin.editor?.action) && !canGc"
        class="text-muted text-sm"
      >
        回收执行尚未开启；当前只可预览，不能排队或重试。
      </p>
      <div class="space-y-2">
        <label for="resource-admin-reason" class="text-primary">操作原因</label
        ><CustomSelect
          id="resource-admin-reason"
          :model-value="admin.reason"
          :options="reasons"
          :disabled="admin.busy"
          full-width
          @update:model-value="admin.setReason"
        />
      </div>
      <p v-if="admin.error" role="alert" class="text-accent-danger text-sm">{{ admin.error }}</p>
      <ul v-if="admin.blockers.length" class="text-secondary text-sm list-disc pl-5">
        <li v-for="blocker in admin.blockers" :key="blocker">{{ gcBlockerLabel(blocker) }}</li>
      </ul>
      <div class="flex justify-end gap-3">
        <AppButton variant="neutral" :disabled="admin.busy" @click="admin.close">关闭</AppButton
        ><AppButton
          type="submit"
          :loading="admin.busy"
          loading-text="登记中"
          :disabled="
            (['preview', 'retry'].includes(admin.editor?.action) && !canGc) ||
            (admin.editor?.action === 'preview' &&
              (!admin.preview?.eligible || admin.previewLoading))
          "
          >{{ admin.editor?.action === 'preview' ? '登记回收' : '下一步' }}</AppButton
        >
      </div>
    </form>
  </SettingsModal>
  <ConfirmDialog
    :show="admin.confirming"
    :title="'确认' + title"
    :message="explanation"
    confirm-text="确认执行"
    :type="
      ['preview', 'retry', 'availability'].includes(admin.editor?.action) ? 'danger' : 'warning'
    "
    @update:show="admin.setConfirming"
    @confirm="admin.confirm"
  />
</template>
