<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { downloadApi, resourceApi } from '../api'
import { useToastStore } from '../stores/toast'
import { useSettingsStore } from '../stores/settings'
import { RouterLink, useRoute } from 'vue-router'
import ConfirmDialog from './ConfirmDialog.vue'

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
const settingsStore = useSettingsStore()
const placeholder = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='
const coverUrl = ref(placeholder)
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
const displayedTitle = computed(() => {
  const titleField = settingsStore.displayTitle
  const resource = props.resource

  if (titleField === 'original_title' && resource.original_title) {
    return resource.original_title
  }
  if (titleField === 'source_title' && resource.source_title) {
    return resource.source_title
  }
  if (titleField === 'translated_title' && resource.translated_title) {
    return resource.translated_title
  }

  // 降级逻辑：如果首选字段不存在，按优先级返回可用的标题
  return (
    resource.translated_title ||
    resource.source_title ||
    resource.original_title ||
    resource.title ||
    resource.avid
  )
})

const toastStore = useToastStore()
const showDeleteMenu = ref(false)
const showRefreshMenu = ref(false)
const showConfirmDialog = ref(false)
const pendingDeleteOption = ref(null)
const downloading = ref(false)
const refreshMenuFlip = ref(false)
const deleteMenuFlip = ref(false)

// 生成刷新菜单选项
const refreshOptions = [
  { text: '全部刷新', params: { refresh_m3u8: true, refresh_metadata: true, retranslate: false } },
  {
    text: '刷新 M3U8',
    params: { refresh_m3u8: true, refresh_metadata: false, retranslate: false },
  },
  {
    text: '刷新元数据',
    params: { refresh_m3u8: false, refresh_metadata: true, retranslate: false },
  },
  { text: '重新翻译', params: { refresh_m3u8: false, refresh_metadata: false, retranslate: true } },
  {
    text: '元数据+翻译',
    params: { refresh_m3u8: false, refresh_metadata: true, retranslate: true },
  },
]

function handleDownloadClick() {
  if (downloading.value || props.resource.has_video) return
  downloading.value = true
  emit('download', props.resource.avid)
  setTimeout(() => {
    downloading.value = false
  }, 4000)
}

watch(
  () => props.resource.has_video,
  (val) => {
    if (val) downloading.value = false
  }
)

function openDeleteMenu(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  deleteMenuFlip.value = rect.top < 140
  showDeleteMenu.value = !showDeleteMenu.value
}

function handleRefreshOption(option) {
  showRefreshMenu.value = false
  emit('refresh', props.resource.avid, option.params)
}

// 生成删除菜单选项
const deleteOptions = computed(() => {
  const isDownloaded = props.resource.has_video
  const baseOptions = []

  if (isDownloaded) {
    baseOptions.push(
      {
        text: '删除视频',
        action: 'deleteFile',
        confirm: '确定要删除视频文件吗？元数据和封面将保留',
      },
      {
        text: '全部删除',
        action: 'delete',
        confirm: '确定要删除该资源的所有数据（包括视频、元数据、封面）吗？',
      }
    )
  } else {
    baseOptions.push({
      text: '删除数据',
      action: 'delete',
      confirm: '确定要删除该资源的元数据和封面吗？',
    })
  }
  return baseOptions
})

function handleDeleteOption(option) {
  pendingDeleteOption.value = option
  showConfirmDialog.value = true
  showDeleteMenu.value = false
}

