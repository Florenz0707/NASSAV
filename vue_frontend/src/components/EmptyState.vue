<script setup>
defineProps({
	icon: {
		type: String,
		default: '◇'
	},
	title: {
		type: String,
		required: true
	},
	description: {
		type: String,
		default: ''
	}
})
</script>

<template>
	<div class="flex flex-col items-center justify-center py-16 px-8 text-center">
		<div class="text-6xl opacity-30 mb-6 animate-[float_3s_ease-in-out_infinite]">
			{{ icon }}
		</div>
		<h3 class="text-xl font-semibold text-[#f4f4f5] mb-2">
			{{ title }}
		</h3>
		<p v-if="description" class="text-[0.95rem] text-[#71717a] max-w-[400px] leading-relaxed">
			{{ description }}
		</p>
		<div class="mt-6">
			<slot name="action"/>
		</div>
	</div>
</template>

<style scoped>
@keyframes float {
	0%, 100% {
		transform: translateY(0);
	}
	50% {
		transform: translateY(-10px);
	}
}
</style>
