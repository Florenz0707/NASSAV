<template>
  <div v-if="pages > 1" class="mt-8 w-full">
    <div class="flex items-center justify-center gap-3 mb-3">
      <button @click="goFirst" :disabled="page === 1"
        class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md transform transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0">
        跳转开头
      </button>
      <button @click="goPrev" :disabled="page === 1"
        class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md transform transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0">
        上一页
      </button>
      <div class="px-4 py-2 rounded-md bg-[rgba(255,255,255,0.03)] text-[#f4f4f5]">第 {{ page }} 页 / 共 {{ pages }} 页</div>
      <button @click="goNext" :disabled="page === pages"
        class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md transform transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0">
        下一页
      </button>
      <button @click="goLast" :disabled="page === pages"
        class="px-4 py-2 rounded-lg bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md transform transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0">
        跳转末尾
      </button>
    </div>
    <div class="flex items-center justify-center gap-4">
      <div class="flex items-center gap-2">
        <button class="px-3 py-1 rounded-md bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white shadow-md" @click="emitGoTo(page)">跳转至第</button>
        <input v-model.number="localPage" @keydown.enter="emitGoTo(localPage)" type="number" min="1" :max="pages"
          class="w-20 px-3 py-1 rounded-md bg-[#1b1b26] text-[#f4f4f5] border border-white/[0.06] focus:outline-none text-center" />
        <label class="text-sm text-[#bcbcbc]">页</label>
      </div>
      <div class="flex items-center gap-2">
        <label class="text-sm text-[#bcbcbc]">每页显示</label>
        <input v-model.number="localPageSize" @change="emitPageSizeChange" type="number" min="1"
          class="w-20 px-3 py-1 rounded-md bg-[#1b1b26] text-[#f4f4f5] border border-white/[0.06] focus:outline-none text-center" />
        <label class="text-sm text-[#bcbcbc]">个资源卡</label>
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent, ref, watch } from 'vue'

export default defineComponent({
  name: 'ResourcePagination',
  props: {
    page: { type: Number, required: true },
    pages: { type: Number, required: true },
    pageSize: { type: Number, required: true },
    total: { type: Number, required: false, default: 0 }
  },
  emits: ['change-page', 'change-page-size'],
  setup(props, { emit }) {
    const localPage = ref(props.page)
    const localPageSize = ref(props.pageSize)

    watch(() => props.page, (v) => { localPage.value = v })
    watch(() => props.pageSize, (v) => { localPageSize.value = v })

    function goFirst() { emit('change-page', 1) }
    function goPrev() { emit('change-page', Math.max(1, props.page - 1)) }
    function goNext() { emit('change-page', Math.min(props.pages, props.page + 1)) }
    function goLast() { emit('change-page', props.pages) }
    function emitGoTo(p) { const np = Number(p) || 1; emit('change-page', Math.max(1, Math.min(props.pages, np))) }
    function emitPageSizeChange() { const ns = Number(localPageSize.value) || props.pageSize; emit('change-page-size', ns) }

    return { localPage, localPageSize, goFirst, goPrev, goNext, goLast, emitGoTo, emitPageSizeChange }
  }
})
</script>

<style scoped>
/* keep styling consistent with ResourcesView */
</style>
