<script setup>
import { onMounted, onScopeDispose } from 'vue'
import { systemCredentialApi } from '../../../api/admin.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { createSystemCredentials } from '../lib/systemCredentials.js'
import SystemCredentialEditor from './SystemCredentialEditor.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
const session = useSessionStore()
const admin = createSystemCredentials(
  systemCredentialApi,
  () =>
    session.status === 'authenticated' && session.capabilities.app_admin ? session.identity : '',
  session.updateSourceIdentity
)
onMounted(admin.load)
onScopeDispose(admin.dispose)
const labels = { active: '已保存', revoked: '已撤销', quarantined: '待审核' }
const date = (value) => new Date(value).toLocaleString('zh-CN')
</script>
<template>
  <section aria-labelledby="admin-source-title" class="min-w-0">
    <header class="flex flex-wrap justify-between items-center gap-3 mb-5">
      <h2 id="admin-source-title" class="text-xl font-semibold text-primary">系统来源凭证</h2>
      <div class="flex gap-3">
        <AppButton variant="neutral" :loading="admin.list.loading" @click="admin.load"
          >刷新凭证</AppButton
        ><AppButton :disabled="!admin.sources.length || admin.list.loading" @click="admin.open()"
          >添加系统凭证</AppButton
        >
      </div>
    </header>
    <p class="text-muted text-sm mb-5">
      仅管理公共访问验证；个人账号 Cookie 不在此处展示。内容保存后不回显，修改需填写新的 Cookie 与
      User-Agent。
    </p>
    <p v-if="admin.message" role="status" class="text-secondary text-sm mb-4">
      {{ admin.message }}
    </p>
    <RequestError
      v-if="admin.list.error || (!admin.editor && admin.error)"
      :message="admin.list.error || admin.error"
      compact
      @retry="admin.load"
    />
    <PageLoad
      v-if="admin.list.loading && !admin.list.rows.length"
      variant="spinner"
      text="正在加载系统凭证"
    />
    <EmptyState
      v-else-if="!admin.list.rows.length && !admin.list.error"
      title="尚无系统凭证"
      description="需要时添加访问验证 Cookie；无凭证时沿来源的匿名策略访问。"
      compact
    />
    <div
      v-else-if="admin.list.rows.length"
      class="overflow-x-auto rounded-xl border border-[var(--border-color)] bg-secondary"
    >
      <table class="w-full min-w-[40rem] text-sm text-primary">
        <caption class="sr-only">
          系统来源凭证元信息
        </caption>
        <thead>
          <tr class="border-b border-[var(--border-color)]">
            <th class="p-3 text-left">来源</th>
            <th class="p-3 text-left">状态</th>
            <th class="p-3 text-left">版本</th>
            <th class="p-3 text-left">更新时间</th>
            <th class="p-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in admin.list.rows"
            :key="row.id"
            class="border-b border-[var(--border-color)]"
          >
            <th scope="row" class="p-3 text-left">
              {{ row.source_name
              }}<span class="block text-muted text-xs mt-1">{{ row.origin_host }}</span>
            </th>
            <td class="p-3">{{ labels[row.state] || '不可用' }}</td>
            <td class="p-3">{{ row.version }}</td>
            <td class="p-3 whitespace-nowrap">{{ date(row.updated_at) }}</td>
            <td class="p-3">
              <div class="flex justify-end gap-2">
                <AppButton
                  size="sm"
                  variant="neutral"
                  :aria-label="'更新系统凭证 ' + row.source_name"
                  @click="admin.open(row)"
                  >更新</AppButton
                ><AppButton
                  size="sm"
                  variant="danger"
                  :disabled="row.state === 'revoked'"
                  :aria-label="'撤销系统凭证 ' + row.source_name"
                  @click="admin.open(row, true)"
                  >撤销</AppButton
                >
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <SystemCredentialEditor :admin="admin" />
  </section>
</template>
