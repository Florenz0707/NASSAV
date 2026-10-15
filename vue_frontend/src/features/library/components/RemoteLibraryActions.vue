<script setup>
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '../../auth/stores/session.js'
import { useMembershipsStore } from '../stores/memberships.js'
import RemoteResourceActions from '../../resources/components/RemoteResourceActions.vue'

const props = defineProps({
  avid: { type: String, required: true },
  adding: Boolean,
  added: Boolean,
})
const emit = defineEmits(['add', 'open', 'view'])
const router = useRouter(),
  session = useSessionStore(),
  memberships = useMembershipsStore()
const shared = computed(() => Boolean(session.capabilities.shared_library))
const status = computed(() => (shared.value ? memberships.get(props.avid) : null))
const error = computed(() => (shared.value ? memberships.errors.get(props.avid) || '' : ''))
const owned = computed(() => (shared.value ? Boolean(status.value?.is_in_my_library) : props.added))
const pending = computed(() => status.value?.membership_state === 'pending')
watch(
  () => [shared.value, props.avid],
  ([enabled, avid], previous, cleanup) => {
    if (!enabled || !avid) return
    const release = memberships.retain(avid)
    cleanup(release)
    memberships.schedule([avid])
  },
  { immediate: true }
)
watch(
  () => memberships.revision,
  () => {
    if (shared.value) memberships.schedule([props.avid])
  }
)
function view() {
  if (shared.value && pending.value) router.push('/downloads')
  else emit('view')
}
</script>
<template>
  <RemoteResourceActions
    :adding="shared ? adding && !owned : adding"
    :added="owned"
    :checking="shared && !status && !error"
    :status-error="error"
    :pending="pending"
    :unavailable="owned && status?.is_available === false"
    @add="emit('add')"
    @open="emit('open')"
    @view="view"
    @retry="memberships.schedule([avid], { force: true })"
  />
</template>
