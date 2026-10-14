<script setup>
import { onBeforeUnmount, reactive, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { resourceApi } from '../../../api/index.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { useToastStore } from '../../../shared/stores/toast.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppInput from '../../../shared/ui/AppInput.vue'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import PersonalResourceActions from './PersonalResourceActions.vue'
import { createPersonalResourceEditor } from '../lib/personalResourceEditor.js'
import { createNoteDialog } from '../lib/noteDialog.js'
const props = defineProps({ resource: { type: Object, required: true } })
const emit = defineEmits(['updated'])
const session = useSessionStore(),
  toast = useToastStore()
const state = reactive({}),
  ui = reactive({ open: false, confirm: false })
const editor = createPersonalResourceEditor({
  state,
  updateStatus: resourceApi.updateStatus,
  onUpdated: (snapshot) => emit('updated', snapshot),
  notify: (message) => toast.success(message),
})
const dialog = createNoteDialog({ state, ui, save: editor.save })
watch(
  () => [props.resource.avid, session.status, session.username],
  (next, previous) => {
    if (next.some((value, index) => value !== previous[index])) dialog.reset()
  }
)
watch(
  () => [props.resource, session.status, session.username],
  () => editor.sync(props.resource, session.status === 'authenticated' ? session.username : ''),
  { immediate: true, deep: true }
)
onBeforeRouteLeave(() => dialog.close())
onBeforeRouteUpdate((to, from) => (to.params.avid !== from.params.avid ? dialog.close() : true))
function beforeUnload(event) {
  if (ui.open && dialog.dirty()) {
    event.preventDefault()
    event.returnValue = ''
  }
}
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  dialog.reset()
  editor.reset()
})
</script>
<template>
  <section aria-label="个人资源状态" class="min-w-0 w-full space-y-6">
    <slot :state="state" :save="editor.save"
      ><PersonalResourceActions :state="state" @change="editor.save"
    /></slot>
    <div class="flex items-start gap-4 min-w-0 w-full max-w-full">
      <AppButton
        size="sm"
        variant="neutral"
        class="shrink-0 w-8 h-8 p-0"
        :disabled="!!state.busy"
        aria-label="编辑个人备注"
        title="编辑个人备注"
        @click="dialog.open"
      >
        <svg
          class="w-4 h-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          aria-hidden="true"
        >
          <path d="m16 3 5 5L8 21H3v-5L16 3Z" />
          <path d="m14 5 5 5" />
        </svg>
      </AppButton>
      <p class="text-secondary whitespace-pre-wrap [overflow-wrap:anywhere] flex-1 min-w-0">
        <span class="font-medium text-primary">个人备注：</span>{{ state.savedNotes || '暂无备注' }}
      </p>
    </div>
    <p v-if="state.error && !ui.open" role="alert" class="text-sm text-accent-danger">
      {{ state.error }}
    </p>
    <SettingsModal
      :show="ui.open"
      title="编辑个人备注"
      :show-close="false"
      max-width-class="max-w-2xl max-h-[90dvh] flex flex-col"
      content-class="min-h-0 overflow-y-auto"
      @close="dialog.close"
    >
      <AppInput
        v-model="state.notes"
        label="个人备注"
        multiline
        rows="6"
        maxlength="5000"
        placeholder="记录自己的观看感想或提醒"
        :disabled="!!state.busy"
        :clearable="false"
      />
      <p class="text-xs text-muted mt-3">
        仅当前账号可见 · {{ state.notes.length }} / 5000<span v-if="dialog.dirty()">
          · 尚未保存</span
        >
      </p>
      <p v-if="state.error" role="alert" class="text-sm text-accent-danger mt-3">
        {{ state.error }}
      </p>
      <template #footer
        ><div class="flex flex-wrap justify-end gap-3">
          <AppButton variant="neutral" :disabled="!!state.busy" @click="dialog.close"
            >关闭</AppButton
          >
          <AppButton
            variant="neutral"
            :disabled="!!state.busy || !state.notes"
            @click="state.notes = ''"
            >清空</AppButton
          >
          <AppButton
            :disabled="!!state.busy || !dialog.dirty()"
            :loading="state.busy === 'notes'"
            loading-text="正在保存备注"
            @click="dialog.persist"
            >保存</AppButton
          >
        </div></template
      >
    </SettingsModal>
    <ConfirmDialog
      :show="ui.confirm"
      title="尚未保存"
      message="个人备注有尚未保存的修改，确定放弃并退出吗？"
      confirm-text="放弃修改"
      cancel-text="继续编辑"
      @confirm="dialog.discard"
      @cancel="dialog.keep"
    />
  </section>
</template>
