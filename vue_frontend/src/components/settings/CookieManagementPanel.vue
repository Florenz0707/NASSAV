<script setup>
import CookieStatusBadge from './CookieStatusBadge.vue'

defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
  sources: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['view', 'edit', 'delete'])
</script>

<template>
  <div>
    <div class="mb-6">
      <h2 class="text-xl font-semibold text-[var(--text-primary)] mb-2">Cookie 管理</h2>
      <p class="text-sm text-[var(--text-muted)]">管理各个下载源的 Cookie 配置，确保正常访问</p>
    </div>

    <div v-if="loading" class="text-center py-12">
      <div
        class="inline-block animate-spin rounded-full h-8 w-8"
        style="border-bottom: 2px solid var(--accent-primary)"
      />
      <p class="mt-3 text-[var(--text-muted)]">加载中...</p>
    </div>

    <div v-else-if="sources.length > 0" class="overflow-x-auto">
      <table class="w-full">
        <thead>
          <tr style="border-bottom: 1px solid var(--border-color)">
            <th class="text-left py-3 px-4 text-sm font-semibold text-[var(--text-muted)]">
              下载源
            </th>
            <th class="text-left py-3 px-4 text-sm font-semibold text-[var(--text-muted)]">
              Cookie 状态
            </th>
            <th class="text-left py-3 px-4 text-sm font-semibold text-[var(--text-muted)]">
              更新时间
            </th>
            <th class="text-left py-3 px-4 text-sm font-semibold text-[var(--text-muted)]">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="source in sources"
            :key="source.name"
            class="hover:bg-white/[0.02] transition-colors"
            style="border-bottom: 1px solid rgba(255, 255, 255, 0.04)"
          >
            <td class="py-4 px-4 text-[var(--text-primary)] font-medium">
              {{ source.name }}
            </td>
            <td class="py-4 px-4">
              <CookieStatusBadge :has-cookie="source.hasCookie" />
            </td>
            <td class="py-4 px-4 text-sm text-[var(--text-muted)]">
              {{ source.lastUpdate || '-' }}
            </td>
            <td class="py-4 px-4">
              <div class="flex gap-2">
                <button
                  class="cookie-btn cookie-btn-view"
                  :disabled="!source.hasCookie"
                  @click="emit('view', source)"
                >
                  查看
                </button>
                <button class="cookie-btn cookie-btn-update" @click="emit('edit', source)">
                  更新
                </button>
                <button class="cookie-btn cookie-btn-delete" @click="emit('delete', source)">
                  删除
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else class="text-center py-12 text-[var(--text-muted)]">
      <div class="text-4xl mb-3">📭</div>
      <p>暂无可用的下载源</p>
    </div>

    <div
      v-if="sources.length > 0"
      class="mt-6 p-4 rounded-lg"
      style="background: rgba(78, 205, 196, 0.05); border: 1px solid rgba(78, 205, 196, 0.2)"
    >
      <div class="flex gap-3">
        <span class="text-[var(--accent-tertiary)] text-lg flex-shrink-0">ℹ️</span>
        <div class="text-sm text-[var(--text-muted)]">
          <p class="mb-2">
            <span class="text-[var(--text-primary)] font-medium">关于 Cookie：</span>
          </p>
          <ul class="list-disc list-inside space-y-1 text-[var(--text-muted)]">
            <li>Cookie 用于访问需要登录的下载源（如 MissAV）</li>
            <li>可以手动设置 Cookie，也可以使用"自动获取"功能</li>
            <li>Cookie 会定期失效，建议定期更新</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cookie-btn {
  border-radius: 0.5rem;
  border: 1px solid transparent;
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  line-height: 1.25rem;
  transition: all 0.2s ease;
}

.cookie-btn-view {
  border-color: rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary);
}

.cookie-btn-view:hover:not(:disabled) {
  border-color: rgba(255, 255, 255, 0.24);
  background: rgba(255, 255, 255, 0.12);
  color: var(--text-primary);
}

.cookie-btn-view:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.cookie-btn-update {
  border-color: rgba(255, 107, 107, 0.25);
  background: rgba(255, 107, 107, 0.12);
  color: #ff8b8b;
}

.cookie-btn-update:hover {
  border-color: rgba(255, 107, 107, 0.38);
  background: rgba(255, 107, 107, 0.2);
  color: #ffb3b3;
}

.cookie-btn-delete {
  border-color: rgba(239, 68, 68, 0.25);
  background: rgba(239, 68, 68, 0.11);
  color: #f87171;
}

.cookie-btn-delete:hover {
  border-color: rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.2);
  color: #fca5a5;
}
</style>
