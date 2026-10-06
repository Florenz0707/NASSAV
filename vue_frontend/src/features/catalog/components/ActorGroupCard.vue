<template>
  <RouterLink :to="to" class="actor-card">
    <div class="avatar">
      <div class="avatar-circle" :style="{ backgroundColor: bgColor }">
        <img
          v-if="settingsStore.showActorAvatar && actor.id && actor.avatar_filename"
          :src="actorApi.getAvatarUrl(actor.id)"
          :alt="actor.name"
          loading="lazy"
          class="avatar-img"
        />
        <span v-else>{{ initial }}</span>
      </div>
    </div>
    <div class="actor-name">
      {{ actor.name }}
    </div>
    <div class="actor-count">共有 {{ actor.resource_count }} 部作品</div>
  </RouterLink>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { actorApi } from '../../../api/index.js'
import { useSettingsStore } from '../../settings/stores/settings.js'

const props = defineProps({
  actor: { type: Object, required: true },
  to: { type: [String, Object], required: true },
})

const settingsStore = useSettingsStore()

const initial = computed(() => {
  const n = props.actor && props.actor.name ? props.actor.name.trim() : ''
  return n ? n.substring(0, 2) : '?'
})

const bgColor = computed(() => {
  // use a unified dark background for all avatars
  return 'var(--bg-secondary)'
})
</script>

<style scoped>
.actor-card {
  text-decoration: none;
  color: inherit;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  border: 0;
  font: inherit;
  background: transparent;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    background-color 0.18s ease;
}

.avatar {
  margin-bottom: 10px;
}

.avatar-circle {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-primary);
  font-weight: 500;
  font-size: 24px;
  overflow: hidden;
  border: 2px solid var(--border-color);
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.actor-name {
  font-weight: 600;
  margin-bottom: 6px;
  text-align: center;
}

.actor-count {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
}

.actor-card:hover {
  transform: translateY(-6px);
  box-shadow: var(--shadow-xl);
  background-color: var(--bg-white-5);
}
</style>
