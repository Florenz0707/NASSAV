<script setup>
import { computed } from 'vue'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppInput from '../../../shared/ui/AppInput.vue'
import AppCheckbox from '../../../shared/ui/AppCheckbox.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'

const props = defineProps({ admin: { type: Object, required: true } })
const action = computed(() => props.admin.editor?.action)
const title = computed(
  () =>
    ({
      create: '创建账号',
      update: '编辑账号',
      revoke_sessions: '撤销登录会话',
      reset_password: '重置密码',
    })[action.value] || '账号操作'
)
const reasonOptions = [
  { value: 'maintenance', label: '系统维护' },
  { value: 'security', label: '安全处理' },
  { value: 'user_request', label: '用户请求' },
  { value: 'quota_adjustment', label: '配额调整' },
]
const confirmation = computed(() => {
  const name = props.admin.editor?.account?.username || props.admin.draft.username
  if (action.value === 'create')
    return `创建账号 ${name}，角色为${props.admin.draft.role === 'admin' ? '管理员' : '普通用户'}？登录开放策略仍由服务端控制。`
  if (action.value === 'reset_password') return `重置 ${name} 的密码并撤销其现有登录及播放会话？`
  if (action.value === 'revoke_sessions')
    return `撤销 ${name} 的登录及播放会话？其持有的资源将保留。`
  if (!props.admin.draft.is_active && props.admin.editor?.account?.is_active)
    return `停用 ${name}？将撤销登录和个人来源凭证、移出其持有并撤销该用户的任务请求，其他用户仍需要的共享工作会保留。`
  if (props.admin.draft.is_active && props.admin.editor?.account?.is_active === false)
    return `启用 ${name}？此前移出的资源和已撤销的来源凭证不会自动恢复。`
  return `修改 ${name} 的账号策略？角色变化会撤销该用户的现有登录及播放会话。`
})
</script>
<template>
  <SettingsModal
    :show="Boolean(admin.editor)"
    :title="title"
    :show-close="!admin.busy"
    max-width-class="max-w-xl flex flex-col max-h-[calc(100dvh-2rem)]"
    content-class="min-h-0 flex-1 overflow-y-auto"
    @close="admin.close"
  >
    <form class="space-y-6" @submit.prevent="admin.prepare">
      <p v-if="admin.editor?.account" class="text-secondary">
        {{ admin.editor.account.username }} · #{{ admin.editor.account.user_id }}
      </p>
      <AppInput
        v-if="action === 'create'"
        :model-value="admin.draft.username"
        @update:model-value="admin.setField('username', $event)"
        label="用户名"
        placeholder="填写新账号的用户名"
        autocomplete="off"
        :maxlength="150"
        :error="admin.fieldErrors.username"
        :disabled="admin.busy"
      />
      <AppInput
        v-if="['create', 'reset_password'].includes(action)"
        :model-value="admin.draft.password"
        @update:model-value="admin.setField('password', $event)"
        type="password"
        label="新密码"
        placeholder="填写至少12位的新密码"
        autocomplete="new-password"
        :maxlength="256"
        :error="admin.fieldErrors.password"
        :disabled="admin.busy"
      />
      <template v-if="['create', 'update'].includes(action)">
        <div class="space-y-2">
          <label for="account-role" class="text-primary">应用角色</label>
          <CustomSelect
            id="account-role"
            :model-value="admin.draft.role"
            @update:model-value="admin.setField('role', $event)"
            :options="[
              { value: 'user', label: '普通用户' },
              { value: 'admin', label: '管理员' },
            ]"
            :disabled="admin.busy"
            full-width
          />
        </div>
        <div class="flex items-center gap-3 text-primary">
          <AppCheckbox
            :checked="admin.draft.is_active"
            label="启用账号"
            :disabled="admin.busy"
            @change="admin.setField('is_active', $event)"
          /><span>启用账号</span>
        </div>
      </template>
      <template v-if="action === 'update'">
        <div class="flex items-center gap-3 text-primary">
          <AppCheckbox
            :checked="admin.draft.unlimited"
            label="不限制存储配额"
            :disabled="admin.busy"
            @change="admin.setField('unlimited', $event)"
          /><span>不限制存储配额</span>
        </div>
        <AppInput
          v-if="!admin.draft.unlimited"
          :model-value="admin.draft.quota"
          @update:model-value="admin.setField('quota', $event)"
          type="number"
          label="存储配额（GiB）"
          placeholder="填写非负GiB数值"
          min="0"
          step="any"
          :error="admin.fieldErrors.quota"
          :disabled="admin.busy"
        />
        <AppInput
          :model-value="admin.draft.operations"
          @update:model-value="admin.setField('operations', $event)"
          type="number"
          label="活动请求上限"
          placeholder="填写至少1个活动请求"
          min="1"
          step="1"
          :error="admin.fieldErrors.operations"
          :disabled="admin.busy"
        />
        <p class="text-muted text-sm">存储按该用户持有视频的逻辑大小计算；活动请求上限单独设置。</p>
      </template>
      <p v-if="action === 'create'" class="text-muted text-sm">
        新账号采用服务器默认配额，创建后可调整。
      </p>
      <div class="space-y-2">
        <label for="account-reason" class="text-primary">操作原因</label>
        <CustomSelect
          id="account-reason"
          :model-value="admin.draft.reason"
          @update:model-value="admin.setField('reason', $event)"
          :options="reasonOptions"
          :disabled="admin.busy"
          full-width
        />
        <p v-if="admin.fieldErrors.reason" class="text-accent-danger text-sm">
          {{ admin.fieldErrors.reason }}
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
    @update:show="admin.setConfirming"
    :title="title"
    :message="confirmation"
    confirm-text="确认执行"
    :type="
      ['reset_password', 'revoke_sessions'].includes(action) || !admin.draft.is_active
        ? 'danger'
        : 'warning'
    "
    @confirm="admin.confirm"
  />
  <ConfirmDialog
    :show="admin.discarding"
    @update:show="admin.setDiscarding"
    title="放弃未提交的输入"
    message="关闭会清空未提交的账号输入，是否继续？"
    confirm-text="放弃输入"
    @confirm="admin.clearEditor"
  />
</template>
