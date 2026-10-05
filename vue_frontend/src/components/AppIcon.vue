<script setup>
import { computed } from 'vue'
const props = defineProps({ name: { type: String, default: 'empty' } })
const paths = {
  settings: [
    'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8',
    'm9 3-1 3-3 1-2 5 2 5 3 1 1 3h6l1-3 3-1 2-5-2-5-3-1-1-3z',
  ],
  cookie: [
    'M21 12a9 9 0 1 1-9-9 4 4 0 0 0 4 4 4 4 0 0 0 5 5Z',
    'M8 8h.01M7 14h.01M12 12h.01M14 17h.01',
  ],
  download: ['M12 3v12m-5-5 5 5 5-5', 'M4 16v5h16v-5'],
  bolt: ['m13 2-9 12h7l-1 8 10-13h-7z'],
  target: ['M21 12a9 9 0 1 1-9-9', 'M17 12a5 5 0 1 1-5-5', 'm12 12 9-9m-5 0h5v5'],
  palette: [
    'M12 3a9 9 0 1 0 0 18h2a2 2 0 0 0 0-4h-1a2 2 0 0 1 0-4h3a5 5 0 0 0 5-5c0-3-4-5-9-5Z',
    'M7 8h.01M10 6h.01M6 12h.01',
  ],
  close: ['m6 6 12 12M18 6 6 18'],
  check: ['m5 12 4 4L19 6'],
  star: ['m12 3 3 6 6 1-4 5 1 6-6-3-6 3 1-6-4-5 6-1z'],
  warning: ['m12 3 10 18H2z', 'M12 9v5m0 3h.01'],
  empty: ['m12 3 9 9-9 9-9-9z'],
}
const iconPaths = computed(() => paths[props.name] || paths.empty)
</script>
<template>
  <svg
    class="w-5 h-5 shrink-0"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path v-for="(path, index) in iconPaths" :key="index" :d="path" />
  </svg>
</template>
