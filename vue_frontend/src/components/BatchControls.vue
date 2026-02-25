<template>
	<div class="mb-4 flex flex-wrap items-center gap-2">
		<div>
			<button class="inline-flex items-center justify-center px-3 py-2 h-10 rounded-md bg-white/[0.06] hover:bg-white/10 transition-colors duration-200"
				style="color: var(--text-primary);"
				@click="$emit('toggle-batch-mode')">
				<span class="text-sm">{{ batchMode ? '退出批量' : '批量操作' }}</span>
			</button>
		</div>

		<div v-if="batchMode" class="flex items-center gap-2 flex-wrap">
			<label class="inline-flex items-center gap-3 text-sm" style="color: var(--text-secondary);">
				<label class="inline-flex items-center cursor-pointer">
					<input type="checkbox" class="sr-only"
						:checked="selectedCount === totalCount && totalCount > 0"
						@change="$emit('toggle-select-all', $event.target.checked)">
					<span
						class="w-5 h-5 flex items-center justify-center rounded-md transition border-2"
						:style="(selectedCount === totalCount && totalCount > 0)
							? 'background: linear-gradient(135deg, var(--accent-primary), #ff5252); border-color: white;'
							: 'background: rgba(128,128,128,0.6); border-color: white;'">
						<svg v-if="selectedCount === totalCount && totalCount > 0"
							class="w-3 h-3 text-white" viewBox="0 0 20 20" fill="currentColor">
							<path fill-rule="evenodd" clip-rule="evenodd"
								d="M16.707 5.293a1 1 0 00-1.414-1.414L7 12.172l-2.293-2.293A1 1 0 003.293 11.293l3 3a1 1 0 001.414 0l9-9z"/>
						</svg>
					</span>
				</label>
				<span>已选择 {{ selectedCount }} 项</span>
			</label>
			<button
				class="inline-flex items-center justify-center px-3 py-2 h-10 rounded-md bg-white/[0.06] text-sm hover:bg-white/10 disabled:opacity-60 transition-colors duration-200"
				style="color: var(--text-primary);"
				:disabled="batchLoading" @click="$emit('batch-refresh')">
				批量刷新
			</button>
			<button
				class="inline-flex items-center justify-center px-3 py-2 h-10 rounded-md text-white shadow text-sm hover:brightness-105 disabled:opacity-60 transition-all duration-200"
				style="background: linear-gradient(135deg, var(--accent-primary), #ff5252);"
				:disabled="batchLoading" @click="$emit('batch-download')">
				批量下载
			</button>
			<button
				class="inline-flex items-center justify-center px-3 py-2 h-10 rounded-md text-white shadow text-sm hover:brightness-95 disabled:opacity-60 transition-all duration-200"
				style="background: var(--accent-danger);"
				:disabled="batchLoading" @click="$emit('batch-delete')">
				批量删除
			</button>
		</div>
	</div>
</template>

<script setup>
defineProps({
	batchMode: {
		type: Boolean,
		default: false
	},
	batchLoading: {
		type: Boolean,
		default: false
	},
	selectedCount: {
		type: Number,
		default: 0
	},
	totalCount: {
		type: Number,
		default: 0
	}
})

defineEmits(['toggle-batch-mode', 'toggle-select-all', 'batch-refresh', 'batch-download', 'batch-delete'])
</script>
