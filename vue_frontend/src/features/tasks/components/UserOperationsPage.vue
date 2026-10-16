<script setup>
import { computed, ref } from 'vue'
import { resourceApi } from '../../../api/resources.js'
import { useRoute, RouterLink } from 'vue-router'
import { useUserOperationsStore } from '../stores/userOperations.js'
import { useResourceStore } from '../../resources/stores/resource.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { buildOperationDetails } from '../lib/operationDetails.js'
import TaskDetailsPanel from './TaskDetailsPanel.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import InfoDialog from '../../../shared/ui/InfoDialog.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'

const operations = useUserOperationsStore(),
  resources = useResourceStore(),
  settings = useSettingsStore()
const route = useRoute()
const tasks = computed(() =>
  buildOperationDetails(
    operations.visible,
    resources.resources,
    settings.displayTitle,
    resourceApi.resolveCoverUrl
  )
)
const focused = computed(
  () => tasks.value.find((task) => task.operationId === route.query.task)?.id || ''
)
const showCancel = ref(false),
  showHide = ref(false),
  selected = ref([])
function requestCancel(action, ids) {
  if (action !== 'cancel') return
  selected.value = ids
  showCancel.value = true
}
function requestHide(ids) {
  selected.value = ids
  showHide.value = true
}
function selectedOperations() {
  return tasks.value
    .filter((task) => selected.value.includes(task.id))
    .map((task) => task.operationId)
}
</script>

<template>
  <div class="flex flex-col min-h-[calc(100dvh-6rem)] min-[641px]:min-h-[calc(100dvh-8rem)]">
    <RequestError
      v-if="operations.listError"
      :message="operations.listError"
      compact
      @retry="operations.load()"
    />
    <p v-if="operations.error" role="alert" class="text-accent-danger mb-4">
      {{ operations.error }}
    </p>
    <PageLoad
      v-if="operations.loading && !tasks.length"
      variant="spinner"
      text="正在加载本人请求"
    />
    <TaskDetailsPanel
      v-else
      :tasks="tasks"
      operation-mode
      :ordering="operations.ordering"
      :busy="operations.busy"
      :focus-task-id="focused"
      @sort="operations.setOrdering"
      @control="requestCancel"
      @dismiss="requestHide"
    >
      <template #information>
        <InfoDialog title="本人请求跟踪说明" label="查看请求跟踪说明">
          <p class="text-secondary leading-relaxed">
            当前跟踪 {{ operations.visible.length }} 个已加载请求；已隐藏
            {{ operations.operations.size - operations.visible.length }} 个；服务端共
            {{ operations.total }} 个。列表与批量操作只针对本人已加载请求。
          </p>
          <p class="text-secondary mt-3 leading-relaxed">
            撤销只移除本人的需求，其他用户仍有需求时共享执行继续。不再跟踪仅隐藏记录，不会撤销请求或移出资源库。
          </p>
        </InfoDialog>
      </template>
      <template #details="{ task }">
        <RouterLink
          v-if="task.hasResource"
          :to="'/resource/' + encodeURIComponent(task.avid)"
          class="tw-btn-primary mt-5 px-4 py-2.5 rounded-xl"
          >查看资源</RouterLink
        >
      </template>
    </TaskDetailsPanel>
    <AppButton
      v-if="operations.hasMore"
      variant="neutral"
      size="sm"
      class="self-center mt-4"
      :loading="operations.loading"
      @click="operations.load(true)"
      >加载更多</AppButton
    >
    <ConfirmDialog
      v-model:show="showCancel"
      title="撤销我的请求"
      :message="`撤销所选 ${selected.length} 个本人请求？其他用户仍有需求时，共享执行会继续；此操作不会移出已持有的资源。`"
      confirm-text="撤销请求"
      @confirm="operations.cancel(selectedOperations())"
    />
    <ConfirmDialog
      v-model:show="showHide"
      title="不再跟踪请求"
      message="仅在当前登录的列表中隐藏这些记录，后台请求仍会继续。"
      confirm-text="不再跟踪"
      @confirm="operations.hide(selectedOperations())"
    />
  </div>
</template>
