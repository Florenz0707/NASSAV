<script setup>
import { computed, onMounted, onScopeDispose } from 'vue'
import { resourceAdminApi } from '../../../api/admin.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { useMembershipsStore } from '../../library/stores/memberships.js'
import { createAdminRead } from '../lib/adminRead.js'
import { createResourceAdministration } from '../lib/resourceAdministration.js'
import ResourceAdminDialog from './ResourceAdminDialog.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
import ResourcePagination from '../../../shared/ui/ResourcePagination.vue'
import { ref } from 'vue'
const props = defineProps({ jobs: Boolean })
const session = useSessionStore(),
  memberships = useMembershipsStore()
const owner = () =>
  session.status === 'authenticated' &&
  session.capabilities.app_admin &&
  session.capabilities.shared_library
    ? session.identity
    : ''
const page = ref(1),
  size = ref(20)
const list = createAdminRead(props.jobs ? resourceAdminApi.jobs : resourceAdminApi.pools, owner)
const load = () => list.load({ page: page.value, page_size: size.value })
const canGc = computed(() => Boolean(session.capabilities.resource_gc))
const admin = createResourceAdministration(
  resourceAdminApi,
  owner,
  () => canGc.value,
  async () => {
    memberships.invalidate()
    await load()
  }
)
const pages = computed(() => Math.max(1, Math.ceil((list.pagination?.total || 0) / size.value)))
const stateLabels = {
  ready: '可用',
  preparing: '准备中',
  pending_gc: '等待回收',
  deleting: '正在删除',
  cleanup_failed: '清理失败',
  reclaimed: '已回收',
  queued: '已排队',
  completed: '已完成',
  cancelled: '已取消',
}
const time = (value) => (value ? new Date(value).toLocaleString('zh-CN') : '未设置')
function changePage(value) {
  page.value = value
  load()
}
function changeSize(value) {
  size.value = Math.max(1, Math.min(100, Math.trunc(Number(value)) || 20))
  page.value = 1
  load()
}
onMounted(load)
onScopeDispose(() => {
  admin.dispose()
  list.dispose()
})
</script>
<template>
  <section :aria-labelledby="jobs ? 'gc-jobs-title' : 'admin-resources-title'" class="min-w-0">
    <header class="flex flex-wrap items-center justify-between gap-3 mb-5">
      <h2
        :id="jobs ? 'gc-jobs-title' : 'admin-resources-title'"
        class="text-xl font-semibold text-primary"
      >
        {{ jobs ? '回收记录' : '共享资源管理' }}
      </h2>
      <AppButton variant="neutral" :loading="list.loading" @click="load"
        >刷新{{ jobs ? '回收记录' : '资源池' }}</AppButton
      >
    </header>
    <p class="text-muted text-sm mb-5">
      {{
        jobs
          ? '后台文件处理以记录状态为准；失败保留现场，修复原因后才能重试。'
          : '此处管理共享池的访问与保留，不展示用户的私人元数据或持有者名单。下架会影响所有持有者。'
      }}
    </p>
    <p v-if="!canGc" class="text-muted text-sm mb-4">
      回收执行开关关闭，文件不会由此界面开始删除。
    </p>
    <p v-if="admin.message" role="status" class="text-secondary text-sm mb-4">
      {{ admin.message }}
    </p>
    <RequestError v-if="list.error" :message="list.error" compact @retry="load" />
    <PageLoad v-if="list.loading && !list.rows.length" variant="spinner" text="正在加载管理记录" />
    <EmptyState
      v-else-if="!list.rows.length && !list.error"
      :title="jobs ? '暂无回收记录' : '暂无共享资源池'"
      description="准备完成的共享资源及回收进展将在这里显示。"
      compact
    />
    <div
      v-else-if="list.rows.length"
      class="overflow-x-auto rounded-xl border border-[var(--border-color)] bg-secondary"
    >
      <table class="min-w-[48rem] w-full text-sm text-primary">
        <caption class="sr-only">
          {{
            jobs ? '资源回收记录' : '共享资源池'
          }}
        </caption>
        <thead>
          <tr class="border-b border-[var(--border-color)]">
            <th class="p-3 text-center">{{ jobs ? '回收任务' : '资源' }}</th>
            <th v-if="!jobs" class="p-3 text-center">版本</th>
            <th class="p-3 text-center">状态</th>
            <th v-if="!jobs" class="p-3 text-center">访问</th>
            <th v-if="!jobs" class="p-3 text-center">保留</th>
            <th class="p-3 text-center">{{ jobs ? '错误代码' : '最早回收时间' }}</th>
            <th class="p-3 text-center">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in list.rows"
            :key="jobs ? row.job_id : row.pool_id"
            class="border-b border-[var(--border-color)]"
          >
            <th scope="row" class="p-3 text-center font-medium">
              <span class="block break-all">{{ jobs ? row.job_id : row.avid }}</span>
            </th>
            <td class="p-3 whitespace-nowrap text-center">
              {{ jobs ? row.version_id || '整池' : '池版本 ' + row.pool_version }}
            </td>
            <td class="p-3 whitespace-nowrap text-center">
              {{ stateLabels[row.state] || row.state }}
            </td>
            <td v-if="!jobs" class="p-3 whitespace-nowrap text-center">
              {{ row.is_available ? '可访问' : '已下架' }}
            </td>
            <td v-if="!jobs" class="p-3 whitespace-nowrap text-center">
              {{ row.retained ? '已保留' : '未保留' }}
            </td>
            <td class="p-3 text-muted text-center">
              {{ jobs ? row.error_code || '无' : time(row.gc_after) }}
            </td>
            <td class="p-3">
              <div class="flex justify-center gap-2">
                <AppButton
                  v-if="jobs"
                  size="sm"
                  variant="danger"
                  :disabled="!canGc || row.state !== 'cleanup_failed'"
                  :aria-label="'重试回收 ' + row.job_id"
                  @click="admin.open('retry', row)"
                  >重试</AppButton
                >
                <template v-else>
                  <AppButton
                    size="sm"
                    variant="neutral"
                    :aria-label="'预览回收 ' + row.avid"
                    @click="admin.open('preview', row)"
                    >回收预览</AppButton
                  >
                  <AppButton
                    size="sm"
                    variant="neutral"
                    :disabled="['deleting', 'reclaimed'].includes(row.state)"
                    :aria-label="(row.retained ? '取消保留 ' : '保留资源 ') + row.avid"
                    @click="admin.open('retention', row)"
                    >{{ row.retained ? '取消保留' : '保留' }}</AppButton
                  >
                  <AppButton
                    size="sm"
                    :variant="row.is_available ? 'danger' : 'neutral'"
                    :disabled="['deleting', 'cleanup_failed', 'reclaimed'].includes(row.state)"
                    :aria-label="(row.is_available ? '下架资源 ' : '恢复访问 ') + row.avid"
                    @click="admin.open('availability', row)"
                    >{{ row.is_available ? '下架' : '恢复访问' }}</AppButton
                  >
                </template>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ResourcePagination
      v-if="(list.pagination?.total || 0) > size"
      :page="page"
      :pages="pages"
      :page-size="size"
      :total="list.pagination.total"
      @change-page="changePage"
      @change-page-size="changeSize"
    />
    <ResourceAdminDialog :admin="admin" :can-gc="canGc" />
  </section>
</template>
