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
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div
            v-for="toast in toastStore.toasts"
            :key="toast.id"
            :class="['toast', `toast-${toast.type}`]"
            @click="toastStore.remove(toast.id)"
        >
          <span class="toast-icon">{{ iconMap[toast.type] }}</span>
          <span class="toast-message">{{ toast.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: 80px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.toast {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border-radius: 12px;
  background: rgba(30, 30, 40, 0.95);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  min-width: 280px;
  max-width: 400px;
}

.toast-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  font-weight: 600;
  flex-shrink: 0;
}

.toast-message {
  font-size: 0.9rem;
  color: var(--text-primary);
  line-height: 1.4;
}

.toast-success .toast-icon {
  background: rgba(46, 213, 115, 0.2);
  color: #2ed573;
}

.toast-error .toast-icon {
  background: rgba(255, 107, 107, 0.2);
  color: #ff6b6b;
}

.toast-warning .toast-icon {
  background: rgba(255, 193, 7, 0.2);
  color: #ffc107;
}

.toast-info .toast-icon {
  background: rgba(78, 205, 196, 0.2);
  color: #4ecdc4;
}

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
