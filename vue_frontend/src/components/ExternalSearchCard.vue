<script setup>
import { computed, ref, watch } from 'vue'
import { recommendationApi } from '../api'

const props = defineProps({
  item: {
    type: Object,
    required: true,
  },
  adding: {
    type: Boolean,
    default: false,
  },
  added: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['add', 'open', 'view'])

const displayTitle = computed(() => props.item?.title || props.item?.avid || '')
const imageFailed = ref(false)
const proxiedCoverUrl = computed(() =>
  props.item?.cover_url
    ? recommendationApi.getCoverUrl(props.item.cover_url, props.item.source || 'jable')
    : ''
)
watch(proxiedCoverUrl, () => {
  imageFailed.value = false
})

function formatCompactMetric(value) {
  const parsed = Number(value || 0)
  if (!Number.isFinite(parsed) || parsed <= 0) return null
  if (parsed >= 1000000) return `${Math.floor(parsed / 1000000)}M+`
  if (parsed >= 1000) return `${Math.floor(parsed / 1000)}K+`
  return `${parsed}`
}

const metrics = computed(() => {
  const raw = props.item?.raw_metrics || {}
  return {
    duration: raw.duration || '',
    views: formatCompactMetric(raw.views),
    likes: formatCompactMetric(raw.likes),
  }
})
</script>

<template>
  <article class="external-search-card">
    <div class="cover-shell">
      <img
        v-if="item.cover_url && !imageFailed"
        :src="proxiedCoverUrl"
        :alt="displayTitle"
        class="cover-image"
        loading="lazy"
        @error="imageFailed = true"
      />
      <div v-else class="cover-fallback">
        <span>{{ item.avid }}</span>
      </div>
    </div>

    <div class="card-body">
      <div class="card-meta">
        <span class="avid-chip">{{ item.avid }}</span>
        <span v-if="item.source" class="source-chip">{{ item.source }}</span>
      </div>

      <h3 class="card-title">
        {{ displayTitle }}
      </h3>

      <div v-if="item.raw_metrics" class="metrics-row">
        <span v-if="metrics.duration">时长 {{ metrics.duration }}</span>
        <span v-if="metrics.views">浏览 {{ metrics.views }}</span>
        <span v-if="metrics.likes">收藏 {{ metrics.likes }}</span>
      </div>

      <div class="card-actions">
        <button
          v-if="!added"
          type="button"
          class="action-btn primary"
          :disabled="adding"
          @click="emit('add')"
        >
          {{ adding ? '添加中...' : '加入资源库' }}
        </button>
        <button v-else type="button" class="action-btn success" disabled>已添加</button>

        <button
          type="button"
          class="action-btn secondary"
          @click="added ? emit('view') : emit('open')"
        >
          {{ added ? '查看详情' : '跳转来源' }}
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.external-search-card {
  background: linear-gradient(180deg, var(--bg-surface-subtle-8), var(--bg-surface-subtle-5));
  border: 1px solid;
  border-color: var(--border-color);
  border-radius: 1.25rem;
  overflow: hidden;
  backdrop-filter: blur(16px);
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
  min-height: 100%;
  transition:
    transform 0.25s ease,
    border-color 0.25s ease,
    box-shadow 0.25s ease;
}

.external-search-card:hover {
  transform: translateY(-4px);
  border-color: var(--accent-primary);
  box-shadow: var(--shadow-2xl);
}

.cover-shell {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background:
    radial-gradient(
      circle at top left,
      color-mix(in srgb, var(--accent-primary) 28%, transparent),
      transparent 55%
    ),
    linear-gradient(145deg, var(--bg-secondary), var(--bg-primary));
}

.cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  filter: brightness(1.05);
}

.cover-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-primary);
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 1rem;
  text-align: center;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  padding: 1rem 1rem 1.1rem;
  flex: 1;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.avid-chip,
.source-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0.28rem 0.65rem;
  font-size: 0.72rem;
  font-weight: 600;
}

.avid-chip {
  background: color-mix(in srgb, var(--accent-primary) 12%, transparent);
  color: var(--accent-primary-text);
}

.source-chip {
  background: color-mix(in srgb, var(--accent-tertiary) 12%, transparent);
  color: var(--accent-tertiary-text);
}

.card-title {
  color: var(--text-primary);
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.45;
  margin: 0;
  min-height: calc(1rem * 1.45 * 3);
  max-height: calc(1rem * 1.45 * 3);
  display: -webkit-box;
  line-clamp: 3;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.metrics-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  color: var(--text-secondary);
  font-size: 0.82rem;
  min-height: 1.2rem;
}

.card-actions {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.65rem;
  margin-top: auto;
}

.action-btn {
  border: none;
  border-radius: 0.9rem;
  padding: 0.8rem 0.95rem;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    opacity 0.2s ease,
    box-shadow 0.2s ease;
}

.action-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.action-btn.primary {
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
  color: var(--on-accent);
  box-shadow: var(--shadow-accent-lg);
}

.action-btn.secondary {
  background: var(--bg-surface-subtle-5);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.action-btn.success {
  background: linear-gradient(135deg, var(--accent-success), var(--accent-tertiary));
  color: var(--on-accent);
}
</style>
