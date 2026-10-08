<script setup>
defineProps({ groups: { type: Object, required: true } })
</script>
<template>
  <section aria-label="推荐依据">
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <section
        v-for="group in [
          { key: 'actor', label: '高频演员' },
          { key: 'genre', label: '高频类别' },
        ]"
        :key="group.key"
        class="min-w-0"
      >
        <h4 class="text-secondary text-sm font-medium mb-2">{{ group.label }}</h4>
        <ul v-if="groups[group.key]?.length" class="flex flex-wrap gap-2">
          <li
            v-for="seed in groups[group.key]"
            :key="`${seed.seed_type}-${seed.value}`"
            class="text-on-accent text-sm rounded-lg px-3 py-2 max-w-full break-words"
            :class="
              group.key === 'actor' ? 'bg-[var(--coral-fill)]/80' : 'bg-[var(--teal-fill)]/80'
            "
          >
            {{ seed.value }}
            <span class="text-on-accent opacity-80">· {{ seed.resource_count }}</span>
          </li>
        </ul>
        <p v-else class="text-muted text-sm">暂无{{ group.label }}数据</p>
      </section>
    </div>
  </section>
</template>