// 确认删除操作
async function confirmDelete() {
  const option = pendingDeleteOption.value
  if (!option) return

  try {
    if (option.action === 'deleteFile') {
      await downloadApi.deleteFile(props.resource.avid)
      toastStore.success('视频文件已删除')
      emit('deleteFile', props.resource.avid)
    } else {
      await resourceApi.delete(props.resource.avid)
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

// 点击外部关闭菜单
function handleKeydown(e) {
  if (e.key === 'Escape') {
    showDeleteMenu.value = false
    showRefreshMenu.value = false
  }
}

function closeMenuOnOutsideClick(event) {
  const deleteMenu = document.querySelector(`.delete-menu[data-avid="${props.resource.avid}"]`)
  const deleteBtn = document.querySelector(`.delete-btn[data-avid="${props.resource.avid}"]`)
  if (
    deleteMenu &&
    deleteBtn &&
    !deleteMenu.contains(event.target) &&
    !deleteBtn.contains(event.target)
  ) {
    showDeleteMenu.value = false
  }

  const refreshMenu = document.querySelector(`.refresh-menu[data-avid="${props.resource.avid}"]`)
  const refreshBtn = document.querySelector(`.refresh-btn[data-avid="${props.resource.avid}"]`)
  if (
    refreshMenu &&
    refreshBtn &&
    !refreshMenu.contains(event.target) &&
    !refreshBtn.contains(event.target)
  ) {
    showRefreshMenu.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', closeMenuOnOutsideClick)
  document.addEventListener('keydown', handleKeydown)
  // wait for DOM
  nextTick(() => {
    imgEl = document.querySelector(`img[data-avid="${props.resource.avid}"]`)
    if (imgEl) ensureObserver().observe(imgEl)
  })
})
onUnmounted(() => {
  document.removeEventListener('click', closeMenuOnOutsideClick)
  document.removeEventListener('keydown', handleKeydown)
  if (observer && imgEl) observer.unobserve(imgEl)
})
</script>

<template>
  <div
    class="relative rounded-2xl overflow-hidden border transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_12px_40px_rgba(0,0,0,0.3)]"
    :class="statusClass"
    :style="
      selected
        ? 'background: var(--card-bg); border-color: rgba(255,107,107,0.75); box-shadow: 0 0 0 3px rgba(255,107,107,0.2);'
        : 'background: var(--card-bg); border-color: rgba(255,107,107,0.35);'
    "
    @mouseenter="!selected && ($event.currentTarget.style.borderColor = 'rgba(255,107,107,0.2)')"
    @mouseleave="
      !selected &&
      ($event.currentTarget.style.borderColor = selected
        ? 'rgba(255,107,107,0.75)'
        : 'rgba(255,107,107,0.35)')
    "
  >
    <!-- 选择复选框（可选） -> 放到封面内以保证可见性 -->
    <!-- 封面图 -->
    <div class="relative aspect-video overflow-hidden bg-black/30 group">
      <!-- checkbox placed over cover for visibility -->
      <template v-if="selectable">
        <label
          class="absolute z-30 top-3 left-3 inline-flex items-center cursor-pointer"
          aria-label="选择资源"
        >
          <input
            type="checkbox"
            class="sr-only"
            :checked="selected"
            @change.stop="$emit('toggle-select', resource.avid, $event.target.checked)"
          />
          <span
            :class="[
              'w-6 h-6 flex items-center justify-center rounded-md transition border-2',
              selected
                ? 'border-white shadow-lg'
                : 'bg-[rgba(128,128,128,0.6)] border-white text-white',
            ]"
            :style="
              selected ? 'background: linear-gradient(135deg, var(--accent-primary), #ff5252)' : ''
            "
          >
            <svg
              v-if="selected"
              class="w-3 h-3 text-white"
              viewBox="0 0 20 20"
              fill="currentColor"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                fill-rule="evenodd"
                clip-rule="evenodd"
                d="M16.707 5.293a1 1 0 00-1.414-1.414L7 12.172l-2.293-2.293A1 1 0 003.293 11.293l3 3a1 1 0 001.414 0l9-9z"
              />
            </svg>
          </span>
        </label>
      </template>
      <img
        :data-avid="resource.avid"
        :src="coverUrl"
        :alt="displayedTitle"
        loading="lazy"
        class="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
      />
      <div
        class="absolute inset-0 bg-black/60 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300"
      >
        <RouterLink
          :to="{ path: `/resource/${resource.avid}`, query: { from: route.fullPath } }"
          class="px-6 py-3 text-white rounded-lg font-medium text-sm transition-transform hover:scale-105"
          style="background: var(--accent-primary)"
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
          style="color: var(--accent-primary); background: rgba(255, 107, 107, 0.15)"
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
        <!-- 刷新按钮容器 -->
        <div class="relative" @click.stop>
          <button
            class="refresh-btn inline-flex items-center justify-center px-3.5 py-2 rounded-lg text-[0.9rem] font-medium cursor-pointer transition-all duration-200"
            :data-avid="resource.avid"
            title="刷新资源"
            style="
              background: var(--bg-secondary);
              color: var(--text-secondary);
              border: 1px solid var(--border-color);
            "
            @click="showRefreshMenu = !showRefreshMenu"
            @mouseenter="
              (($event.target.style.background = 'var(--bg-overlay)'),
              ($event.target.style.color = 'var(--text-primary)'))
            "
            @mouseleave="
              (($event.target.style.background = 'var(--bg-secondary)'),
              ($event.target.style.color = 'var(--text-secondary)'))
            "
          >
            刷新
          </button>

          <!-- 刷新下拉菜单 -->
          <div
            v-if="showRefreshMenu"
            :data-avid="resource.avid"
            role="menu"
            :class="
              refreshMenuFlip
                ? 'absolute top-[calc(100%+0.5rem)] left-0'
                : 'absolute bottom-[calc(100%+0.5rem)] left-0'
            "
            class="refresh-menu border rounded-lg shadow-[0_4px_12px_rgba(0,0,0,0.2)] min-w-[120px] z-[100] overflow-hidden"
            style="background: var(--bg-overlay); border-color: var(--border-color)"
          >
            <button
              v-for="option in refreshOptions"
              :key="option.text"
              role="menuitem"
              class="w-full px-4 py-2.5 text-left bg-transparent border-none text-[var(--text-secondary)] text-[0.85rem] cursor-pointer transition-colors duration-200 hover:bg-white/[0.08] hover:text-[var(--text-primary)]"
              @click="handleRefreshOption(option)"
            >
              {{ option.text }}
            </button>
          </div>
        </div>

        <button
          :class="[
            'inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-[0.9rem] font-medium transition-all duration-200',
            resource.has_video || downloading
              ? 'cursor-not-allowed opacity-60'
              : 'text-white cursor-pointer hover:shadow-lg hover:-translate-y-0.5',
          ]"
          :style="
            resource.has_video || downloading
              ? 'background: var(--bg-secondary); color: var(--text-muted); border: 1px solid var(--border-color)'
              : 'background: linear-gradient(135deg, var(--accent-primary), #ff5252)'
          "
          :disabled="resource.has_video || downloading"
          :title="resource.has_video ? '视频已下载' : downloading ? '下载中...' : '提交下载任务'"
          @click="handleDownloadClick"
        >
          <svg
            v-if="downloading"
            class="w-3.5 h-3.5 animate-spin"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <circle
              cx="12"
              cy="12"
              r="10"
              stroke-width="2.5"
              stroke-dasharray="32"
              stroke-dashoffset="12"
            />
          </svg>
          {{ resource.has_video ? '已下载' : downloading ? '下载中' : '下载' }}
        </button>

        <!-- 删除按钮容器 -->
        <div class="relative" @click.stop>
          <button
            class="delete-btn inline-flex items-center justify-center px-3.5 py-2 rounded-lg text-[0.9rem] font-medium cursor-pointer transition-all duration-200 text-[var(--accent-danger)] border border-[var(--accent-danger)]/20 bg-[var(--accent-danger)]/10 hover:bg-[var(--accent-danger)]/20"
            :data-avid="resource.avid"
            title="删除"
            aria-label="删除"
            aria-haspopup="menu"
            :aria-expanded="showDeleteMenu"
            @click="openDeleteMenu($event)"
          >
            删除
          </button>

          <!-- 删除下拉菜单 -->
          <div
            v-if="showDeleteMenu"
            :data-avid="resource.avid"
            role="menu"
            :class="
              deleteMenuFlip
                ? 'absolute top-[calc(100%+0.5rem)] right-0'
                : 'absolute bottom-[calc(100%+0.5rem)] right-0'
            "
            class="delete-menu border rounded-lg shadow-[0_4px_12px_rgba(0,0,0,0.2)] min-w-[85px] z-[100] overflow-hidden max-h-[calc(100vh-20px)] overflow-y-auto"
            style="background: var(--bg-overlay); border-color: var(--border-color)"
          >
            <button
              v-for="option in deleteOptions"
              :key="option.action"
              role="menuitem"
              class="w-full px-4 py-2.5 text-center border-none text-[0.8rem] cursor-pointer transition-colors duration-200 text-[var(--accent-danger)] bg-[var(--accent-danger)]/20 hover:bg-[var(--accent-danger)]/10"
              @click="handleDeleteOption(option)"
            >
              {{ option.text }}
            </button>
          </div>
        </div>
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
