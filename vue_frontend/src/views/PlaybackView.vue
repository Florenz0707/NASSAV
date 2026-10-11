<script setup>
import PlaybackPage from '../features/playback/components/PlaybackPage.vue'
defineProps({ avid: { type: String, required: true } })
</script>
<template>
  <PlaybackPage :avid="avid" />
</template>
