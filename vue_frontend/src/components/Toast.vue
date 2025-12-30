<script setup>
import {useToastStore} from '../stores/toast'

const toastStore = useToastStore()

const iconMap = {
	success: '✓',
	error: '✕',
	warning: '⚠',
	info: 'ℹ'
}
</script>

<template>
	<Teleport to="body">
		<div class="fixed top-20 right-5 z-[9999] flex flex-col gap-3">
			<TransitionGroup name="toast">
				<div
					v-for="toast in toastStore.toasts"
					:key="toast.id"
					class="flex items-center gap-3 px-5 py-4 rounded-xl bg-[rgba(30,30,40,0.95)] backdrop-blur-[10px] border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.3)] cursor-pointer min-w-[280px] max-w-[400px]"
					:class="`toast-${toast.type}`"
					@click="toastStore.remove(toast.id)"
				>
					<span
						class="w-6 h-6 rounded-full flex items-center justify-center text-[0.85rem] font-semibold flex-shrink-0"
						:class="{
							'bg-[#2ed573]/20 text-[#2ed573]': toast.type === 'success',
							'bg-[#ff6b6b]/20 text-[#ff6b6b]': toast.type === 'error',
							'bg-[#ffc107]/20 text-[#ffc107]': toast.type === 'warning',
							'bg-[#4ecdc4]/20 text-[#4ecdc4]': toast.type === 'info'
						}"
					>
						{{ iconMap[toast.type] }}
					</span>
					<span class="text-sm text-[#f4f4f5] leading-[1.4]">{{ toast.message }}</span>
				</div>
			</TransitionGroup>
		</div>
	</Teleport>
</template>

<style scoped>
.toast-enter-active {
	animation: toastIn 0.3s ease;
}

.toast-leave-active {
	animation: toastOut 0.3s ease;
}

@keyframes toastIn {
	from {
		opacity: 0;
		transform: translateX(100px);
	}
	to {
		opacity: 1;
		transform: translateX(0);
	}
}

@keyframes toastOut {
	from {
		opacity: 1;
		transform: translateX(0);
	}
	to {
		opacity: 0;
		transform: translateX(100px);
	}
}
</style>
