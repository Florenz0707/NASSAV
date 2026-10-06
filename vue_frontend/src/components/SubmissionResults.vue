<script setup>
import { computed } from 'vue'
import { resolveResourceTitle } from '../utils/resourceTitle.js'
const props = defineProps({
  result: { type: Object, default: null },
  preferredTitle: { type: String, default: 'source_title' },
})
defineEmits(['view'])
const displayedTitle = computed(() =>
  resolveResourceTitle(props.result?.data, props.preferredTitle)
)
</script>
<template>
  <!-- 添加结果 -->
  <Transition name="result">
    <div
      v-if="result && result.total === 1 && result.data"
      class="result-card"
      :class="{ success: result.success.length > 0, exists: result.exists.length > 0 }"
    >
      <div class="result-header">
        <div class="result-icon">
          <svg
            v-if="result.success.length > 0"
            class="w-6 h-6 text-accent-success"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M5 13l4 4L19 7"
            ></path>
          </svg>
          <svg
            v-else-if="result.exists.length > 0"
            class="w-6 h-6 text-accent-tertiary"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <circle cx="12" cy="12" r="10" stroke-width="2"></circle>
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M12 8v4m0 4h.01"
            ></path>
          </svg>
          <svg
            v-else
            class="w-6 h-6 text-accent-danger"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M6 18L18 6M6 6l12 12"
            ></path>
          </svg>
        </div>
        <h2 class="result-title">
          {{
            result.success.length > 0
              ? '添加成功'
              : result.exists.length > 0
                ? '资源已存在'
                : '添加失败'
          }}
        </h2>
      </div>

      <div class="result-details">
        <div class="result-item">
          <span class="result-label">编号</span>
          <span class="result-value avid">{{ result.data.avid }}</span>
        </div>
        <div v-if="displayedTitle" class="result-item">
          <span class="result-label">标题</span>
          <span class="result-value">{{ displayedTitle }}</span>
        </div>
        <div v-if="result.data.source" class="result-item">
          <span class="result-label">来源</span>
          <span class="result-value source">{{ result.data.source }}</span>
        </div>
        <div v-if="result.success.length > 0 || result.exists.length > 0" class="result-checks">
          <div class="check-item" :class="{ done: result.data.cover_downloaded }">
            <span class="check-icon">
              <svg
                v-if="result.data.cover_downloaded"
                class="w-4 h-4 text-accent-success"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M5 13l4 4L19 7"
                ></path>
              </svg>
              <svg
                v-else
                class="w-4 h-4 text-muted"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="10" stroke-width="2"></circle>
              </svg>
            </span>
            封面下载
          </div>
          <div class="check-item" :class="{ done: result.data.metadata_saved }">
            <span class="check-icon">
              <svg
                v-if="result.data.metadata_saved"
                class="w-4 h-4 text-accent-success"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M5 13l4 4L19 7"
                ></path>
              </svg>
              <svg
                v-else
                class="w-4 h-4 text-muted"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="10" stroke-width="2"></circle>
              </svg>
            </span>
            元数据保存
          </div>
          <div v-if="result.data.source" class="check-item" :class="{ done: result.data.scraped }">
            <span class="check-icon">
              <svg
                v-if="result.data.scraped"
                class="w-4 h-4 text-accent-success"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M5 13l4 4L19 7"
                ></path>
              </svg>
              <svg
                v-else
                class="w-4 h-4 text-muted"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="10" stroke-width="2"></circle>
              </svg>
            </span>
            信息刮削
          </div>
        </div>
      </div>

      <div class="result-actions">
        <button
          class="btn-primary rounded-lg px-6 py-3 hover:bg-opacity-80 transition-colors duration-200"
          @click="$emit('view')"
        >
          查看详情
        </button>
      </div>
    </div>
  </Transition>

  <!-- 批量添加结果 -->
  <Transition name="result">
    <div v-if="result && (result.total > 1 || !result.data)" class="batch-result-card">
      <div class="batch-result-header">
        <h2 class="batch-result-title">
          {{ result.total > 1 ? '批量提交结果' : '提交结果' }}
        </h2>
        <div class="batch-result-stats">
          <div class="stat-item success">
            <span class="stat-icon"
              ><svg
                class="w-4 h-4 text-accent-success"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M5 13l4 4L19 7"
                ></path></svg
            ></span>
            <span class="stat-label">已排队</span>
            <span class="stat-value">{{ result.queued?.length || 0 }}</span>
          </div>
          <div class="stat-item success">
            <span class="stat-label">已完成</span>
            <span class="stat-value">{{ result.success.length }}</span>
          </div>
          <div class="stat-item exists">
            <span class="stat-icon"
              ><svg
                class="w-4 h-4 text-accent-tertiary"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="10" stroke-width="2"></circle>
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 8v4m0 4h.01"
                ></path></svg
            ></span>
            <span class="stat-label">已存在</span>
            <span class="stat-value">{{ result.exists.length }}</span>
          </div>
          <div class="stat-item failed">
            <span class="stat-icon"
              ><svg
                class="w-4 h-4 text-accent-danger"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M6 18L18 6M6 6l12 12"
                ></path></svg
            ></span>
            <span class="stat-label">失败</span>
            <span class="stat-value">{{ result.failed.length }}</span>
          </div>
        </div>
      </div>

      <div class="batch-result-details">
        <div v-if="result.queued?.length > 0" class="result-group">
          <h3 class="result-group-title success">已排队 ({{ result.queued.length }})</h3>
          <div class="result-group-list">
            <span
              v-for="successAvid in result.queued"
              :key="successAvid"
              class="result-tag success"
              >{{ successAvid }}</span
            >
          </div>
        </div>

        <div v-if="result.success.length > 0" class="result-group">
          <h3 class="result-group-title success">已完成 ({{ result.success.length }})</h3>
          <div class="result-group-list">
            <span
              v-for="successAvid in result.success"
              :key="successAvid"
              class="result-tag success"
              >{{ successAvid }}</span
            >
          </div>
        </div>

        <div v-if="result.exists.length > 0" class="result-group">
          <h3 class="result-group-title exists">ℹ 已存在 ({{ result.exists.length }})</h3>
          <div class="result-group-list">
            <span v-for="existsAvid in result.exists" :key="existsAvid" class="result-tag exists">{{
              existsAvid
            }}</span>
          </div>
        </div>

        <div v-if="result.failed.length > 0" class="result-group">
          <h3 class="result-group-title failed flex items-center gap-2">
            <AppIcon name="close" /> 添加失败 ({{ result.failed.length }})
          </h3>
          <div class="result-group-list">
            <span
              v-for="failedItem in result.failed"
              :key="failedItem.avid"
              class="result-tag failed"
              :class="`error-${failedItem.code}`"
            >
              {{ failedItem.avid }}:{{ failedItem.code }}
            </span>
          </div>
        </div>
      </div>

      <div class="result-actions">
        <button
          v-if="result.success.length === 1"
          class="btn-primary rounded-lg px-6 py-3 hover:bg-opacity-80 transition-colors duration-200"
          @click="$emit('view')"
        >
          查看详情
        </button>
      </div>
    </div>
  </Transition>
</template>
