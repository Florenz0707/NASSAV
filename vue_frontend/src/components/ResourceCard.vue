<script setup>
import { computed } from 'vue'
import { resourceApi } from '../api'

const props = defineProps({
  resource: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['download', 'refresh'])

const coverUrl = computed(() => resourceApi.getCoverUrl(props.resource.avid))

const statusClass = computed(() => ({
  downloaded: props.resource.has_video,
  pending: !props.resource.has_video
}))
</script>

<template>
  <div class="resource-card" :class="statusClass">
    <div class="card-cover">
      <img :src="coverUrl" :alt="resource.title" loading="lazy" />
      <div class="cover-overlay">
        <RouterLink :to="`/resource/${resource.avid}`" class="btn-view">
          查看详情
        </RouterLink>
      </div>
      <div class="status-badge" :class="{ downloaded: resource.has_video }">
        {{ resource.has_video ? '已下载' : '未下载' }}
      </div>
    </div>

    <div class="card-content">
      <div class="card-avid">{{ resource.avid }}</div>
      <h3 class="card-title" :title="resource.title">{{ resource.title }}</h3>

      <div class="card-meta">
        <span class="meta-item">
          <span class="meta-icon">◉</span>
          {{ resource.source }}
        </span>
        <span class="meta-item" v-if="resource.release_date">
          <span class="meta-icon">◷</span>
          {{ resource.release_date }}
        </span>
      </div>

      <div class="card-actions">
        <button
          v-if="!resource.has_video"
          class="btn btn-primary btn-small"
          @click="emit('download', resource.avid)"
        >
          <span class="btn-icon">⬇</span>
          下载
        </button>
        <button
          class="btn btn-secondary btn-small"
          @click="emit('refresh', resource.avid)"
        >
          <span class="btn-icon">↻</span>
          刷新
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.resource-card {
  background: var(--card-bg);
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
}

.resource-card:hover {
  transform: translateY(-4px);
  border-color: rgba(255, 107, 107, 0.3);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
}

.card-cover {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.3);
}

.card-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.5s ease;
}

.resource-card:hover .card-cover img {
  transform: scale(1.05);
}

.cover-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.resource-card:hover .cover-overlay {
  opacity: 1;
}

.btn-view {
  padding: 0.75rem 1.5rem;
  background: var(--accent-primary);
  color: white;
  border-radius: 8px;
  text-decoration: none;
  font-weight: 500;
  font-size: 0.9rem;
  transition: transform 0.2s ease;
}

.btn-view:hover {
  transform: scale(1.05);
}

.status-badge {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 0.35rem 0.75rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  background: rgba(255, 193, 7, 0.9);
  color: #1a1a2e;
}

.status-badge.downloaded {
  background: rgba(46, 213, 115, 0.9);
  color: #1a1a2e;
}

.card-content {
  padding: 1.25rem;
}

.card-avid {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: var(--accent-primary);
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.card-title {
  font-size: 1rem;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.4;
  margin-bottom: 0.75rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.meta-icon {
  font-size: 0.7rem;
  opacity: 0.7;
}

.card-actions {
  display: flex;
  gap: 0.5rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.6rem 1rem;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-small {
  padding: 0.5rem 0.85rem;
  font-size: 0.8rem;
}

.btn-primary {
  background: var(--accent-primary);
  color: white;
}

.btn-primary:hover {
  background: #ff5252;
  transform: translateY(-1px);
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.12);
  color: var(--text-primary);
}

.btn-icon {
  font-size: 0.9rem;
}
</style>
