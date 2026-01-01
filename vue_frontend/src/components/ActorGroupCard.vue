<template>
  <div class="actor-card" @click="$emit('click')">
    <div class="avatar">
      <div class="avatar-circle" :style="{ backgroundColor: bgColor }">{{ initial }}</div>
    </div>
    <div class="actor-name">{{ actor.name }}</div>
    <div class="actor-count">共有 {{ actor.resource_count }} 部作品</div>
  </div>
</template>

<script>
export default {
  name: 'ActorGroupCard',
  props: {
    actor: { type: Object, required: true },
    thumbs: { type: Array, default: () => [] }
  },
  computed: {
    initial() {
      const n = this.actor && this.actor.name ? this.actor.name.trim() : ''
      return n ? n.charAt(0) : '?'
    },
    bgColor() {
      // use a unified dark background for all avatars
      return '#1f2937'
    }
  }
}
</script>

<style scoped>
.actor-card{display:flex;flex-direction:column;align-items:center;justify-content:flex-start;padding:12px;border-radius:8px;cursor:pointer;background:transparent}
.avatar{margin-bottom:10px}
.avatar-circle{width:72px;height:72px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-weight:700;font-size:28px}
.actor-name{font-weight:600;margin-bottom:6px;text-align:center}
.actor-count{color:#9ca3af;font-size:13px;text-align:center}
</style>
