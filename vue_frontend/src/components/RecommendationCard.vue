<script setup>
import { computed } from 'vue'
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
  layoutStyle: {
    type: String,
    default: 'grid',
  },
  reasonsOpen: {
    type: Boolean,
    default: false,
  },
  feedback: {
    type: String,
    default: '',
  },
  feedbackSubmitting: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['add', 'open', 'view', 'reasons', 'feedback'])

const isDisliked = computed(() => props.feedback === 'dislike')
const hasReasons = computed(
  () => Array.isArray(props.item?.reasons) && props.item.reasons.length > 0
)
const displayTitle = computed(() => props.item?.title || props.item?.avid || '')
const reasonsCount = computed(() => (hasReasons.value ? props.item.reasons.length : 0))
const formattedScore = computed(() => Number(props.item?.score || 0).toFixed(1))
const proxiedCoverUrl = computed(() =>
  props.item?.cover_url ? recommendationApi.getCoverUrl(props.item.cover_url) : ''
)

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

function handleReasonsClick(event) {
  if (!hasReasons.value) return
  emit('reasons', event)
}
</script>

<template>
  <article
    class="recommendation-card"
    :class="{
      masonry: layoutStyle === 'masonry',
      disliked: isDisliked,
    }"
  >
    <div class="cover-shell">
      <img
        v-if="item.cover_url"
        :src="proxiedCoverUrl"
        :alt="displayTitle"
        class="cover-image"
        :class="{ disliked: isDisliked }"
        loading="lazy"
      />
      <div v-else class="cover-fallback">
        <span>{{ item.avid }}</span>
      </div>
      <div class="feedback-overlay">
        <span v-if="isDisliked" class="feedback-overlay-badge">已屏蔽</span>
        <button
          v-else
          type="button"
          class="feedback-overlay-button"
          :disabled="feedbackSubmitting"
          aria-label="不感兴趣"
          @click="emit('feedback', 'dislike')"
        >
          ⨉
        </button>
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

      <div v-if="item.score !== undefined || item.reasons?.length" class="reasons-wrap">
        <button
          type="button"
          class="reason-toggle"
          :data-reason-anchor="item.avid"
          :disabled="!hasReasons"
          :class="{ active: reasonsOpen }"
          @click="handleReasonsClick"
        >
          {{ `推荐分：${formattedScore}（${reasonsCount}）` }}
        </button>
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
.recommendation-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02));
  border: 1px solid;
  border-color: rgba(255, 255, 255, 0.16);
  border-radius: 1.25rem;
  overflow: hidden;
  backdrop-filter: blur(16px);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.22);
  display: flex;
  flex-direction: column;
  min-height: 100%;
  transition:
    transform 0.25s ease,
    border-color 0.25s ease,
    box-shadow 0.25s ease;
}

.recommendation-card:hover {
  transform: translateY(-4px);
  border-color: rgba(255, 107, 107, 0.24);
  box-shadow: 0 22px 48px rgba(0, 0, 0, 0.28);
}

.recommendation-card.disliked {
  background: linear-gradient(180deg, rgba(255, 107, 107, 0.03), rgba(255, 255, 255, 0.01));
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.22);
}

.cover-shell {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(255, 107, 107, 0.28), transparent 55%),
    linear-gradient(145deg, rgba(18, 18, 24, 0.92), rgba(28, 28, 38, 0.86));
}

.feedback-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: 0.4rem;
  background: linear-gradient(180deg, rgba(20, 24, 34, 0.12), rgba(20, 24, 34, 0.42));
  pointer-events: none;
}

.feedback-overlay-badge {
  display: inline-flex;
  align-items: center;
  min-height: 1.95rem;
  padding: 0.28rem 0.72rem;
  border-radius: 999px;
  background: rgba(255, 107, 107, 0.5);
  color: white;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  box-shadow: 0 10px 24px rgba(255, 107, 107, 0.28);
  pointer-events: auto;
}

.feedback-overlay-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.7rem;
  min-height: 1.7rem;
  padding: 0.28rem 0.72rem;
  border: 0;
  border-radius: 999px;
  background: rgba(255, 107, 107, 0.3);
  color: white;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  box-shadow: 0 10px 24px rgba(255, 107, 107, 0.28);
  pointer-events: auto;
  cursor: pointer;
}

.feedback-overlay-button:disabled {
  cursor: progress;
  opacity: 0.75;
}

.cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  filter: brightness(1.05);
}

.cover-image.disliked {
  filter: brightness(0.5) grayscale(0.4);
}

.cover-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.86);
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
  background: rgba(255, 107, 107, 0.12);
  color: var(--accent-primary);
}

.source-chip {
  background: rgba(78, 205, 196, 0.12);
  color: var(--accent-tertiary);
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
  color: var(--text-muted);
  font-size: 0.82rem;
  min-height: 1.2rem;
}

.reasons-wrap {
  display: flex;
  flex-direction: row;
}

.reason-toggle {
  align-self: flex-start;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 999px;
  padding: 0.38rem 0.72rem;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-secondary);
  font-size: 0.76rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    color 0.2s ease,
    background 0.2s ease;
}

.reason-toggle:disabled {
  cursor: default;
  opacity: 0.8;
}

.reason-toggle.active {
  border-color: rgba(255, 107, 107, 0.28);
  background: rgba(255, 107, 107, 0.08);
  color: var(--text-primary);
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
  background: linear-gradient(135deg, var(--accent-primary), #ff8b5f);
  color: white;
  box-shadow: 0 10px 20px rgba(255, 107, 107, 0.22);
}

.action-btn.secondary {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.action-btn.success {
  background: linear-gradient(135deg, rgba(46, 204, 113, 0.9), rgba(26, 188, 156, 0.9));
  color: white;
}

.recommendation-card.masonry .card-title {
  display: block;
  min-height: auto;
  max-height: none;
  line-clamp: unset;
  -webkit-line-clamp: unset;
  -webkit-box-orient: initial;
  overflow: visible;
}

.recommendation-card.masonry .card-body {
  gap: 0.65rem;
  padding: 0.72rem 0.72rem 0.82rem;
}

.recommendation-card.masonry .card-meta {
  gap: 0.36rem;
}

.recommendation-card.masonry .avid-chip,
.recommendation-card.masonry .source-chip {
  padding: 0.22rem 0.48rem;
  font-size: 0.64rem;
}

.recommendation-card.masonry .card-title {
  font-size: 0.88rem;
  line-height: 1.4;
}

.recommendation-card.masonry .metrics-row {
  gap: 0.48rem;
  font-size: 0.72rem;
}

.recommendation-card.masonry .reason-toggle {
  padding: 0.32rem 0.55rem;
  font-size: 0.68rem;
}

.recommendation-card.masonry .card-actions {
  grid-template-columns: 1fr;
  gap: 0.45rem;
}

.recommendation-card.masonry .action-btn {
  padding: 0.62rem 0.75rem;
  font-size: 0.78rem;
}

@media (max-width: 640px) {
  .card-actions {
    grid-template-columns: 1fr;
  }
}
</style>
