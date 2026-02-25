<script setup>
defineProps({
	size: {
		type: String,
		default: 'medium'
	},
	text: {
		type: String,
		default: ''
	}
})
</script>

<template>
	<div class="flex flex-row items-center justify-center" :class="size">
		<div class="relative flex items-center justify-center spinner">
			<div class="absolute rounded-full border-2 border-transparent animate-spin spinner-ring ring-1"/>
			<div class="absolute rounded-full border-2 border-transparent animate-[spin_1.2s_linear_0.1s_infinite_reverse] spinner-ring-2 ring-2"/>
			<div class="absolute rounded-full border-2 border-transparent animate-[spin_1.2s_linear_0.2s_infinite] spinner-ring-3 ring-3"/>
		</div>
		<p v-if="text" class="text-sm ml-3 animate-pulse" style="color: var(--text-muted);">
			{{ text }}
		</p>
	</div>
</template>

<style scoped>
.small .spinner { width: 12px; height: 12px; }
.medium .spinner { width: 24px; height: 24px; }
.large .spinner { width: 48px; height: 48px; }

.small .spinner-ring { border-width: 2px; }
.medium .spinner-ring { border-width: 3px; }
.large .spinner-ring { border-width: 4px; }

.spinner-ring { width: 100%; height: 100%; }
.spinner-ring-2 { width: 75%; height: 75%; }
.spinner-ring-3 { width: 50%; height: 50%; }

.ring-1 { border-top-color: var(--accent-primary); }
.ring-2 { border-top-color: var(--accent-secondary); }
.ring-3 { border-top-color: var(--accent-tertiary); }

@keyframes spin {
	0% { transform: rotate(0deg); }
	100% { transform: rotate(360deg); }
}
</style>
