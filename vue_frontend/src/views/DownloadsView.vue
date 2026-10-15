<script setup>
import { useSessionStore } from '../features/auth/stores/session.js'
import LegacyDownloadsPage from '../features/tasks/components/LegacyDownloadsPage.vue'
import UserOperationsPage from '../features/tasks/components/UserOperationsPage.vue'

// Set true to preview synthetic download/scrape tasks without real mutations.
const DEBUG_MODE = false
const session = useSessionStore()
</script>

<template>
  <UserOperationsPage v-if="session.capabilities.shared_library && !DEBUG_MODE" />
  <LegacyDownloadsPage v-else :debug="DEBUG_MODE" />
</template>
