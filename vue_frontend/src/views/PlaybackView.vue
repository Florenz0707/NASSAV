<script setup>
import PlaybackPage from '../features/playback/components/PlaybackPage.vue'
defineProps({ avid: { type: String, required: true }, mode: { type: String, default: 'auto' } })
</script>
<template>
  <PlaybackPage :avid="avid" :mode="mode" />
</template>
