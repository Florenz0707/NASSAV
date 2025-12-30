<script setup>
import {ref, watch} from 'vue'

const props = defineProps({
	show: {
		type: Boolean,
		default: false
	},
	title: {
		type: String,
		default: '确认操作'
	},
	message: {
		type: String,
		required: true
	},
	confirmText: {
		type: String,
		default: '确认'
	},
	cancelText: {
		type: String,
		default: '取消'
	},
	type: {
		type: String,
		default: 'warning', // warning, danger, info
		validator: (value) => ['warning', 'danger', 'info'].includes(value)
	}
})

const emit = defineEmits(['confirm', 'cancel', 'update:show'])

const isVisible = ref(props.show)

watch(() => props.show, (val) => {
	isVisible.value = val
})

function handleConfirm() {
	emit('confirm')
	close()
}

function handleCancel() {
	emit('cancel')
	close()
}

function close() {
	isVisible.value = false
	emit('update:show', false)
}

// 阻止背景滚动
watch(isVisible, (val) => {
	if (val) {
		document.body.style.overflow = 'hidden'
	} else {
		document.body.style.overflow = ''
	}
})
</script>

<template>
	<Teleport to="body">
		<Transition name="dialog">
			<div v-if="isVisible" class="fixed inset-0 bg-black/75 backdrop-blur flex items-center justify-center z-[10000] p-4" @click.self="handleCancel">
				<div
					class="bg-[#12121a] rounded-2xl border border-white/[0.08] shadow-[0_20px_60px_rgba(0,0,0,0.5)] min-w-[320px] max-w-[480px] w-full overflow-hidden"
					:class="`confirm-${type}`"
				>
					<!-- Header -->
					<div class="py-6 px-6 pb-4 flex flex-col items-center gap-3">
						<div
							class="w-14 h-14 rounded-full flex items-center justify-center text-[1.75rem] font-bold"
							:class="{
								'bg-[#ff9f43]/15 text-[#ff9f43] border-2 border-[#ff9f43]/30': type === 'warning',
								'bg-[#ef476f]/15 text-[#ef476f] border-2 border-[#ef476f]/30': type === 'danger',
								'bg-[#4ecdc4]/15 text-[#4ecdc4] border-2 border-[#4ecdc4]/30': type === 'info'
							}"
						>
							<span v-if="type === 'warning'">⚠</span>
							<span v-else-if="type === 'danger'">✕</span>
							<span v-else>ℹ</span>
						</div>
						<h3 class="text-xl font-semibold text-[#f4f4f5] text-center">{{ title }}</h3>
					</div>

					<!-- Body -->
					<div class="px-6 pb-6">
						<p class="text-[0.95rem] text-[#a1a1aa] text-center leading-relaxed">{{ message }}</p>
					</div>

					<!-- Footer -->
					<div class="py-4 px-6 pb-6 flex gap-3 justify-center">
						<button
							class="flex-1 py-3 px-6 border-none rounded-[10px] text-sm font-semibold cursor-pointer transition-all duration-200 font-inherit bg-white/[0.08] text-[#a1a1aa] border border-white/[0.08] hover:bg-white/[0.12] hover:text-[#f4f4f5] hover:-translate-y-0.5"
							@click="handleCancel"
						>
							{{ cancelText }}
						</button>
						<button
							class="flex-1 py-3 px-6 border-none rounded-[10px] text-sm font-semibold cursor-pointer transition-all duration-200 font-inherit text-white"
							:class="{
								'bg-[#ff9f43] hover:bg-[#ff8c1a] hover:-translate-y-0.5 hover:shadow-[0_4px_12px_rgba(255,159,67,0.3)]': type === 'warning',
								'bg-[#ef476f] hover:bg-[#dc3558] hover:-translate-y-0.5 hover:shadow-[0_4px_12px_rgba(239,71,111,0.3)]': type === 'danger',
								'bg-[#4ecdc4] hover:bg-[#3db9b0] hover:-translate-y-0.5 hover:shadow-[0_4px_12px_rgba(78,205,196,0.3)]': type === 'info'
							}"
							@click="handleConfirm"
						>
							{{ confirmText }}
						</button>
					</div>
				</div>
			</div>
		</Transition>
	</Teleport>
</template>

<style scoped>
/* 对话框动画 */
.dialog-enter-active,
.dialog-leave-active {
	transition: all 0.3s ease;
}

.dialog-enter-active .confirm-dialog,
.dialog-leave-active .confirm-dialog {
	transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.dialog-enter-from,
.dialog-leave-to {
	opacity: 0;
}

.dialog-enter-from > div {
	transform: scale(0.9) translateY(-20px);
	opacity: 0;
}

.dialog-leave-to > div {
	transform: scale(0.9) translateY(20px);
	opacity: 0;
}

/* 响应式 */
@media (max-width: 480px) {
	.confirm-dialog {
		margin: 0 1rem;
	}
}
</style>
