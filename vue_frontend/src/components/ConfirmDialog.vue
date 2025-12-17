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
			<div v-if="isVisible" class="confirm-overlay" @click.self="handleCancel">
				<div class="confirm-dialog" :class="`confirm-${type}`">
					<div class="confirm-header">
						<div class="confirm-icon">
							<span v-if="type === 'warning'">⚠</span>
							<span v-else-if="type === 'danger'">✕</span>
							<span v-else>ℹ</span>
						</div>
						<h3 class="confirm-title">{{ title }}</h3>
					</div>

					<div class="confirm-body">
						<p class="confirm-message">{{ message }}</p>
					</div>

					<div class="confirm-footer">
						<button class="btn btn-cancel" @click="handleCancel">
							{{ cancelText }}
						</button>
						<button class="btn btn-confirm" :class="`btn-${type}`" @click="handleConfirm">
							{{ confirmText }}
						</button>
					</div>
				</div>
			</div>
		</Transition>
	</Teleport>
</template>

<style scoped>
.confirm-overlay {
	position: fixed;
	inset: 0;
	background: rgba(0, 0, 0, 0.75);
	backdrop-filter: blur(4px);
	display: flex;
	align-items: center;
	justify-content: center;
	z-index: 10000;
	padding: 1rem;
}

.confirm-dialog {
	background: var(--bg-secondary);
	border-radius: 16px;
	border: 1px solid var(--border-color);
	box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
	min-width: 320px;
	max-width: 480px;
	width: 100%;
	overflow: hidden;
}

.confirm-header {
	padding: 1.5rem 1.5rem 1rem;
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 0.75rem;
}

.confirm-icon {
	width: 56px;
	height: 56px;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 1.75rem;
	font-weight: bold;
}

.confirm-warning .confirm-icon {
	background: rgba(255, 159, 67, 0.15);
	color: var(--accent-secondary);
	border: 2px solid rgba(255, 159, 67, 0.3);
}

.confirm-danger .confirm-icon {
	background: rgba(239, 71, 111, 0.15);
	color: #ef476f;
	border: 2px solid rgba(239, 71, 111, 0.3);
}

.confirm-info .confirm-icon {
	background: rgba(78, 205, 196, 0.15);
	color: var(--accent-tertiary);
	border: 2px solid rgba(78, 205, 196, 0.3);
}

.confirm-title {
	font-size: 1.25rem;
	font-weight: 600;
	color: var(--text-primary);
	text-align: center;
}

.confirm-body {
	padding: 0 1.5rem 1.5rem;
}

.confirm-message {
	font-size: 0.95rem;
	color: var(--text-secondary);
	text-align: center;
	line-height: 1.6;
}

.confirm-footer {
	padding: 1rem 1.5rem 1.5rem;
	display: flex;
	gap: 0.75rem;
	justify-content: center;
}

.btn {
	flex: 1;
	padding: 0.75rem 1.5rem;
	border: none;
	border-radius: 10px;
	font-size: 0.9rem;
	font-weight: 600;
	cursor: pointer;
	transition: all 0.2s ease;
	font-family: inherit;
}

.btn-cancel {
	background: rgba(255, 255, 255, 0.08);
	color: var(--text-secondary);
	border: 1px solid var(--border-color);
}

.btn-cancel:hover {
	background: rgba(255, 255, 255, 0.12);
	color: var(--text-primary);
	transform: translateY(-1px);
}

.btn-confirm {
	color: white;
}

.btn-warning {
	background: var(--accent-secondary);
}

.btn-warning:hover {
	background: #ff8c1a;
	transform: translateY(-1px);
	box-shadow: 0 4px 12px rgba(255, 159, 67, 0.3);
}

.btn-danger {
	background: #ef476f;
}

.btn-danger:hover {
	background: #dc3558;
	transform: translateY(-1px);
	box-shadow: 0 4px 12px rgba(239, 71, 111, 0.3);
}

.btn-info {
	background: var(--accent-tertiary);
}

.btn-info:hover {
	background: #3db9b0;
	transform: translateY(-1px);
	box-shadow: 0 4px 12px rgba(78, 205, 196, 0.3);
}

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

.dialog-enter-from .confirm-dialog {
	transform: scale(0.9) translateY(-20px);
	opacity: 0;
}

.dialog-leave-to .confirm-dialog {
	transform: scale(0.9) translateY(20px);
	opacity: 0;
}

/* 响应式 */
@media (max-width: 480px) {
	.confirm-dialog {
		min-width: unset;
		margin: 0 1rem;
	}

	.confirm-footer {
		flex-direction: column;
	}

	.btn {
		width: 100%;
	}
}
</style>
