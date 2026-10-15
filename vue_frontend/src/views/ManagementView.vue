<script setup>
import { useSessionStore } from '../features/auth/stores/session.js'
import ManagementCenter from '../features/admin/components/ManagementCenter.vue'
import EmptyState from '../shared/ui/EmptyState.vue'
const session = useSessionStore()
</script>
<template>
  <ManagementCenter v-if="session.capabilities.app_admin" />
  <EmptyState
    v-else
    icon="empty"
    title="需要应用管理员权限"
    description="当前账号无法访问管理中心。"
  />
</template>
