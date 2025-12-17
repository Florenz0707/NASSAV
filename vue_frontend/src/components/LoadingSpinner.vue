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
	<div class="loading-container" :class="size">
		<div class="spinner">
			<div class="spinner-ring"></div>
			<div class="spinner-ring"></div>
			<div class="spinner-ring"></div>
		</div>
		<p v-if="text" class="loading-text">{{ text }}</p>
	</div>
</template>

<style scoped>
.loading-container {
	display: flex;
	flex-direction: row;
	align-items: center;
	justify-content: center;
}

.spinner {
	position: relative;
	display: flex;
	align-items: center;
	justify-content: center;
}

.small .spinner {
	width: 12px;
	height: 12px;
}

.medium .spinner {
	width: 24px;
	height: 24px;
}

.large .spinner {
	width: 48px;
	height: 48px;
}

.spinner-ring {
	position: absolute;
	border-radius: 50%;
	border: 2px solid transparent;
	animation: spin 1.2s linear infinite;
}

.small .spinner-ring {
	border-width: 2px;
}

.medium .spinner-ring {
	border-width: 3px;
}

.large .spinner-ring {
	border-width: 4px;
}

.spinner-ring:nth-child(1) {
	width: 100%;
	height: 100%;
	border-top-color: var(--accent-primary);
	animation-delay: 0s;
}

.spinner-ring:nth-child(2) {
	width: 75%;
	height: 75%;
	border-top-color: var(--accent-secondary);
	animation-delay: 0.1s;
	animation-direction: reverse;
}

.spinner-ring:nth-child(3) {
	width: 50%;
	height: 50%;
	border-top-color: var(--accent-tertiary);
	animation-delay: 0.2s;
}

@keyframes spin {
	0% {
		transform: rotate(0deg);
	}
	100% {
		transform: rotate(360deg);
	}
}

.loading-text {
	font-size: 0.9rem;
	color: var(--text-muted);
	animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
	0%, 100% {
		opacity: 0.5;
	}
	50% {
		opacity: 1;
	}
}
</style>
