<script setup>
// Notification cards shared by the global sidebar and isolated preview.
import AppButton from './AppButton.vue'
import AppIcon from './AppIcon.vue'
defineProps({ events: { type: Array, required: true }, selectedId: { type: String, default: '' } })
defineEmits(['select', 'read'])
</script>
<template>
  <ol class="border-l border-[var(--border-color)] pl-4 space-y-4">
    <li
      v-for="event in events"
      :key="event.id"
      class="bg-secondary border rounded-xl p-4 border-[var(--border-color)]"
      :class="selectedId === event.id ? 'border-accent-primary' : ''"
    >
      <div class="flex items-center justify-between gap-3 text-xs mb-2">
        <time class="text-muted">{{ event.day }} {{ event.time }}</time>
        <span v-if="event.unread" class="text-accent-primary">未读</span>
      </div>
      <button
        class="flex items-start gap-2 text-left text-primary w-full"
        :aria-label="'查看通知：' + event.title"
        @click="$emit('select', event)"
      >
        <AppIcon
          :name="event.severity === 'danger' ? 'warning' : 'check'"
          :class="event.severity === 'danger' ? 'text-accent-danger' : 'text-accent-success'"
        />
        <span class="font-semibold break-words">{{ event.title }}</span>
      </button>
      <p class="text-secondary text-sm mt-2">{{ event.message }}</p>
      <p v-if="event.avid" class="text-muted text-xs mt-2">{{ event.avid }}</p>
      <details v-if="event.failures" class="text-sm mt-3">
        <summary class="text-accent-danger cursor-pointer">
          查看 {{ event.failures.length }} 项失败
        </summary>
        <ul class="text-secondary mt-2 space-y-1">
          <li v-for="failure in event.failures" :key="failure">{{ failure }}</li>
        </ul>
      </details>
      <div class="flex flex-wrap gap-2 mt-3">
        <AppButton size="sm" variant="neutral" @click="$emit('select', event)">{{
          event.targetLabel
        }}</AppButton>
        <AppButton
          v-if="event.unread"
          size="sm"
          variant="neutral"
          :aria-label="event.title + '，标为已读'"
          @click="$emit('read', event)"
          >标为已读</AppButton
        >
      </div>
    </li>
  </ol>
</template>
