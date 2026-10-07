<script setup>
import PageLoad from '../../../shared/ui/PageLoad.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
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

    <PageLoad v-if="loading" variant="spinner" text="正在加载 Cookie" />

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
            class="hover:bg-surface-subtle/[0.02] transition-colors"
            style="
              border-bottom: 1px solid color-mix(in srgb, var(--neutral-color) 4%, transparent);
            "
          >
            <td class="py-4 px-4 text-[var(--text-primary)] font-medium">
              {{ source.name }}
            </td>
            <td class="py-4 px-4">
              <CookieStatusBadge
                :has-cookie="source.hasCookie"
                :verified-direct-reuse="source.verifiedDirectReuse"
                :session-expired="source.sessionExpired"
              />
            </td>
            <td class="py-4 px-4 text-sm text-[var(--text-muted)]">
              {{ source.lastUpdate || '-' }}
            </td>
            <td class="py-4 px-4">
              <div class="flex gap-2">
                <AppButton
                  variant="neutral"
                  size="sm"
                  :disabled="!source.hasCookie"
                  @click="emit('view', source)"
                >
                  查看
                </AppButton>
                <AppButton variant="neutral" size="sm" @click="emit('edit', source)">
                  更新
                </AppButton>
                <AppButton variant="danger" size="sm" @click="emit('delete', source)">
                  删除
                </AppButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <EmptyState v-else icon="empty" title="暂无可用的下载源" />

    <div
      v-if="sources.length > 0"
      class="mt-6 p-4 rounded-lg"
      style="
        background: color-mix(in srgb, var(--accent-tertiary) 5%, transparent);
        border: 1px solid color-mix(in srgb, var(--accent-tertiary) 20%, transparent);
      "
    >
      <div class="flex flex-col gap-3 sm:flex-row">
        <svg
          class="w-5 h-5 text-accent-tertiary flex-shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <circle cx="12" cy="12" r="10" stroke-width="2"></circle>
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 8v4m0 4h.01"
          ></path>
        </svg>
        <div class="text-sm text-muted">
          <p class="mb-2">
            <span class="text-primary font-medium">关于 Cookie：</span>
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
