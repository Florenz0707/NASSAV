<script setup>
import { computed, ref } from 'vue'
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

defineEmits(['add', 'open', 'view'])

const showReasons = ref(false)
const proxiedCoverUrl = computed(() => recommendationApi.getCoverUrl(props.item.cover_url))
</script>

<template>
  <article class="recommendation-card">
    <div class="cover-shell">
      <img
        v-if="item.cover_url"
        :src="proxiedCoverUrl"
        :alt="item.title || item.avid"
        class="cover-image"
        loading="lazy"
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
        {{ item.title || item.avid }}
      </h3>

      <div v-if="item.raw_metrics" class="metrics-row">
        <span v-if="item.raw_metrics.duration">时长 {{ item.raw_metrics.duration }}</span>
        <span v-if="item.raw_metrics.views">浏览 {{ item.raw_metrics.views }}</span>
        <span v-if="item.raw_metrics.likes">收藏 {{ item.raw_metrics.likes }}</span>
      </div>

      <div v-if="item.score !== undefined || item.reasons?.length" class="reasons-wrap">
        <button
          class="reason-toggle"
          :disabled="!item.reasons?.length"
          @click="item.reasons?.length && (showReasons = !showReasons)"
        >
          {{
            `推荐评分：${Number(item.score || 0).toFixed(1)}，理由（${item.reasons?.length || 0}）`
          }}
        </button>

        <div v-if="showReasons" class="reasons">
          <span v-for="reason in item.reasons" :key="reason" class="reason-pill">
            {{ reason }}
          </span>
        </div>
      </div>

      <div class="card-actions">
        <button v-if="!added" class="action-btn primary" :disabled="adding" @click="$emit('add')">
          {{ adding ? '添加中...' : '加入资源库' }}
        </button>
        <button v-else class="action-btn success" @click="$emit('view')">查看详情</button>

        <button class="action-btn secondary" @click="$emit('open')">打开来源</button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.recommendation-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02));
  border: 1px solid rgba(255, 255, 255, 0.08);
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
  border-color: rgba(255, 255, 255, 0.16);
  box-shadow: 0 22px 48px rgba(0, 0, 0, 0.28);
}

.cover-shell {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(255, 107, 107, 0.28), transparent 55%),
    linear-gradient(145deg, rgba(18, 18, 24, 0.92), rgba(28, 28, 38, 0.86));
}

.cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
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
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.metrics-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.reasons-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
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
}

.reason-toggle:disabled {
  cursor: default;
  opacity: 0.8;
}

.reason-pill {
  display: inline-flex;
  align-items: center;
  min-height: 1.9rem;
  border-radius: 999px;
  padding: 0.28rem 0.7rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
  font-size: 0.76rem;
  line-height: 1.3;
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

@media (max-width: 640px) {
  .card-actions {
    grid-template-columns: 1fr;
  }
}
</style>
