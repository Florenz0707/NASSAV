<template>
	<div class="mt-8 w-full">
		<div class="flex flex-wrap items-center justify-center gap-2 mb-3">
			<button :disabled="page === 1" class="hidden sm:inline-flex px-4 py-2 rounded-lg text-white shadow-md transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0"
				style="background: linear-gradient(135deg, var(--accent-primary), #ff5252);"
				@click="goFirst">
				跳转开头
			</button>
			<button :disabled="page === 1" class="px-4 py-2 rounded-lg text-white shadow-md transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0"
				style="background: linear-gradient(135deg, var(--accent-primary), #ff5252);"
				@click="goPrev">
				上一页
			</button>
			<div class="px-4 py-2 rounded-md bg-white/[0.03] text-sm" style="color: var(--text-primary);">
				第 {{ page }} 页 / 共 {{ pages }} 页
			</div>
			<button :disabled="page === pages" class="px-4 py-2 rounded-lg text-white shadow-md transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0"
				style="background: linear-gradient(135deg, var(--accent-primary), #ff5252);"
				@click="goNext">
				下一页
			</button>
			<button :disabled="page === pages" class="hidden sm:inline-flex px-4 py-2 rounded-lg text-white shadow-md transition-transform duration-200 hover:-translate-y-1 disabled:opacity-50 disabled:translate-y-0"
				style="background: linear-gradient(135deg, var(--accent-primary), #ff5252);"
				@click="goLast">
				跳转末尾
			</button>
		</div>
		<div class="flex flex-wrap items-center justify-center gap-3">
			<div class="flex items-center gap-2">
				<button class="px-3 py-1 rounded-md text-white shadow-md text-sm"
					style="background: linear-gradient(135deg, var(--accent-primary), #ff5252);"
					@click="emitGoTo(localPage)">
					跳转至第
				</button>
				<input v-model.number="localPage" type="number" min="1" :max="pages"
					class="page-input w-16 px-2 py-1 rounded-md border focus:outline-none text-center text-sm"
					@keydown.enter="emitGoTo(localPage)">
				<label class="text-sm" style="color: var(--text-secondary);">页</label>
			</div>
			<div class="flex items-center gap-2">
				<label class="text-sm" style="color: var(--text-secondary);">每页</label>
				<input v-model.number="localPageSize" type="number" min="1"
					class="page-input w-16 px-2 py-1 rounded-md border focus:outline-none text-center text-sm"
					@change="emitPageSizeChange">
				<label class="text-sm" style="color: var(--text-secondary);">条</label>
			</div>
		</div>
	</div>
</template>

<script>
import {defineComponent, ref, watch} from 'vue'

export default defineComponent({
	name: 'ResourcePagination',
	props: {
		page: {type: Number, required: true},
		pages: {type: Number, required: true},
		pageSize: {type: Number, required: true},
		total: {type: Number, required: false, default: 0}
	},
	emits: ['change-page', 'change-page-size'],
	setup(props, {emit}) {
		const localPage = ref(props.page)
		const localPageSize = ref(props.pageSize)

		watch(() => props.page, (v) => { localPage.value = v })
		watch(() => props.pageSize, (v) => { localPageSize.value = v })

		function goFirst() { emit('change-page', 1) }
		function goPrev() { emit('change-page', Math.max(1, props.page - 1)) }
		function goNext() { emit('change-page', Math.min(props.pages, props.page + 1)) }
		function goLast() { emit('change-page', props.pages) }

		function emitGoTo(p) {
			const np = Number(p) || 1
			emit('change-page', Math.max(1, Math.min(props.pages, np)))
		}

		function emitPageSizeChange() {
			const ns = Number(localPageSize.value) || props.pageSize
			emit('change-page-size', ns)
		}

		return {localPage, localPageSize, goFirst, goPrev, goNext, goLast, emitGoTo, emitPageSizeChange}
	}
})
</script>

<style scoped>
.page-input {
	background: var(--bg-secondary);
	color: var(--text-primary);
	border-color: var(--border-color);
}
</style>
