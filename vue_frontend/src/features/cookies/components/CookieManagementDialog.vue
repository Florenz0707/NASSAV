<script setup>
import { useSessionStore } from '../../auth/stores/session.js'
import PersonalCredentialsDialog from './PersonalCredentialsDialog.vue'
import LegacyCookieManagementDialog from './LegacyCookieManagementDialog.vue'
const emit = defineEmits(['close'])
const session = useSessionStore()
</script>
<template>
  <PersonalCredentialsDialog
    v-if="session.capabilities.personal_source_credentials"
    @close="emit('close')"
  />
  <LegacyCookieManagementDialog v-else @close="emit('close')" />
</template>
