<template>
  <nav aria-label="分页" class="mt-8 w-full">
    <div class="flex flex-wrap items-center justify-center gap-2 mb-3">
      <AppButton
        variant="neutral"
        :disabled="page === 1"
        class="hidden sm:inline-flex"
        @click="goFirst"
      >
        跳转开头
      </AppButton>
      <AppButton variant="neutral" :disabled="page === 1" @click="goPrev"> 上一页 </AppButton>
      <div class="px-4 py-2 rounded-lg bg-secondary text-primary text-sm">
        第 {{ page }} 页 / 共 {{ pages }} 页
      </div>
      <AppButton variant="neutral" :disabled="page === pages" @click="goNext"> 下一页 </AppButton>
      <AppButton
        variant="neutral"
        :disabled="page === pages"
        class="hidden sm:inline-flex"
        @click="goLast"
      >
        跳转末尾
      </AppButton>
    </div>
    <div class="flex flex-wrap items-center justify-center gap-3">
      <div class="flex items-center gap-2">
        <AppButton variant="neutral" size="sm" @click="emitGoTo(localPage)"> 跳转至第 </AppButton>
        <input
          :id="inputId + '-page'"
          aria-label="跳转页码"
          v-model.number="localPage"
          type="number"
          min="1"
          :max="pages"
          class="page-input w-16 px-2 py-1 rounded-md border focus:outline-none text-center text-sm"
          @keydown.enter="emitGoTo(localPage)"
        />
        <span class="text-sm text-secondary">页</span>
      </div>
      <div class="flex items-center gap-2">
        <label :for="inputId + '-size'" class="text-sm text-secondary">每页条数</label>
        <input
          :id="inputId + '-size'"
          v-model.number="localPageSize"
          type="number"
          min="1"
          class="page-input w-16 px-2 py-1 rounded-md border focus:outline-none text-center text-sm"
          @change="emitPageSizeChange"
        />
        <span class="text-sm text-secondary">条</span>
      </div>
    </div>
  </nav>
</template>

<script>
import AppButton from './AppButton.vue'
import { defineComponent, ref, watch, useId } from 'vue'

export default defineComponent({
  name: 'ResourcePagination',
  components: { AppButton },
  props: {
    page: { type: Number, required: true },
    pages: { type: Number, required: true },
    pageSize: { type: Number, required: true },
    total: { type: Number, required: false, default: 0 },
  },
  emits: ['change-page', 'change-page-size'],
  setup(props, { emit }) {
    const inputId = useId()
    const localPage = ref(props.page)
    const localPageSize = ref(props.pageSize)

    watch(
      () => props.page,
      (v) => {
        localPage.value = v
      }
    )
    watch(
      () => props.pageSize,
      (v) => {
        localPageSize.value = v
      }
    )

    function goFirst() {
      emit('change-page', 1)
    }
    function goPrev() {
      emit('change-page', Math.max(1, props.page - 1))
    }
    function goNext() {
      emit('change-page', Math.min(props.pages, props.page + 1))
    }
    function goLast() {
      emit('change-page', props.pages)
    }

    function emitGoTo(p) {
      const np = Math.trunc(Number(p)) || 1
      emit('change-page', Math.max(1, Math.min(props.pages, np)))
    }

    function emitPageSizeChange() {
      const ns = Math.max(
        1,
        Math.min(200, Math.trunc(Number(localPageSize.value)) || props.pageSize)
      )
      emit('change-page-size', ns)
    }

    return {
      inputId,
      localPage,
      localPageSize,
      goFirst,
      goPrev,
      goNext,
      goLast,
      emitGoTo,
      emitPageSizeChange,
    }
  },
})
</script>

<style scoped>
.page-input {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-color: var(--border-color);
  caret-color: var(--accent-primary-text);
}
.page-input:focus {
  border-color: var(--accent-primary-text);
  box-shadow: 0 0 0 3px var(--focus-ring);
}
.page-input::placeholder {
  color: var(--text-muted);
}
</style>
