<script setup>
import { computed, onMounted, onScopeDispose, ref, watch } from 'vue'
import { libraryApi } from '../../../api/library.js'
import { createMembershipList } from '../lib/membershipList.js'
import { useLibraryCommandsStore } from '../stores/commands.js'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppCheckbox from '../../../shared/ui/AppCheckbox.vue'
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
import SearchInput from '../../../shared/ui/SearchInput.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
import ResourcePagination from '../../../shared/ui/ResourcePagination.vue'

const emit = defineEmits(['close'])
const commands = useLibraryCommandsStore()
const list = createMembershipList(libraryApi.listMemberships)
const { rows, loading, error, pagination } = list
const query = ref({
  page: 1,
  page_size: 20,
  ordering: '-created_at',
  state: '',
  availability: '',
  search: '',
})
const search = ref(''),
  selected = ref(new Set()),
  requested = ref([]),
  showConfirm = ref(false),
  busy = ref(false),
  message = ref(''),
  failures = ref([])
let active = true
onScopeDispose(() => {
  active = false
  list.dispose()
})
onMounted(() => list.load(query.value))
watch(query, (value) => list.load(value), { deep: true })
watch(rows, (value) => {
  const ids = new Set(value.map((row) => row.entry_id))
  selected.value = new Set([...selected.value].filter((id) => ids.has(id)))
})
const allChecked = computed(
  () => rows.value.length > 0 && rows.value.every((row) => selected.value.has(row.entry_id))
)
function check(id, value) {
  const next = new Set(selected.value)
  value ? next.add(id) : next.delete(id)
  selected.value = next
}
function checkAll(value) {
  selected.value = value ? new Set(rows.value.map((row) => row.entry_id)) : new Set()
}
function close() {
  if (!busy.value) emit('close')
}
function requestRelease(items) {
  requested.value = items.map((item) => ({ ...item }))
  showConfirm.value = true
}
async function release() {
  if (busy.value || !requested.value.length) return
  const items = requested.value
  busy.value = true
  message.value = ''
  failures.value = []
  try {
    const results = await commands.batch(
      'release',
      items.map((item) => item.avid),
      { memberships: Object.fromEntries(items.map((item) => [item.avid, item])) }
    )
    if (!active) return
    failures.value = results.filter((item) => !(item.code >= 200 && item.code < 300))
    message.value = `已移出 ${results.length - failures.value.length} 个，失败 ${failures.value.length} 个`
    const failed = new Set(failures.value.map((item) => item.avid))
    selected.value = new Set(
      items.filter((item) => failed.has(item.avid)).map((item) => item.entry_id)
    )
    await list.load(query.value)
  } catch (reason) {
    if (active) message.value = reason.message || '移出未确认，请重试'
  } finally {
    if (active) busy.value = false
  }
}
function filter(key, value) {
  query.value = { ...query.value, [key]: value, page: 1 }
}
function setPageSize(value) {
  filter('page_size', Math.max(1, Math.min(100, Math.trunc(Number(value)) || 20)))
}
const displayTime = (value) => new Date(value).toLocaleString('zh-CN', { hour12: false })
</script>

