<script setup>
import { computed, onMounted, onScopeDispose } from 'vue'
import { adminApi } from '../../../api/admin.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { createAccountAdministration } from '../lib/accountAdministration.js'
import AccountEditor from './AccountEditor.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
import ResourcePagination from '../../../shared/ui/ResourcePagination.vue'
import InfoDialog from '../../../shared/ui/InfoDialog.vue'

const session = useSessionStore()
const admin = createAccountAdministration(adminApi, () =>
  session.status === 'authenticated' && session.capabilities.app_admin ? session.identity : ''
)
onMounted(admin.load)
onScopeDispose(admin.dispose)
const pages = computed(() =>
  Math.max(1, Math.ceil((admin.list.pagination?.total || 0) / admin.page_size))
)
function changePage(page) {
  admin.page = page
  admin.load()
}
function changePageSize(value) {
  admin.page_size = Math.max(1, Math.min(100, Math.trunc(Number(value)) || 20))
  admin.page = 1
  admin.load()
}
const quota = (bytes) =>
  bytes === null
    ? '不限制'
    : `${(bytes / 1024 ** 3).toLocaleString('zh-CN', { maximumFractionDigits: 3 })} GiB`
</script>
<template>
  <section aria-labelledby="admin-accounts-title" class="min-w-0">
    <header class="flex flex-wrap items-center justify-between gap-3 mb-5">
      <div class="flex items-center gap-2">
        <h2 id="admin-accounts-title" class="text-xl font-semibold text-primary">账号管理</h2>
        <InfoDialog title="账号操作说明" label="查看账号操作说明">
          <p class="text-secondary leading-relaxed">
            角色变更、停用、重置密码和撤销会话会使该用户需要重新登录。停用还会撤销个人来源凭证、移出其资源持有并撤销其任务请求。共享资源仍受其他用户的持有和播放保护。
          </p>
          <p class="text-muted text-sm mt-3">
            至少保留一个启用的应用管理员；管理权限由应用角色决定。
          </p>
        </InfoDialog>
      </div>
      <div class="flex gap-3">
        <AppButton variant="neutral" :loading="admin.list.loading" @click="admin.load"
          >刷新账号</AppButton
        >
        <AppButton @click="admin.open('create')">创建账号</AppButton>
      </div>
    </header>
    <p v-if="!session.capabilities.ordinary_login" class="text-muted text-sm mb-4">
      多账号登录尚未开放；创建账号不会改变当前登录策略。
    </p>
    <p v-if="admin.message" role="status" class="text-secondary text-sm mb-4">
      {{ admin.message }}
    </p>
    <RequestError v-if="admin.list.error" :message="admin.list.error" compact @retry="admin.load" />
    <PageLoad
      v-if="admin.list.loading && !admin.list.rows.length"
      variant="spinner"
      text="正在加载账号"
    />
    <EmptyState
      v-else-if="!admin.list.rows.length && !admin.list.error"
      icon="empty"
      title="暂无管理账号"
      description="可创建新的管理账号。"
    />
    <div
      v-else-if="admin.list.rows.length"
      class="overflow-x-auto rounded-xl border border-[var(--border-color)] bg-secondary"
    >
      <table class="w-full min-w-[48rem] text-sm text-primary">
        <caption class="sr-only">
          应用账号与配置配额
        </caption>
        <thead>
          <tr class="border-b border-[var(--border-color)]">
            <th class="p-3 text-center">id</th>
            <th class="p-3 text-center">用户名</th>
            <th class="p-3 text-center">角色</th>
            <th class="p-3 text-center">状态</th>
            <th class="p-3 text-center">存储配额</th>
            <th class="p-3 text-center">请求上限</th>
            <th class="p-3 text-center">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in admin.list.rows"
            :key="row.user_id"
            class="border-b border-[var(--border-color)]"
          >
            <th scope="row" class="p-3 text-center font-medium">
              {{ '#' + row.user_id }}
            </th>
            <th scope="row" class="p-3 text-center font-medium">
              {{ row.username }}
            </th>
            <td class="p-3 text-center font-medium">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </td>
            <td
              class="p-3 text-center font-medium"
              :class="row.is_active ? 'text-accent-success' : 'text-muted'"
            >
              {{ row.is_active ? '启用' : '停用' }}
            </td>
            <td class="p-3 whitespace-nowrap text-center font-medium">
              {{ quota(row.storage_quota_bytes) }}
            </td>
            <td class="p-3 text-center font-medium">{{ row.max_active_operations }}</td>
            <td class="p-3">
              <div class="flex justify-center gap-3">
                <AppButton
                  size="sm"
                  variant="neutral"
                  :aria-label="'编辑账号 ' + row.username"
                  @click="admin.open('update', row)"
                  >编辑</AppButton
                >
                <AppButton
                  size="sm"
                  variant="neutral"
                  :aria-label="'撤销会话 ' + row.username"
                  @click="admin.open('revoke_sessions', row)"
                  >撤销会话</AppButton
                >
                <AppButton
                  size="sm"
                  variant="danger"
                  :aria-label="'重置密码 ' + row.username"
                  @click="admin.open('reset_password', row)"
                  >重置密码</AppButton
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
      @change-page-size="changePageSize"
    />
    <AccountEditor :admin="admin" />
  </section>
</template>
