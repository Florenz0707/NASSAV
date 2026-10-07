<script setup>
import { resolveResourceTitle } from '../lib/resourceTitle.js'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { resourceApi } from '../../../api/index.js'
import { useResourceStore } from '../stores/resource.js'
import { useToastStore } from '../../../shared/stores/toast.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { RouterLink, useRoute } from 'vue-router'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import ActionMenu from '../../../shared/ui/ActionMenu.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppCheckbox from '../../../shared/ui/AppCheckbox.vue'
import { resourceRefreshOptions, resourceDeleteOptions } from '../lib/resourceActions.js'
import ResourceCover from '../../../shared/ui/ResourceCover.vue'

const props = defineProps({
  resource: {
    type: Object,
    required: true,
  },
  selectable: {
    type: Boolean,
    default: false,
  },
  selected: {
    type: Boolean,
    default: false,
  },
  // preferred cover size for this card: 'small'|'medium'|'large' or undefined for original
  coverSize: {
    type: String,
    default: 'medium',
  },
})

const emit = defineEmits(['download', 'refresh', 'delete', 'deleteFile', 'toggle-select'])
// add toggle-select event if selectable
if (typeof emit === 'function') {
  // nothing, emit already available
}

const route = useRoute()
const resourceStore = useResourceStore()
const settingsStore = useSettingsStore()
const coverUrl = ref('')
const coverImage = ref(null)
let observer = null
let imgEl = null

async function loadCover() {
  // Prefer backend-provided thumbnail_url or cover_url if present
  if (props.resource) {
    if (props.resource.thumbnail_url) {
      coverUrl.value = props.resource.thumbnail_url
      return
    }
    if (props.resource.cover_url) {
      coverUrl.value = props.resource.cover_url
      return
    }
  }
  // fallback: request server thumbnail of preferred size (avoids blob downloads)
  try {
    const url = resourceApi.getCoverUrl(props.resource.avid, props.coverSize)
    coverUrl.value = url
  } catch {
    // last-resort: blob object URL
    try {
      const obj = await resourceApi.getCoverObjectUrl(props.resource.avid)
      if (obj) coverUrl.value = obj
    } catch {
      coverUrl.value = resourceApi.getCoverUrl(props.resource.avid)
    }
  }
}

function ensureObserver() {
  if (observer) return observer
  observer = new IntersectionObserver(
    (entries) => {
      for (const ent of entries) {
        if (ent.isIntersecting) {
          loadCover()
          if (imgEl) observer.unobserve(imgEl)
        }
      }
    },
    { rootMargin: '200px' }
  )
  return observer
}

const statusClass = computed(() => ({
  downloaded: props.resource.has_video,
  pending: !props.resource.has_video,
}))

// 根据设置选择显示的标题
const displayedTitle = computed(() =>
  resolveResourceTitle(props.resource, settingsStore.displayTitle)
)

const toastStore = useToastStore()
const showConfirmDialog = ref(false)
const pendingDeleteOption = ref(null)
const downloadState = computed(() => resourceStore.getDownloadState(props.resource.avid))
const isSubmittingDownload = computed(() => downloadState.value === 'submitting')
const isDownloading = computed(() => downloadState.value === 'downloading')
const isDownloadBusy = computed(() => isSubmittingDownload.value || isDownloading.value)

// 生成刷新菜单选项
const refreshOptions = resourceRefreshOptions()

function handleDownloadClick() {
  if (isDownloadBusy.value || props.resource.has_video) return
  emit('download', props.resource.avid)
}

function handleRefreshOption(option) {
  emit('refresh', props.resource.avid, option.params)
}

// 生成删除菜单选项
const deleteOptions = computed(() => resourceDeleteOptions(props.resource.has_video))

function handleDeleteOption(option) {
  pendingDeleteOption.value = option
  showConfirmDialog.value = true
}

// 确认删除操作
async function confirmDelete() {
  const option = pendingDeleteOption.value
  if (!option) return

  try {
    if (option.action === 'deleteFile') {
      await resourceStore.removeAsset(props.resource.avid, 'deleteFile')
      toastStore.success('视频文件已删除')
      emit('deleteFile', props.resource.avid)
    } else {
      await resourceStore.removeAsset(props.resource.avid, 'delete')
      toastStore.success('资源已删除')
      emit('delete', props.resource.avid)
    }
  } catch (err) {
    toastStore.error(err.message || `删除${option.action === 'deleteFile' ? '视频' : '资源'}失败`)
  } finally {
    pendingDeleteOption.value = null
  }
}

// 取消删除操作
function cancelDelete() {
  pendingDeleteOption.value = null
}

onMounted(() => {
  // wait for DOM
  nextTick(() => {
    imgEl = coverImage.value?.$el
    if (imgEl) ensureObserver().observe(imgEl)
  })
})
onUnmounted(() => {
  if (observer && imgEl) observer.unobserve(imgEl)
})
</script>

