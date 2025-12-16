<script setup>
import {ref, onMounted, computed} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {resourceApi} from '../api'
import {useResourceStore} from '../stores/resource'
import {useToastStore} from '../stores/toast'
import LoadingSpinner from '../components/LoadingSpinner.vue'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
const toastStore = useToastStore()

const avid = computed(() => route.params.avid)
const metadata = ref(null)
const loading = ref(true)
const error = ref(null)
const downloading = ref(false)
const refreshing = ref(false)

const coverUrl = computed(() => resourceApi.getCoverUrl(avid.value))

const fileSize = computed(() => {
  if (!metadata.value?.file_size) return null
  const bytes = metadata.value.file_size
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
})

onMounted(async () => {
  await fetchMetadata()
})

async function fetchMetadata() {
  loading.value = true
  error.value = null
  try {
    const response = await resourceApi.getMetadata(avid.value)
    metadata.value = response.data
  } catch (err) {
    error.value = err.message || '获取元数据失败'
  } finally {
    loading.value = false
  }
}

async function handleDownload() {
  downloading.value = true
  try {
    await resourceStore.submitDownload(avid.value)
    toastStore.success('下载任务已提交')
  } catch (err) {
    if (err.code === 409) {
      toastStore.info('视频已下载')
    } else {
      toastStore.error(err.message || '提交下载失败')
    }
  } finally {
    downloading.value = false
  }
}

async function handleRefresh() {
  refreshing.value = true
  try {
    await resourceStore.refreshResource(avid.value)
    await fetchMetadata()
    toastStore.success('刷新成功')
  } catch (err) {
    toastStore.error(err.message || '刷新失败')
  } finally {
    refreshing.value = false
  }
}

function goBack() {
  router.back()
}
</script>

<template>
  <div class="detail-view">
    <button class="back-btn" @click="goBack">
      <span class="back-icon">←</span>
      返回
    </button>

    <LoadingSpinner v-if="loading" size="large" text="加载详情中..."/>

    <div v-else-if="error" class="error-state">
      <div class="error-icon">✕</div>
      <h2>加载失败</h2>
      <p>{{ error }}</p>
      <button class="btn btn-primary" @click="fetchMetadata">重试</button>
    </div>

    <template v-else-if="metadata">
      <div class="detail-header">
        <div class="cover-wrapper">
          <img :src="coverUrl" :alt="metadata.title" class="cover-image"/>
          <div class="cover-status" :class="{ downloaded: metadata.file_exists }">
            {{ metadata.file_exists ? '已下载' : '未下载' }}
          </div>
        </div>

        <div class="header-info">
          <div class="avid-badge">{{ metadata.avid }}</div>
          <h1 class="title">{{ metadata.title }}</h1>

          <div class="meta-grid">
            <div class="meta-item" v-if="metadata.release_date">
              <span class="meta-label">发行日期</span>
              <span class="meta-value">{{ metadata.release_date }}</span>
            </div>
            <div class="meta-item" v-if="metadata.duration">
              <span class="meta-label">时长</span>
              <span class="meta-value">{{ metadata.duration }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">来源</span>
              <span class="meta-value source">{{ metadata.source }}</span>
            </div>
            <div class="meta-item" v-if="fileSize">
              <span class="meta-label">文件大小</span>
              <span class="meta-value">{{ fileSize }}</span>
            </div>
          </div>

          <div class="action-buttons">
            <button
                v-if="!metadata.file_exists"
                class="btn btn-primary"
                :disabled="downloading"
                @click="handleDownload"
            >
              <span class="btn-icon">{{ downloading ? '◷' : '⬇' }}</span>
              {{ downloading ? '提交中...' : '下载视频' }}
            </button>
            <button
                class="btn btn-secondary"
                :disabled="refreshing"
                @click="handleRefresh"
            >
              <span class="btn-icon">{{ refreshing ? '◷' : '↻' }}</span>
              {{ refreshing ? '刷新中...' : '刷新信息' }}
            </button>
          </div>
        </div>
      </div>

      <div class="detail-sections">
        <section class="detail-section" v-if="metadata.director || metadata.studio || metadata.label">
          <h2 class="section-title">制作信息</h2>
          <div class="info-list">
            <div class="info-item" v-if="metadata.director">
              <span class="info-label">导演</span>
              <span class="info-value">{{ metadata.director }}</span>
            </div>
            <div class="info-item" v-if="metadata.studio">
              <span class="info-label">制作商</span>
              <span class="info-value">{{ metadata.studio }}</span>
            </div>
            <div class="info-item" v-if="metadata.label">
              <span class="info-label">发行商</span>
              <span class="info-value">{{ metadata.label }}</span>
            </div>
            <div class="info-item" v-if="metadata.series">
              <span class="info-label">系列</span>
              <span class="info-value">{{ metadata.series }}</span>
            </div>
          </div>
        </section>

        <section class="detail-section" v-if="metadata.actors?.length">
          <h2 class="section-title">演员</h2>
          <div class="tags">
            <span class="tag actor" v-for="actor in metadata.actors" :key="actor">
              {{ actor }}
            </span>
          </div>
        </section>

        <section class="detail-section" v-if="metadata.genres?.length">
          <h2 class="section-title">类别</h2>
          <div class="tags">
            <span class="tag genre" v-for="genre in metadata.genres" :key="genre">
              {{ genre }}
            </span>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.detail-view {
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

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1rem;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 2rem;
}

.back-btn:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
}

