<script setup>
import { ref, watch } from 'vue'

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
			<div v-if="isVisible"
				class="fixed inset-0 bg-black/75 backdrop-blur flex items-center justify-center z-[10000] p-4"
				@click.self="handleCancel">
				<div class="rounded-2xl border shadow-[0_20px_60px_rgba(0,0,0,0.5)] min-w-[320px] max-w-[480px] w-full overflow-hidden"
					style="background: var(--bg-secondary); border-color: var(--border-color);"
					:class="`confirm-${type}`">
					<!-- Header -->
					<div class="py-6 px-6 pb-4 flex flex-col items-center gap-3">
						<div class="w-14 h-14 rounded-full flex items-center justify-center border-2"
							:style="{
								background: type === 'warning' ? 'rgba(255,159,67,0.15)' : type === 'danger' ? 'rgba(239,71,111,0.15)' : 'rgba(78,205,196,0.15)',
								color: type === 'warning' ? 'var(--accent-secondary)' : type === 'danger' ? 'var(--accent-danger)' : 'var(--accent-tertiary)',
								borderColor: type === 'warning' ? 'rgba(255,159,67,0.3)' : type === 'danger' ? 'rgba(239,71,111,0.3)' : 'rgba(78,205,196,0.3)'
							}">
							<!-- warning -->
							<svg v-if="type === 'warning'" class="w-7 h-7" viewBox="0 0 20 20" fill="currentColor">
								<path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"/>
							</svg>
							<!-- danger -->
							<svg v-else-if="type === 'danger'" class="w-7 h-7" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M6 6l8 8M14 6l-8 8"/>
							</svg>
							<!-- info -->
							<svg v-else class="w-7 h-7" viewBox="0 0 20 20" fill="currentColor">
								<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"/>
							</svg>
						</div>
						<h3 class="text-xl font-semibold text-center" style="color: var(--text-primary);">
							{{ title }}
						</h3>
					</div>

					<!-- Body -->
					<div class="px-6 pb-6">
						<p class="text-[0.95rem] text-center leading-relaxed" style="color: var(--text-secondary);">
							{{ message }}
						</p>
					</div>

					<!-- Footer -->
					<div class="py-4 px-6 pb-6 flex gap-3 justify-center">
						<button
							class="flex-1 py-3 px-6 border rounded-[10px] text-sm font-semibold cursor-pointer transition-all duration-200 font-inherit bg-white/[0.08] hover:bg-white/[0.12] hover:-translate-y-0.5"
							style="color: var(--text-secondary); border-color: var(--border-color);"
							@click="handleCancel">
							{{ cancelText }}
						</button>
						<button
							class="flex-1 py-3 px-6 border-none rounded-[10px] text-sm font-semibold cursor-pointer transition-all duration-200 font-inherit text-white hover:-translate-y-0.5"
							:style="{
								background: type === 'warning' ? 'var(--accent-secondary)' : type === 'danger' ? 'var(--accent-danger)' : 'var(--accent-tertiary)'
							}"
							@click="handleConfirm">
							{{ confirmText }}
						</button>
						<slot name="extra-button" />
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

.dialog-enter-from>div {
	transform: scale(0.9) translateY(-20px);
	opacity: 0;
}

.dialog-leave-to>div {
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
