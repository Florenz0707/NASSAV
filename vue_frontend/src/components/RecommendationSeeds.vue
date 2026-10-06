<script setup>
defineProps({ groups: { type: Object, required: true } })
</script>
<template>
  <section class="seed-panel">
    <div class="seed-section">
      <h2 class="seed-title">高频演员</h2>
      <div class="seed-list">
        <span
          v-for="seed in groups.actor"
          :key="`${seed.seed_type}-${seed.value}`"
          class="seed-pill"
        >
          {{ seed.value }} · {{ seed.resource_count }}
        </span>
      </div>
    </div>

    <div class="seed-section">
      <h2 class="seed-title">高频类别</h2>
      <div class="seed-list">
        <span
          v-for="seed in groups.genre"
          :key="`${seed.seed_type}-${seed.value}`"
          class="seed-pill secondary"
        >
          {{ seed.value }} · {{ seed.resource_count }}
        </span>
      </div>
    </div>
  </section>
</template>
