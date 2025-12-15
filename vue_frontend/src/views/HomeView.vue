<script setup>
import { onMounted, computed } from 'vue'
import { useResourceStore } from '../stores/resource'
import { RouterLink } from 'vue-router'
import LoadingSpinner from '../components/LoadingSpinner.vue'

const resourceStore = useResourceStore()

onMounted(async () => {
  await resourceStore.fetchResources()
  await resourceStore.fetchDownloads()
})

const recentResources = computed(() => {
  return resourceStore.resources.slice(0, 6)
})
</script>

<template>
  <div class="home-view">
    <section class="hero">
      <div class="hero-content">
        <h1 class="hero-title">
          <span class="title-accent">NASSAV</span>
          <span class="title-sub">视频资源管理系统</span>
        </h1>
        <p class="hero-description">
          高效管理您的视频资源，支持多下载源、自动刮削元数据
        </p>
        <div class="hero-actions">
          <RouterLink to="/add" class="btn btn-primary btn-large">
            <span class="btn-icon">⊕</span>
            添加资源
          </RouterLink>
          <RouterLink to="/resources" class="btn btn-secondary btn-large">
            <span class="btn-icon">▣</span>
            浏览资源库
          </RouterLink>
        </div>
      </div>

      <div class="hero-visual">
        <div class="visual-shape shape-1"></div>
        <div class="visual-shape shape-2"></div>
        <div class="visual-shape shape-3"></div>
      </div>
    </section>

    <section class="stats-section">
      <div class="stat-card">
        <div class="stat-icon">▣</div>
        <div class="stat-content">
          <div class="stat-value">{{ resourceStore.stats.total }}</div>
          <div class="stat-label">总资源数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon success">✓</div>
        <div class="stat-content">
          <div class="stat-value">{{ resourceStore.stats.downloaded }}</div>
          <div class="stat-label">已下载</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon warning">◷</div>
        <div class="stat-content">
          <div class="stat-value">{{ resourceStore.stats.pending }}</div>
          <div class="stat-label">待下载</div>
        </div>
      </div>
    </section>

    <section class="recent-section" v-if="!resourceStore.loading && recentResources.length > 0">
      <div class="section-header">
        <h2 class="section-title">最近添加</h2>
        <RouterLink to="/resources" class="section-link">
          查看全部 →
        </RouterLink>
      </div>

      <div class="recent-grid">
        <RouterLink
          v-for="resource in recentResources"
          :key="resource.avid"
          :to="`/resource/${resource.avid}`"
          class="recent-item"
        >
          <img
            :src="`/nassav/api/resource/cover?avid=${resource.avid}`"
            :alt="resource.title"
            class="recent-cover"
          />
          <div class="recent-info">
            <span class="recent-avid">{{ resource.avid }}</span>
            <span class="recent-title">{{ resource.title }}</span>
          </div>
          <div class="recent-status" :class="{ downloaded: resource.has_video }">
            {{ resource.has_video ? '✓' : '◷' }}
          </div>
        </RouterLink>
      </div>
    </section>

    <LoadingSpinner v-if="resourceStore.loading" text="加载中..." />
  </div>
</template>

<style scoped>
.home-view {
  animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.hero {
  position: relative;
  padding: 4rem 0;
  margin-bottom: 3rem;
  overflow: hidden;
}

.hero-content {
  position: relative;
  z-index: 1;
}

.hero-title {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.title-accent {
  font-size: 4rem;
  font-weight: 700;
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: 2px;
}

.title-sub {
  font-size: 1.5rem;
  font-weight: 400;
  color: var(--text-secondary);
}

.hero-description {
  font-size: 1.1rem;
  color: var(--text-muted);
  max-width: 500px;
  line-height: 1.7;
  margin-bottom: 2rem;
}

.hero-actions {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
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

.btn-large {
  padding: 1rem 2rem;
  font-size: 1rem;
}

.btn-primary {
  background: linear-gradient(135deg, var(--accent-primary), #ff5252);
  color: white;
  box-shadow: 0 4px 15px rgba(255, 107, 107, 0.3);
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(255, 107, 107, 0.4);
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.2);
}

.btn-icon {
  font-size: 1.1rem;
}

.hero-visual {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 400px;
  height: 400px;
  pointer-events: none;
}

.visual-shape {
  position: absolute;
  border-radius: 50%;
  opacity: 0.5;
  filter: blur(60px);
}

.shape-1 {
  width: 300px;
  height: 300px;
  background: var(--accent-primary);
  top: 0;
  right: 0;
  animation: float1 8s ease-in-out infinite;
}

.shape-2 {
  width: 200px;
  height: 200px;
  background: var(--accent-secondary);
  bottom: 20%;
  right: 20%;
  animation: float2 6s ease-in-out infinite;
}

.shape-3 {
  width: 150px;
  height: 150px;
  background: var(--accent-tertiary);
  top: 30%;
  right: 30%;
  animation: float3 7s ease-in-out infinite;
}

@keyframes float1 {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(-20px, 20px); }
}

@keyframes float2 {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(15px, -15px); }
}

@keyframes float3 {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(-10px, -20px); }
}

.stats-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 3rem;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem;
  background: var(--card-bg);
  border-radius: 16px;
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.15);
}

.stat-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 107, 107, 0.1);
  border-radius: 12px;
  font-size: 1.25rem;
  color: var(--accent-primary);
}

.stat-icon.success {
  background: rgba(46, 213, 115, 0.1);
  color: #2ed573;
}

.stat-icon.warning {
  background: rgba(255, 193, 7, 0.1);
  color: #ffc107;
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

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
}

.section-title {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
}

.section-link {
  font-size: 0.9rem;
  color: var(--accent-primary);
  text-decoration: none;
  transition: opacity 0.2s;
}

.section-link:hover {
  opacity: 0.8;
}

.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: var(--card-bg);
  border-radius: 12px;
  border: 1px solid var(--border-color);
  text-decoration: none;
  transition: all 0.2s ease;
}

.recent-item:hover {
  border-color: rgba(255, 107, 107, 0.3);
  transform: translateX(4px);
}

.recent-cover {
  width: 80px;
  height: 45px;
  object-fit: cover;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.3);
}

.recent-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.recent-avid {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  color: var(--accent-primary);
  font-weight: 600;
}

.recent-title {
  font-size: 0.85rem;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recent-status {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(255, 193, 7, 0.15);
  color: #ffc107;
  font-size: 0.8rem;
}

.recent-status.downloaded {
  background: rgba(46, 213, 115, 0.15);
  color: #2ed573;
}

@media (max-width: 768px) {
  .hero {
    padding: 2rem 0;
  }

  .title-accent {
    font-size: 2.5rem;
  }

  .title-sub {
    font-size: 1.1rem;
  }

  .hero-visual {
    display: none;
  }
}
</style>