<template>
  <SettingsModal
    :show="true"
    title="管理我的持有"
    max-width-class="max-w-5xl flex flex-col max-h-[calc(100dvh-2rem)]"
    content-class="min-h-0 flex-1 overflow-y-auto"
    :show-close="!busy"
    @close="close"
  >
    <p class="text-secondary text-sm mb-4">
      包含准备中和暂不可用的本人持有关系。这里只显示编号与关系状态；移出不会删除其他用户的资源，文件由受控回收流程处理。
    </p>
    <form class="flex flex-wrap items-center gap-3 mb-4" @submit.prevent="filter('search', search)">
      <SearchInput v-model="search" placeholder="搜索本人持有的编号" :disabled="busy" />
      <AppButton type="submit" variant="neutral" :disabled="busy" :loading="loading"
        >查询</AppButton
      >
      <CustomSelect
        :model-value="query.state"
        aria-label="持有状态"
        :options="[
          { value: '', label: '全部持有状态' },
          { value: 'active', label: '已持有' },
          { value: 'pending', label: '准备中' },
        ]"
        :disabled="busy"
        @update:model-value="filter('state', $event)"
      />
      <CustomSelect
        :model-value="query.availability"
        aria-label="资源可用性"
        :options="[
          { value: '', label: '全部可用性' },
          { value: 'available', label: '未下架' },
          { value: 'unavailable', label: '暂不可用' },
        ]"
        :disabled="busy"
        @update:model-value="filter('availability', $event)"
      />
    </form>
    <div class="flex flex-wrap items-center gap-3 mb-4">
      <AppButton
        variant="danger"
        :disabled="!selected.size || busy"
        :loading="busy && requested.length > 1"
        @click="requestRelease(rows.filter((row) => selected.has(row.entry_id)))"
        >移出所选</AppButton
      >
      <AppButton variant="neutral" :disabled="busy" :loading="loading" @click="list.load(query)"
        >刷新持有</AppButton
      >
      <span class="text-muted text-sm"
        >共 {{ pagination.total }} 个；已选择 {{ selected.size }} 个当前页持有</span
      >
    </div>
    <p v-if="message" role="status" class="text-secondary text-sm mb-3">{{ message }}</p>
    <ul v-if="failures.length" class="text-accent-danger text-sm space-y-1 mb-3">
      <li v-for="failure in failures" :key="failure.avid">
        {{ failure.avid }}：{{ failure.message }}
      </li>
    </ul>
    <RequestError v-if="error" :message="error" compact @retry="list.load(query)" />
    <PageLoad v-if="loading && !rows.length" variant="spinner" text="正在加载本人持有" />
    <EmptyState
      v-else-if="!rows.length && !error"
      icon="empty"
      title="暂无匹配的持有关系"
      description="调整筛选条件或添加资源。"
    />
    <div v-else-if="rows.length" class="overflow-x-auto">
      <table class="w-full min-w-[42rem] text-sm text-primary">
        <caption class="sr-only">
          本人持有关系，含准备中和暂不可用资源
        </caption>
        <thead>
          <tr class="border-b border-[var(--border-color)]">
            <th class="p-3 text-left">
              <AppCheckbox
                :checked="allChecked"
                :indeterminate="selected.size > 0 && !allChecked"
                :disabled="busy"
                label="选择当前页全部持有"
                @change="checkAll"
              />
            </th>
            <th class="p-3 text-left">资源编号</th>
            <th class="p-3 text-left">状态</th>
            <th class="p-3 text-left">最近更新</th>
            <th class="p-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.entry_id" class="border-b border-[var(--border-color)]">
            <td class="p-3">
              <AppCheckbox
                :checked="selected.has(row.entry_id)"
                :disabled="busy"
                :label="'选择持有 ' + row.avid"
                @change="check(row.entry_id, $event)"
              />
            </td>
            <th scope="row" class="p-3 text-left font-medium">{{ row.avid }}</th>
            <td class="p-3">
              <span :class="row.is_available ? 'text-secondary' : 'text-accent-warning'">{{
                !row.is_available
                  ? '暂不可用'
                  : row.membership_state === 'pending'
                    ? '准备中'
                    : '已持有'
              }}</span>
            </td>
            <td class="p-3 whitespace-nowrap text-muted">
              <time :datetime="row.updated_at">{{ displayTime(row.updated_at) }}</time>
            </td>
            <td class="p-3 text-right">
              <AppButton
                variant="danger"
                size="sm"
                :disabled="busy"
                :loading="busy && requested.some((item) => item.entry_id === row.entry_id)"
                :aria-label="'移出持有 ' + row.avid"
                @click="requestRelease([row])"
                >移出</AppButton
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ResourcePagination
      :inert="busy || loading"
      v-if="pagination.total"
      :page="pagination.page"
      :pages="pagination.pages"
      :page-size="pagination.page_size"
      :total="pagination.total"
      @change-page="query.page = $event"
      @change-page-size="setPageSize"
    />
  </SettingsModal>
  <ConfirmDialog
    v-model:show="showConfirm"
    title="移出我的持有"
    :message="`移出这 ${requested.length} 个本人的持有关系并撤销本人的相关需求？其他用户仍需要的共享资源会保留。`"
    confirm-text="确认移出"
    type="danger"
    @confirm="release"
  />
</template>