.back-icon {
  font-size: 1.1rem;
}

.error-state {
  text-align: center;
  padding: 4rem 2rem;
}

.error-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 1.5rem;
  background: rgba(255, 107, 107, 0.1);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  color: var(--accent-primary);
}

.error-state h2 {
  font-size: 1.25rem;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.error-state p {
  color: var(--text-muted);
  margin-bottom: 1.5rem;
}

.detail-header {
  display: grid;
  grid-template-columns: 400px 1fr;
  gap: 2.5rem;
  margin-bottom: 3rem;
}

.cover-wrapper {
  position: relative;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}

.cover-image {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  display: block;
}

.cover-status {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 0.4rem 0.85rem;
  background: rgba(255, 193, 7, 0.9);
  color: #1a1a2e;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}

.cover-status.downloaded {
  background: rgba(46, 213, 115, 0.9);
}

.header-info {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.avid-badge {
  display: inline-block;
  padding: 0.4rem 0.85rem;
  background: rgba(255, 107, 107, 0.15);
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--accent-primary);
  margin-bottom: 1rem;
  width: fit-content;
}

.title {
  font-size: 1.75rem;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
  margin-bottom: 1.5rem;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-bottom: 2rem;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.meta-label {
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.meta-value {
  font-size: 1rem;
  color: var(--text-primary);
}

.meta-value.source {
  color: var(--accent-secondary);
  font-weight: 500;
}

.action-buttons {
  display: flex;
  gap: 1rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.875rem 1.5rem;
  border: none;
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: linear-gradient(135deg, var(--accent-primary), #ff5252);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 15px rgba(255, 107, 107, 0.3);
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.12);
}

.btn-icon {
  font-size: 1.1rem;
}

.detail-sections {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.detail-section {
  background: var(--card-bg);
  border-radius: 16px;
  border: 1px solid var(--border-color);
  padding: 1.5rem;
}

.section-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 1.25rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-color);
}

.info-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1.25rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.info-label {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.info-value {
  font-size: 0.95rem;
  color: var(--text-primary);
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tag {
  padding: 0.4rem 0.85rem;
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 500;
}

.tag.actor {
  background: rgba(78, 205, 196, 0.15);
  color: var(--accent-tertiary);
}

.tag.genre {
  background: rgba(255, 159, 67, 0.15);
  color: var(--accent-secondary);
}

@media (max-width: 900px) {
  .detail-header {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }

  .cover-wrapper {
    max-width: 500px;
  }

  .meta-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 500px) {
  .action-buttons {
    flex-direction: column;
  }

  .btn {
    justify-content: center;
  }
}
</style>