<template>
  <div
    class="relative rounded-2xl overflow-hidden border transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_12px_40px_color-mix(in_srgb,_var(--shadow-color)_30%,_transparent)]"
    :class="statusClass"
    :style="
      selected
        ? 'background: var(--card-bg); border-color: color-mix(in srgb, var(--accent-primary) 75%, transparent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-primary) 20%, transparent);'
        : 'background: var(--card-bg); border-color: var(--border-color);'
    "
    @mouseenter="
      !selected &&
      ($event.currentTarget.style.borderColor =
        'color-mix(in srgb, var(--accent-primary) 20%, transparent)')
    "
    @mouseleave="
      !selected &&
      ($event.currentTarget.style.borderColor = selected
        ? 'color-mix(in srgb, var(--accent-primary) 75%, transparent)'
        : 'color-mix(in srgb, var(--accent-primary) 35%, transparent)')
    "
  >
    <!-- 选择复选框（可选） -> 放到封面内以保证可见性 -->
    <!-- 封面图 -->
    <div class="relative aspect-video overflow-hidden bg-black/30 group">
      <!-- checkbox placed over cover for visibility -->
      <template v-if="selectable">
        <AppCheckbox
          class="absolute z-30 top-3 left-3"
          :checked="selected"
          :label="'选择资源 ' + resource.avid"
          @change="$emit('toggle-select', resource.avid, $event)"
        />
      </template>
      <ResourceCover
        ref="coverImage"
        :data-avid="resource.avid"
        :url="coverUrl"
        :title="displayedTitle"
        class="w-full h-full transition-transform duration-200 group-hover:scale-105"
      />
      <div
        class="absolute inset-0 bg-black/60 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300"
      >
        <RouterLink
          :to="{ path: `/resource/${resource.avid}`, query: { from: route.fullPath } }"
          class="tw-btn-primary px-6 py-3 rounded-lg text-sm"
        >
          查看详情
        </RouterLink>
      </div>
    </div>

    <!-- 卡片内容 -->
    <div class="p-5 relative">
      <!-- 元数据头部 -->
      <div class="flex gap-4 mb-2.5 items-center flex-wrap">
        <div
          class="text-[0.85rem] font-semibold rounded-md w-fit px-2 py-1"
          style="
            color: var(--accent-primary-text);
            background: color-mix(in srgb, var(--accent-primary) 15%, transparent);
          "
        >
          {{ resource.avid }}
        </div>
        <!-- 类别标签 -->
        <div
          v-for="genre in (resource.genres || []).slice(0, 2)"
          :key="genre"
          class="text-[0.85rem] font-normal rounded-md w-fit px-2 py-1"
          style="color: var(--genre-tag-text); background: var(--genre-tag-bg)"
        >
          #{{ genre }}
        </div>
      </div>

      <!-- 标题 -->
      <h3
        class="text-base font-medium leading-[1.4] mb-3 line-clamp-2 min-h-[2.8em]"
        :title="displayedTitle"
        style="color: var(--text-primary)"
      >
        {{ displayedTitle }}
      </h3>

      <!-- 元信息 -->
      <div class="flex flex-wrap gap-8 mb-4">
        <span class="flex items-center gap-1.5 text-[0.9rem] text-[var(--text-muted)]">
          <svg class="w-3 h-3 opacity-70 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <circle cx="10" cy="10" r="4" />
          </svg>
          {{ resource.source }}
        </span>
        <span
          v-if="resource.release_date"
          class="flex items-center gap-1.5 text-[0.9rem] text-[var(--text-muted)]"
        >
          <svg
            class="w-3 h-3 opacity-70 flex-shrink-0"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <circle cx="10" cy="10" r="7" />
            <path stroke-linecap="round" d="M10 6v4l2.5 2.5" />
          </svg>
          {{ resource.release_date }}
        </span>
      </div>

      <!-- 操作按钮 -->
      <div class="flex gap-2 justify-between items-center relative">
        <ActionMenu
          :label="'刷新资源'"
          button-text="刷新"
          compact
          trigger-class="h-10 px-3.5 py-2 rounded-lg font-medium "
          :options="refreshOptions"
          @select="handleRefreshOption"
        />

        <AppButton
          class="h-10 px-3.5 py-2 rounded-lg font-medium"
          :loading="isSubmittingDownload"
          :disabled="resource.has_video || isDownloading"
          :title="
            resource.has_video
              ? '视频已下载'
              : isSubmittingDownload
                ? '正在提交下载请求...'
                : isDownloading
                  ? '视频下载中...'
                  : '提交下载任务'
          "
          @click="handleDownloadClick"
        >
          {{
            resource.has_video
              ? '已下载'
              : isSubmittingDownload
                ? '下载'
                : isDownloading
                  ? '下载中'
                  : '下载'
          }}
        </AppButton>

        <ActionMenu
          label="删除"
          :options="deleteOptions"
          compact
          trigger-class="h-10 px-3.5 py-2 rounded-lg font-medium "
          danger
          align="right"
          @select="handleDeleteOption"
        />
      </div>
    </div>

    <!-- 确认对话框 -->
    <ConfirmDialog
      v-model:show="showConfirmDialog"
      :title="pendingDeleteOption?.action === 'deleteFile' ? '删除视频文件' : '删除资源'"
      :message="pendingDeleteOption?.confirm || ''"
      :type="'danger'"
      confirm-text="确认删除"
      cancel-text="取消"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />
  </div>
</template>

<style scoped>
/* 响应式调整 - 仅保留必要的媒体查询 */
@media (max-width: 480px) {
  .card-actions button span:not(:first-child) {
    display: none;
  }

  .card-actions button {
    padding: 0.5rem;
  }
}
</style>
