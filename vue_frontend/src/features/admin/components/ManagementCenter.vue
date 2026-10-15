<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppButton from '../../../shared/ui/AppButton.vue'
import AdminAccounts from './AdminAccounts.vue'
import AdminAudit from './AdminAudit.vue'
import AdminSourceCredentials from './AdminSourceCredentials.vue'
import AdminResources from './AdminResources.vue'
import AdminWork from './AdminWork.vue'
import { useSessionStore } from '../../auth/stores/session.js'
const session = useSessionStore()
const route = useRoute(),
  router = useRouter()
const sections = computed(() => [
  { value: 'accounts', label: '账号管理', component: AdminAccounts },
  { value: 'sources', label: '系统来源凭证', component: AdminSourceCredentials },
  ...(session.capabilities.shared_library
    ? [
        { value: 'resources', label: '共享资源', component: AdminResources },
        { value: 'gc', label: '回收记录', component: AdminResources, jobs: true },
      ]
    : []),
  { value: 'work', label: '全局执行', component: AdminWork },
  { value: 'audit', label: '审计记录', component: AdminAudit },
])
const current = computed(
  () => sections.value.find((item) => item.value === route.params.section) || sections.value[0]
)
</script>
<template>
  <section class="max-w-7xl mx-auto px-4 py-8" aria-labelledby="management-title">
    <header class="mb-8">
      <h1 id="management-title" class="text-2xl font-semibold text-primary">管理中心</h1>
      <p class="text-muted text-sm mt-2">管理应用账号、策略与审计</p>
    </header>
    <div class="grid grid-cols-1 lg:grid-cols-[12rem_minmax(0,1fr)] gap-8 items-start">
      <nav aria-label="管理中心功能" class="flex flex-wrap lg:flex-col gap-2 self-start lg:w-48">
        <AppButton
          v-for="section in sections"
          :key="section.value"
          class="lg:w-full whitespace-nowrap"
          :variant="current.value === section.value ? 'primary' : 'neutral'"
          :aria-current="current.value === section.value ? 'page' : undefined"
          @click="router.push({ name: 'Management', params: { section: section.value } })"
          >{{ section.label }}</AppButton
        >
      </nav>
      <component
        :is="current.component"
        :key="current.value"
        :jobs="current.jobs"
        class="min-w-0"
      />
    </div>
  </section>
</template>
