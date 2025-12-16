<script setup>
import {ref, onMounted, computed} from 'vue'
import {useResourceStore} from '../stores/resource'
import {resourceApi} from '../api'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'

const resourceStore = useResourceStore()

const loading = ref(true)
const downloadedResources = ref([])

onMounted(async () => {
  await loadDownloads()
})

async function loadDownloads() {
  loading.value = true
  try {
    await resourceStore.fetchResources()
    await resourceStore.fetchDownloads()

    // 获取已下载资源的详情
    downloadedResources.value = resourceStore.resources.filter(r => r.has_video)
  } finally {
    loading.value = false
  }
}

const totalSize = computed(() => {
  // 假设每个视频平均大小
  const count = downloadedResources.value.length
  return count > 0 ? `${count} 个视频` : '无'
})
</script>

<template>
  <div class="downloads-view">
    <div class="page-header">
      <h1 class="page-title">下载管理</h1>
      <p class="page-subtitle">查看和管理已下载的视频</p>
    </div>

    <div class="stats-bar">
      <div class="stat">
        <span class="stat-value">{{ downloadedResources.length }}</span>
        <span class="stat-label">已下载</span>
      </div>
      <div class="stat">
        <span class="stat-value">{{ resourceStore.stats.pending }}</span>
        <span class="stat-label">待下载</span>
      </div>
    </div>

    <LoadingSpinner v-if="loading" size="large" text="加载下载列表..."/>

    <EmptyState
        v-else-if="downloadedResources.length === 0"
        icon="⬇"
        title="暂无下载"
        description="您还没有下载任何视频，去资源库添加并下载吧"
    >
      <template #action>
        <RouterLink to="/resources" class="btn btn-primary">
          浏览资源库
        </RouterLink>
      </template>
    </EmptyState>

    <div v-else class="downloads-list">
      <RouterLink
          v-for="resource in downloadedResources"
          :key="resource.avid"
          :to="`/resource/${resource.avid}`"
          class="download-item"
      >
        <img
            :src="resourceApi.getCoverUrl(resource.avid)"
            :alt="resource.title"
            class="download-cover"
        />
        <div class="download-info">
          <div class="download-avid">{{ resource.avid }}</div>
          <div class="download-title">{{ resource.title }}</div>
          <div class="download-meta">
            <span class="meta-tag source">{{ resource.source }}</span>
            <span class="meta-tag" v-if="resource.release_date">{{ resource.release_date }}</span>
          </div>
        </div>
        <div class="download-status">
          <span class="status-icon">✓</span>
          <span class="status-text">已下载</span>
        </div>
      </RouterLink>
    </div>
  </div>
</template>

<style scoped>
.downloads-view {
  animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.page-header {
  margin-bottom: 2rem;
}

.page-title {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.page-subtitle {
  color: var(--text-muted);
  font-size: 1rem;
}

.stats-bar {
  display: flex;
  gap: 2rem;
  padding: 1.5rem;
  background: var(--card-bg);
  border-radius: 16px;
  border: 1px solid var(--border-color);
  margin-bottom: 2rem;
}

.stat {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 0.9rem;
  color: var(--text-muted);
}

.downloads-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.download-item {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding: 1rem;
  background: var(--card-bg);
  border-radius: 16px;
  border: 1px solid var(--border-color);
  text-decoration: none;
  transition: all 0.2s ease;
}

.download-item:hover {
  border-color: rgba(46, 213, 115, 0.3);
  transform: translateX(4px);
}

.download-cover {
  width: 120px;
  height: 68px;
  object-fit: cover;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.3);
  flex-shrink: 0;
}

.download-info {
  flex: 1;
  min-width: 0;
}

.download-avid {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--accent-primary);
  margin-bottom: 0.35rem;
}

.download-title {
  font-size: 1rem;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.download-meta {
  display: flex;
  gap: 0.5rem;
}

.meta-tag {
  padding: 0.25rem 0.6rem;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.meta-tag.source {
  background: rgba(255, 159, 67, 0.15);
  color: var(--accent-secondary);
}

.download-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  background: rgba(46, 213, 115, 0.1);
  border-radius: 10px;
  flex-shrink: 0;
}

.status-icon {
  font-size: 1.25rem;
  color: #2ed573;
}

.status-text {
  font-size: 0.75rem;
  color: #2ed573;
  font-weight: 500;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary {
  background: linear-gradient(135deg, var(--accent-primary), #ff5252);
  color: white;
}

.btn-primary:hover {
  transform: translateY(-2px);
}

@media (max-width: 640px) {
  .download-item {
    flex-direction: column;
    align-items: flex-start;
  }

  .download-cover {
    width: 100%;
    height: auto;
    aspect-ratio: 16 / 9;
  }

  .download-status {
    width: 100%;
    flex-direction: row;
    justify-content: center;
  }
}
</style>
