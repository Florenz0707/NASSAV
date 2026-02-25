<script setup>
import {useToastStore} from '../stores/toast'

const toastStore = useToastStore()
</script>

<template>
	<Teleport to="body">
		<div class="fixed top-20 right-5 z-[9999] flex flex-col gap-3" aria-live="polite" aria-atomic="false">
			<TransitionGroup name="toast">
				<div
					v-for="toast in toastStore.toasts"
					:key="toast.id"
					:role="toast.type === 'error' ? 'alert' : 'status'"
					class="flex items-center gap-3 px-5 py-4 rounded-xl backdrop-blur-[10px] border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.3)] cursor-pointer min-w-[280px] max-w-[400px]"
					:class="`toast-${toast.type}`"
					style="background: var(--bg-overlay);"
					@click="toastStore.remove(toast.id)"
				>
					<span
						class="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0"
						:style="{
							'background': toast.type === 'success' ? 'rgba(46,213,115,0.2)' : toast.type === 'error' ? 'rgba(255,107,107,0.2)' : toast.type === 'warning' ? 'rgba(255,193,7,0.2)' : 'rgba(78,205,196,0.2)',
							'color': toast.type === 'success' ? 'var(--accent-success)' : toast.type === 'error' ? 'var(--accent-primary)' : toast.type === 'warning' ? 'var(--accent-warning)' : 'var(--accent-tertiary)'
						}"
					>
						<!-- success -->
						<svg v-if="toast.type === 'success'" class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M4 10l5 5 7-7"/>
						</svg>
						<!-- error -->
						<svg v-else-if="toast.type === 'error'" class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 6l8 8M14 6l-8 8"/>
						</svg>
						<!-- warning -->
						<svg v-else-if="toast.type === 'warning'" class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
							<path d="M10 2L1 17h18L10 2zm0 3l6.5 11h-13L10 5zm-1 4v3h2V9H9zm0 4v2h2v-2H9z"/>
						</svg>
						<!-- info -->
						<svg v-else class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
							<path d="M10 2a8 8 0 100 16A8 8 0 0010 2zm1 11H9V9h2v4zm0-6H9V5h2v2z"/>
						</svg>
					</span>
					<span class="text-sm leading-[1.4]" style="color: var(--text-primary);">{{ toast.message }}</span>
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
