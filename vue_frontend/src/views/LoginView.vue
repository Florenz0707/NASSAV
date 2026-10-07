<script setup>
import { ref, watch } from 'vue'
import AppInput from '../shared/ui/AppInput.vue'
import AppButton from '../shared/ui/AppButton.vue'
import { useSessionStore } from '../features/auth/stores/session.js'

const sessionStore = useSessionStore()
const username = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const credentialsError = ref('')
watch([username, password], () => {
  credentialsError.value = ''
})

async function submit() {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  credentialsError.value = ''
  try {
    await sessionStore.signIn(username.value.trim(), password.value)
    password.value = ''
  } catch (error) {
    errorMessage.value = error.message || '登录失败，请检查连接后重试'
    if (error.httpStatus === 401 || error.code === 401) credentialsError.value = errorMessage.value
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
      <AppInput
        id="login-username"
        v-model="username"
        name="username"
        placeholder="输入管理员用户名"
        autocomplete="username"
        required
        class="mb-4"
        :disabled="submitting"
      />
      <label for="login-password" class="mb-2 block text-sm text-secondary">密码</label>
      <AppInput
        id="login-password"
        v-model="password"
        name="password"
        placeholder="输入登录密码"
        :error="credentialsError"
        type="password"
        autocomplete="current-password"
        required
        class="mb-4"
        :disabled="submitting"
      />
      <p
        v-if="errorMessage && !credentialsError"
        role="alert"
        class="mb-4 text-sm text-accent-danger"
      >
        {{ errorMessage }}
      </p>
      <AppButton type="submit" :loading="submitting" loading-text="正在登录" class="w-full">
        登录
      </AppButton>
    </form>
  </div>
</template>
