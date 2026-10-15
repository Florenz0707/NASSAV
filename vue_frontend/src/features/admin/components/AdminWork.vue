<script setup>
import { computed, onMounted, onScopeDispose } from 'vue'
import { workAdminApi } from '../../../api/admin.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { createWorkAdministration, workActionLabels } from '../lib/workAdministration.js'
import { taskTime } from '../../tasks/lib/taskDetails.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
import ResourcePagination from '../../../shared/ui/ResourcePagination.vue'
const session = useSessionStore()
const admin = createWorkAdministration(workAdminApi, () =>
  session.status === 'authenticated' && session.capabilities.app_admin ? session.identity : ''
)
const stateLabels = {
  queued: '排队中',
  running: '进行中',
  pausing: '暂停中',
  paused: '已暂停',
  cancelling: '终止中',
  cancelled: '已终止',
  failed: '失败',
  succeeded: '已完成',
}
const cleanupLabels = {
  pending: '等待中',
  running: '清理中',
  completed: '已完成',
  failed: '失败',
  not_required: '无需清理',
}
const pages = computed(() =>
  Math.max(1, Math.ceil((admin.list.pagination?.total || 0) / admin.page_size))
)
const title = computed(() => workActionLabels[admin.editor?.action] || '执行控制')
const reasons = [
  { value: 'maintenance', label: '系统维护' },
  { value: 'security', label: '安全处理' },
  { value: 'user_request', label: '用户请求' },
  { value: 'quota_adjustment', label: '配额调整' },
]
function changePage(value) {
  admin.page = value
  admin.load()
}
function changeSize(value) {
  admin.page_size = Math.max(1, Math.min(100, Math.trunc(Number(value)) || 20))
  admin.page = 1
  admin.load()
}
function ordering(value) {
  admin.ordering = value
  admin.page = 1
  admin.load()
}
onMounted(admin.load)
onScopeDispose(admin.dispose)
</script>
<template>
  <section aria-labelledby="admin-work-title" class="min-w-0">
    <header class="flex flex-wrap justify-between items-center gap-3 mb-5">
      <h2 id="admin-work-title" class="text-xl font-semibold text-primary">全局执行管理</h2>
      <div class="flex flex-wrap items-center gap-3">
        <AppButton variant="neutral" :loading="admin.list.loading" @click="admin.load"
          >刷新执行</AppButton
        >
        <CustomSelect
          id="admin-work-order"
          aria-label="执行排序"
          :model-value="admin.ordering"
          :options="[
            { value: '-updated_at', label: '最近更新优先' },
            { value: '-created_at', label: '最近创建优先' },
          ]"
          @update:model-value="ordering"
        />
      </div>
    </header>
    <p class="text-muted text-sm mb-5">
      此处控制后台执行，可能影响所有等待该共享工作的用户。个人请求的撤销请使用任务详情页；终态不等于文件已清理。
    </p>
    <p v-if="admin.message" role="status" class="text-secondary text-sm mb-4">
      {{ admin.message }}
    </p>
    <RequestError v-if="admin.list.error" :message="admin.list.error" compact @retry="admin.load" />
    <PageLoad
      v-if="admin.list.loading && !admin.list.rows.length"
      variant="spinner"
      text="正在加载后台执行"
    />
    <EmptyState
      v-else-if="!admin.list.rows.length && !admin.list.error"
      title="暂无后台执行"
      description="共享下载和刮削执行将在这里显示。"
      compact
    />
    <div
      v-else-if="admin.list.rows.length"
      class="overflow-x-auto rounded-xl border border-[var(--border-color)] bg-secondary"
    >
      <table class="w-full min-w-[48rem] text-sm text-primary">
        <caption class="sr-only">
          后台执行状态与管理员控制
        </caption>
        <thead>
          <tr class="border-b border-[var(--border-color)]">
            <th class="p-3 text-center">执行</th>
            <th class="p-3 text-center">状态</th>
            <th class="p-3 text-center">文件清理</th>
            <th class="p-3 text-center">更新时间</th>
            <th class="p-3 text-center">控制</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in admin.list.rows"
            :key="row.job_id"
            class="border-b border-[var(--border-color)]"
          >
            <th scope="row" class="p-3 text-center font-medium">
              <span class="block">{{ row.avid }} · {{ row.job_type }}</span
              ><span class="block text-muted text-xs mt-1 break-all"
                >{{ row.job_id }} · v{{ row.version }}</span
              >
            </th>
            <td class="p-3 text-center">{{ stateLabels[row.state] || row.state }}</td>
            <td class="p-3 text-center">{{ cleanupLabels[row.cleanup_state] || '状态未知' }}</td>
            <td class="p-3 text-muted text-center whitespace-nowrap">
              {{ taskTime(row.updated_at) }}
            </td>
            <td class="p-3">
              <div class="flex justify-center gap-2">
                <AppButton
                  v-for="(label, action) in workActionLabels"
                  :key="action"
                  size="sm"
                  :variant="action === 'cancel' ? 'danger' : 'neutral'"
                  :disabled="!row.allowed_actions?.includes(action) || admin.busy"
                  :aria-label="label + ' ' + row.job_id"
                  @click="admin.open(action, row)"
                  >{{ label }}</AppButton
                >
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ResourcePagination
      v-if="(admin.list.pagination?.total || 0) > admin.page_size"
      :page="admin.page"
      :pages="pages"
      :page-size="admin.page_size"
      :total="admin.list.pagination.total"
      @change-page="changePage"
      @change-page-size="changeSize"
    />
    <SettingsModal
      :show="Boolean(admin.editor)"
      :title="title"
      :show-close="!admin.busy"
      max-width-class="max-w-xl flex flex-col max-h-[calc(100dvh-2rem)]"
      content-class="min-h-0 flex-1 overflow-y-auto"
      @close="admin.close"
    >
      <form class="space-y-4" @submit.prevent="admin.prepare">
        <p class="text-primary">{{ admin.editor?.row.avid }} · {{ admin.editor?.row.job_type }}</p>
        <p class="text-muted text-sm break-all">
          {{ admin.editor?.row.job_id }} · 版本 {{ admin.editor?.row.version }}
        </p>
        <p class="text-secondary text-sm">
          操作针对整个执行，会影响其他仍在等待的用户。后台须确认写入者停止后才能暂停或清理，登记成功不代表已经完成。
        </p>
        <div class="space-y-2">
          <label for="work-admin-reason" class="text-primary">操作原因</label>
          <CustomSelect
            id="work-admin-reason"
            :model-value="admin.reason"
            :options="reasons"
            :disabled="admin.busy"
            full-width
            @update:model-value="admin.setReason"
          />
        </div>
        <p v-if="admin.error" role="alert" class="text-accent-danger text-sm">{{ admin.error }}</p>
        <div class="flex justify-end gap-3">
          <AppButton variant="neutral" :disabled="admin.busy" @click="admin.close">关闭</AppButton>
          <AppButton type="submit" :loading="admin.busy" loading-text="登记中">下一步</AppButton>
        </div>
      </form>
    </SettingsModal>
    <ConfirmDialog
      :show="admin.confirming"
      :title="'确认' + title"
      message="此操作将控制整个后台执行，可能影响其他用户的请求。确定执行吗？"
      confirm-text="确认执行"
      :type="admin.editor?.action === 'cancel' ? 'danger' : 'warning'"
      @update:show="admin.setConfirming"
      @confirm="admin.confirm"
    />
  </section>
</template>
