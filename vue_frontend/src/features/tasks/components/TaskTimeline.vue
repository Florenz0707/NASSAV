<script setup>
import { taskTime } from '../lib/taskDetails.js'
defineProps({ events: { type: Array, required: true } })
</script>
<template>
  <section class="mt-5" aria-label="活动时间线">
    <h3 class="text-primary font-semibold text-sm mb-3">活动时间线</h3>
    <ol class="border-l border-[var(--border-color)] pl-3 space-y-3">
      <li
        v-for="(event, index) in events"
        :key="index"
        class="flex items-baseline justify-between gap-3 text-sm"
        :class="event.state === 'failed' ? 'text-accent-danger' : 'text-secondary'"
      >
        <span class="min-w-0">{{ event.label }}</span>
        <time class="text-muted text-xs text-right tabular-nums shrink-0">{{
          taskTime(event.at) || '时间未记录'
        }}</time>
      </li>
    </ol>
  </section>
</template>
