<script setup>
import AppButton from '../../../shared/ui/AppButton.vue'
import RemoteLibraryActions from '../../library/components/RemoteLibraryActions.vue'
import { resolveResourceTitle } from '../../resources/lib/resourceTitle.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { computed, ref, watch } from 'vue'
import { recommendationApi } from '../../../api/index.js'
import { useSessionStore } from '../../auth/stores/session.js'

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
  blocked: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['add', 'open', 'view', 'reasons', 'feedback', 'block'])

const isLiked = computed(() => props.feedback === 'like')
const isDisliked = computed(() => props.feedback === 'dislike')
const isBlocked = computed(() => props.blocked)
const hasReasons = computed(
  () => Array.isArray(props.item?.reasons) && props.item.reasons.length > 0
)
const imageFailed = ref(false)
const settingsStore = useSettingsStore()
const displayTitle = computed(() => resolveResourceTitle(props.item, settingsStore.displayTitle))
const reasonsCount = computed(() => (hasReasons.value ? props.item.reasons.length : 0))
const formattedScore = computed(() => Number(props.item?.score || 0).toFixed(1))
const session = useSessionStore()
const proxiedCoverUrl = computed(() =>
  recommendationApi.getResultCoverUrl(props.item, session.capabilities.personal_source_credentials)
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
      blocked: isBlocked,
    }"
  >
    <div class="cover-shell">
      <img
        v-if="proxiedCoverUrl && !imageFailed"
        :src="proxiedCoverUrl"
        :alt="displayTitle"
        class="cover-image"
        :class="{ blocked: isBlocked }"
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

      <div class="reasons-wrap">
        <button
          type="button"
          v-if="item.score !== undefined || item.reasons?.length"
          class="reason-toggle"
          :data-reason-anchor="item.avid"
          :disabled="!hasReasons"
          :class="{ active: reasonsOpen }"
          @click="handleReasonsClick"
        >
          {{ `推荐分：${formattedScore}（${reasonsCount}）` }}
        </button>
        <div class="inline-feedback-actions">
          <button
            type="button"
            class="inline-feedback-btn"
            :class="{ active: isLiked }"
            :disabled="feedbackSubmitting"
            aria-label="喜欢"
            title="喜欢"
            @click="emit('feedback', 'like')"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M14 9V5a3 3 0 0 0-6 0v4H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h10.28a2 2 0 0 0 1.9-1.37l2.44-7.32A2 2 0 0 0 17.72 9H14Z"
              ></path>
            </svg>
          </button>
          <button
            type="button"
            class="inline-feedback-btn danger"
            :class="{ active: isDisliked }"
            :disabled="feedbackSubmitting"
            aria-label="不喜欢"
            title="不喜欢"
            @click="emit('feedback', 'dislike')"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M10 15v4a3 3 0 1 0 6 0v-4h3a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H8.72a2 2 0 0 0-1.9 1.37L4.38 11.7A2 2 0 0 0 6.28 15H10Z"
              ></path>
            </svg>
          </button>
          <AppButton
            type="button"
            variant="danger"
            size="sm"
            class="w-8 h-8 p-0 shrink-0 feedback-block-btn"
            :aria-pressed="isBlocked"
            :disabled="feedbackSubmitting"
            :aria-label="isBlocked ? '取消屏蔽' : '屏蔽'"
            :title="isBlocked ? '取消屏蔽' : '屏蔽'"
            @click="emit('block')"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M6 18L18 6M6 6l12 12"
              ></path>
            </svg>
          </AppButton>
        </div>
      </div>

      <RemoteLibraryActions
        :avid="item.avid"
        :adding="adding"
        :added="added"
        @add="emit('add')"
        @open="emit('open')"
        @view="emit('view')"
      />
    </div>
  </article>
</template>

<style scoped>
.recommendation-card {
  background: linear-gradient(180deg, var(--bg-white-8), var(--bg-white-5));
  border: 1px solid var(--border-color);
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

.recommendation-card:hover {
  transform: translateY(-4px);
  border-color: var(--accent-primary-text);
  box-shadow: var(--shadow-2xl);
}

.recommendation-card.blocked {
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--accent-primary) 3%, transparent),
    color-mix(in srgb, var(--neutral-color) 1%, transparent)
  );
  box-shadow: var(--shadow-xl);
}

.cover-shell {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--surface-raised);
}

.cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  filter: brightness(1.05);
}

.cover-image.blocked {
  filter: brightness(0.5) grayscale(0.4);
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
  color: var(--text-muted);
  font-size: 0.82rem;
  min-height: 1.2rem;
}

.reasons-wrap {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.reason-toggle {
  align-self: flex-start;
  border: 1px solid color-mix(in srgb, var(--neutral-color) 10%, transparent);
  border-radius: 999px;
  padding: 0.38rem 0.72rem;
  background: color-mix(in srgb, var(--neutral-color) 4%, transparent);
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
  border-color: color-mix(in srgb, var(--accent-primary) 28%, transparent);
  background: color-mix(in srgb, var(--accent-primary) 8%, transparent);
  color: var(--text-primary);
}

.inline-feedback-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.feedback-block-btn {
  border-radius: 999px;
}

.inline-feedback-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: 1px solid color-mix(in srgb, var(--neutral-color) 10%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent-tertiary) 10%, transparent);
  color: var(--accent-tertiary);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    background 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease;
}

.inline-feedback-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--accent-tertiary) 25%, transparent);
  background: color-mix(in srgb, var(--accent-tertiary) 16%, transparent);
}

.inline-feedback-btn.danger {
  background: color-mix(in srgb, var(--accent-primary) 10%, transparent);
  color: var(--accent-primary-text);
}

.inline-feedback-btn.danger:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent-primary) 28%, transparent);
  background: color-mix(in srgb, var(--accent-primary) 16%, transparent);
}

.inline-feedback-btn.active {
  border-color: color-mix(in srgb, var(--accent-tertiary) 36%, transparent);
  background: var(--accent-tertiary);
  color: white;
}

.inline-feedback-btn.danger.active {
  border-color: color-mix(in srgb, var(--accent-primary) 36%, transparent);
  background: var(--accent-primary);
  color: var(--on-accent);
}

.inline-feedback-btn:disabled {
  cursor: progress;
  opacity: 0.72;
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

.recommendation-card.masonry .inline-feedback-btn {
  width: 1.8rem;
  height: 1.8rem;
}
</style>
