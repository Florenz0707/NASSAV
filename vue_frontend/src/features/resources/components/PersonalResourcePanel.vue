<script setup>
import { computed, onBeforeUnmount, reactive, watch } from 'vue'
import { resourceApi } from '../../../api/index.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { useToastStore } from '../../../shared/stores/toast.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppInput from '../../../shared/ui/AppInput.vue'
import { createPersonalResourceEditor } from '../lib/personalResourceEditor.js'

const props = defineProps({ resource: { type: Object, required: true } })
const emit = defineEmits(['updated'])
const session = useSessionStore(),
  toast = useToastStore()
const state = reactive({})
const editor = createPersonalResourceEditor({
  state,
  updateStatus: resourceApi.updateStatus,
  onUpdated: (snapshot) => emit('updated', snapshot),
  notify: (message) => toast.success(message),
})
const dirty = computed(() => state.notes !== state.savedNotes)
watch(
  () => [props.resource, session.status, session.username],
  () => {
    editor.sync(props.resource, session.status === 'authenticated' ? session.username : '')
  },
  { immediate: true, deep: true }
)
onBeforeUnmount(editor.reset)
</script>

<template>
  <section aria-label="个人资源状态" class="space-y-4">
    <div class="flex flex-wrap gap-3">
      <AppButton
        variant="neutral"
        class="flex-1"
        :aria-pressed="state.isFavorite"
        :disabled="!!state.busy"
        :loading="state.busy === 'favorite'"
        loading-text="正在保存收藏"
        :title="state.isFavorite ? '取消收藏' : '添加到收藏'"
        @click="editor.save({ is_favorite: !state.isFavorite }, 'favorite')"
      >
        <svg
          class="w-5 h-5"
          :class="state.isFavorite ? 'text-accent-primary' : 'text-muted'"
          :fill="state.isFavorite ? 'currentColor' : 'none'"
          stroke="currentColor"
          stroke-width="1.8"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
          />
        </svg>
        {{ state.isFavorite ? '已收藏' : '收藏' }}
      </AppButton>
      <AppButton
        variant="neutral"
        class="flex-1"
        :aria-pressed="state.watched"
        :disabled="!!state.busy"
        :loading="state.busy === 'watched'"
        loading-text="正在保存观看状态"
        :title="state.watched ? '标记为未观看' : '标记为已观看'"
        @click="editor.save({ watched: !state.watched }, 'watched')"
      >
        <svg
          class="w-5 h-5"
          :class="state.watched ? 'text-accent-success' : 'text-muted'"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path d="M2 12s4-8 10-8 10 8 10 8-4 8-10 8S2 12 2 12Z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
        {{ state.watched ? '已观看' : '标记观看' }}
      </AppButton>
      <AppButton
        variant="neutral"
        class="flex-1 whitespace-nowrap"
        :aria-pressed="state.watchLater"
        :disabled="!!state.busy"
        :loading="state.busy === 'later'"
        loading-text="正在保存稍后观看"
        @click="editor.save({ watch_later: !state.watchLater }, 'later')"
      >
        <svg
          class="w-5 h-5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
        {{ state.watchLater ? '已加入稍后观看' : '稍后观看' }}
      </AppButton>
    </div>
    <form class="space-y-3" @submit.prevent="editor.save({ notes: state.notes }, 'notes')">
      <AppInput
        v-model="state.notes"
        label="个人备注"
        multiline
        rows="4"
        maxlength="5000"
        placeholder="记录自己的观看感想或提醒"
        :disabled="!!state.busy"
        :clearable="false"
      />
      <div class="flex flex-wrap items-center justify-between gap-3">
        <span class="text-xs text-muted">仅当前账号可见 · {{ state.notes.length }} / 5000</span>
        <div class="flex gap-2">
          <AppButton
            size="sm"
            variant="neutral"
            :disabled="!!state.busy || !state.notes"
            @click="state.notes = ''"
            >清空</AppButton
          >
          <AppButton
            type="submit"
            size="sm"
            :disabled="!!state.busy || !dirty"
            :loading="state.busy === 'notes'"
            loading-text="正在保存备注"
            >保存备注</AppButton
          >
        </div>
      </div>
    </form>
    <p v-if="state.error" role="alert" class="text-sm text-accent-danger">{{ state.error }}</p>
  </section>
</template>
