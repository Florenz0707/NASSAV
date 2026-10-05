<script setup>
import { ref } from 'vue'
import { useSessionStore } from '../stores/session'

const sessionStore = useSessionStore()
const username = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')

async function submit() {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    await sessionStore.signIn(username.value.trim(), password.value)
    password.value = ''
  } catch (error) {
    errorMessage.value = error.message || '登录失败，请检查连接后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto flex min-h-screen max-w-md items-center px-4 py-8">
    <form
      class="w-full rounded-xl border border-surface-subtle/10 bg-secondary p-6 shadow-lg"
      @submit.prevent="submit"
    >
      <div class="mb-6 flex items-center gap-3">
        <span
          class="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-primary text-on-accent"
        >
          <svg
            class="h-5 w-5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <rect x="5" y="10" width="14" height="11" rx="2" />
            <path stroke-linecap="round" d="M8 10V7a4 4 0 0 1 8 0v3" />
          </svg>
        </span>
        <div>
          <h1 class="text-xl font-semibold text-primary">登录 NASSAV</h1>
          <p class="text-sm text-secondary">使用管理员账号继续</p>
        </div>
      </div>

      <label for="login-username" class="mb-2 block text-sm text-secondary">用户名</label>
      <input
        id="login-username"
        v-model="username"
        name="username"
        autocomplete="username"
        required
        class="mb-4 w-full rounded-lg border border-surface-subtle/10 bg-primary px-3 py-2 text-primary outline-none focus:border-accent-primary"
      />
      <label for="login-password" class="mb-2 block text-sm text-secondary">密码</label>
      <input
        id="login-password"
        v-model="password"
        name="password"
        type="password"
        autocomplete="current-password"
        required
        class="mb-4 w-full rounded-lg border border-surface-subtle/10 bg-primary px-3 py-2 text-primary outline-none focus:border-accent-primary"
      />
      <p v-if="errorMessage" role="alert" class="mb-4 text-sm text-accent-danger">
        {{ errorMessage }}
      </p>
      <button
        type="submit"
        :disabled="submitting"
        class="w-full rounded-lg bg-accent-primary px-4 py-2 font-medium text-on-accent transition-colors duration-200 hover:opacity-80 disabled:cursor-wait disabled:opacity-60"
      >
        {{ submitting ? '正在登录…' : '登录' }}
      </button>
    </form>
  </div>
</template>
