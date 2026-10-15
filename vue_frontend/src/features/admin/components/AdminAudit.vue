<script setup>
import { onMounted, onScopeDispose } from 'vue'
import { adminApi } from '../../../api/admin.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { createAdminRead } from '../lib/adminRead.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'

const session = useSessionStore()
const list = createAdminRead(adminApi.audit, () =>
  session.capabilities.app_admin ? session.identity : ''
)
onMounted(list.load)
onScopeDispose(list.dispose)
const labels = {
  'account.create': '创建账号',
  'account.update': '修改账号',
  'account.revoke_sessions': '撤销登录',
  'account.reset_password': '重置密码',
  'source_credential.write': '保存系统凭证',
  'source_credential.revoke': '撤销系统凭证',
  'resource.availability': '资源访问策略',
  gc_enqueue: '登记回收',
  gc_retry: '重试回收',
  gc_retention: '资源保留策略',
  'account.bootstrap': '初始化管理员',
}
const reasons = {
  maintenance: '系统维护',
  security: '安全处理',
  user_request: '用户请求',
  quota_adjustment: '配额调整',
  bootstrap: '初始化',
}
const time = (value) => new Date(value).toLocaleString('zh-CN', { hour12: false })
</script>
<template>
  <section aria-labelledby="admin-audit-title" class="min-w-0">
    <header class="flex items-center justify-between gap-3 mb-5">
      <div>
        <h2 id="admin-audit-title" class="text-xl font-semibold text-primary">审计记录</h2>
        <p class="text-muted text-sm mt-1">最近100条管理操作</p>
      </div>
      <AppButton variant="neutral" :loading="list.loading" @click="list.load">刷新记录</AppButton>
    </header>
    <RequestError v-if="list.error" :message="list.error" compact @retry="list.load" /><PageLoad
      v-if="list.loading && !list.rows.length"
      variant="spinner"
      text="正在加载审计记录"
    /><EmptyState
      v-else-if="!list.rows.length && !list.error"
      icon="empty"
      title="暂无审计记录"
      description="管理操作完成后会显示在这里。"
    />
    <div
      v-else-if="list.rows.length"
      class="overflow-x-auto border border-[var(--border-color)] rounded-xl bg-secondary"
    >
      <table class="min-w-[44rem] w-full text-sm text-primary">
        <caption class="sr-only">
          最近的管理审计记录
        </caption>
        <thead>
          <tr class="border-b border-[var(--border-color)]">
            <th class="p-3 text-left">时间</th>
            <th class="p-3 text-left">操作者</th>
            <th class="p-3 text-left">动作</th>
            <th class="p-3 text-left">对象</th>
            <th class="p-3 text-left">原因</th>
            <th class="p-3 text-left">结果</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in list.rows" :key="row.id" class="border-b border-[var(--border-color)]">
            <td class="p-3 whitespace-nowrap text-muted">
              <time :datetime="row.created_at">{{ time(row.created_at) }}</time>
            </td>
            <td class="p-3">{{ row.actor_id ? '#' + row.actor_id : '系统' }}</td>
            <td class="p-3">{{ labels[row.action] || row.action }}</td>
            <td class="p-3 break-all">{{ row.object_id }}</td>
            <td class="p-3">{{ reasons[row.reason] || row.reason }}</td>
            <td class="p-3">{{ row.result?.status === 'succeeded' ? '成功' : '已记录' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
