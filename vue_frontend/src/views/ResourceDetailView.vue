<script setup>
import { useMembershipsStore } from '../features/library/stores/memberships.js'
import { useSessionStore } from '../features/auth/stores/session.js'
import PageLoad from '../shared/ui/PageLoad.vue'
import RequestError from '../shared/ui/RequestError.vue'
import { resolveResourceTitle } from '../features/resources/lib/resourceTitle.js'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { actorApi, genreApi, resourceApi } from '../api/index.js'
import { useResourceStore } from '../features/resources/stores/resource.js'
import { useToastStore } from '../shared/stores/toast.js'
import { useSettingsStore } from '../features/settings/stores/settings.js'
import { createRequestGuard } from '../shared/lib/requestGuard.js'
import ConfirmDialog from '../shared/ui/ConfirmDialog.vue'
import ActionMenu from '../shared/ui/ActionMenu.vue'
import AppButton from '../shared/ui/AppButton.vue'
import {
  resourceRefreshOptions,
  resourceDeleteOptions,
} from '../features/resources/lib/resourceActions.js'
import ResourceCover from '../shared/ui/ResourceCover.vue'
import PersonalResourceActions from '../features/resources/components/PersonalResourceActions.vue'
import PersonalResourcePanel from '../features/resources/components/PersonalResourcePanel.vue'

const route = useRoute()
const router = useRouter()
const resourceStore = useResourceStore()
const shared = computed(() => Boolean(useSessionStore().capabilities.shared_library))
const toastStore = useToastStore()
const settingsStore = useSettingsStore()

const avid = computed(() => route.params.avid)
const metadata = ref(null)
const loading = ref(true)
const error = ref(null)
const refreshing = ref(false)
const showConfirmDialog = ref(false)
const pendingDeleteAction = ref(null)
function openPlayback(mode = 'source') {
  window.open(
    router.resolve({
      name: 'Playback',
      params: { avid: avid.value },
      query: { mode },
    }).href,
    '_blank',
    'noopener,noreferrer'
  )
}

// 刷新菜单选项
const refreshOptions = computed(() => resourceRefreshOptions(true, shared.value))

// 删除菜单选项（根据文件是否存在动态计算）
const deleteOptions = computed(() =>
  resourceDeleteOptions(metadata.value?.file_exists, true, shared.value)
)

watch(
  () => useMembershipsStore().revision,
  () => {
    if (shared.value) fetchMetadata(true)
  }
)

const coverUrl = ref(null)
const downloadState = computed(() => resourceStore.getDownloadState(avid.value))
const isSubmittingDownload = computed(() => downloadState.value === 'submitting')
const isDownloading = computed(() => downloadState.value === 'downloading')

watch(
  () => resourceStore.getScrapeJobForAvid(avid.value)?.state,
  (state, previous) => {
    if (state === 'succeeded' && previous !== 'succeeded') fetchMetadata(true)
  }
)

// 根据设置选择显示的标题
const displayedTitle = computed(() =>
  resolveResourceTitle(metadata.value, settingsStore.displayTitle)
)

async function loadCover() {
  if (!avid.value) return
  // For detail view prefer the original/full cover URL (no size)
  coverUrl.value = resourceApi.getCoverUrl(avid.value)
}

watch(avid, () => loadCover(), { immediate: true })

const fileSize = computed(() => {
  if (!metadata.value?.file_size) return null
  const bytes = metadata.value.file_size
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
})

function applyPersonalState(snapshot) {
  if (metadata.value?.avid === snapshot.avid) Object.assign(metadata.value, snapshot)
}

const metadataGuard = createRequestGuard()
onBeforeUnmount(() => metadataGuard.invalidate())
watch(
  avid,
  () => {
    metadata.value = null
    fetchMetadata()
  },
  { immediate: true }
)

async function fetchMetadata(bypassCache = false) {
  const request = metadataGuard.begin()
  const currentAvid = avid.value
  loading.value = true
  error.value = null
  try {
    const response = await resourceApi.getMetadata(currentAvid, bypassCache)
    if (metadataGuard.current(request)) metadata.value = response.data
  } catch (err) {
    if (err.code === 'user_cancelled') return
    if (metadataGuard.current(request)) error.value = err.message || '获取元数据失败'
  } finally {
    if (metadataGuard.current(request)) loading.value = false
  }
}

async function handleDownload() {
  try {
    await resourceStore.submitDownload(avid.value, metadata.value?.source)
    toastStore.success('下载任务已提交')
  } catch (err) {
    if (err.code === 'user_cancelled') return
    if (!shared.value && err.code === 409) {
      toastStore.info('视频已下载')
      // 即使已下载，也刷新元数据确保状态正确
      await fetchMetadata()
    } else {
      toastStore.error(err.message || '提交下载失败')
    }
  }
}

async function handleRefresh(params = null) {
  refreshing.value = true
  try {
    await resourceStore.refreshResource(
      avid.value,
      shared.value ? { source: metadata.value?.source } : params
    )
  } catch (err) {
    if (err.code === 'user_cancelled') return
    toastStore.error(err.message || '刷新失败')
  } finally {
    refreshing.value = false
  }
}

function handleRefreshOption(option) {
  handleRefresh(option.params)
}

function goBack() {
  const fromPath = route.query.from
  if (fromPath) {
    // 如果有来源页面，直接跳转回去（保留所有 query 参数）
    router.push(fromPath)
  } else {
    // 否则使用浏览器后退
    router.back()
  }
}

// 处理删除菜单选项
function handleDeleteOption(option) {
  pendingDeleteAction.value = option
  showConfirmDialog.value = true
}

// 确认删除操作
async function confirmDelete() {
  const action = pendingDeleteAction.value
  if (!action) return

  try {
    if (action.action === 'deleteFile') {
      await resourceStore.removeAsset(avid.value, 'deleteFile')
      toastStore.success('视频文件已删除')
      await fetchMetadata() // 刷新元数据以更新状态
    } else {
      await resourceStore.removeAsset(avid.value, 'delete')
      toastStore.success(shared.value ? '已移出我的资源库' : '资源已删除')
      // 删除后返回上一页
      setTimeout(() => router.back(), 500)
    }
  } catch (err) {
    if (err.code === 'user_cancelled') return
    toastStore.error(err.message || `删除${action.action === 'deleteFile' ? '视频' : '资源'}失败`)
  } finally {
    pendingDeleteAction.value = null
  }
}

// 取消删除操作
function cancelDelete() {
  pendingDeleteAction.value = null
}

// 跳转到演员详情页
async function navigateToActor(actorName) {
  if (!actorName) return
  try {
    // 通过名称查询演员 ID
    const response = await actorApi.getList({ search: actorName, page_size: 1 })
    if (response?.data?.length > 0) {
      const actorId = response.data[0].id
      router.push(`/actors/${actorId}`)
    } else {
      toastStore.warning(`未找到演员：${actorName}`)
    }
  } catch (err) {
    if (err.code === 'user_cancelled') return
    toastStore.error('跳转失败')
    console.error('Navigate to actor failed:', err)
  }
}

// 跳转到类别详情页
async function navigateToGenre(genreName) {
  if (!genreName) return
  try {
    // 通过名称查询类别 ID
    const response = await genreApi.getList({ search: genreName, page_size: 1 })
    if (response?.data?.length > 0) {
      const genreId = response.data[0].id
      router.push(`/genres/${genreId}`)
    } else {
      toastStore.warning(`未找到类别：${genreName}`)
    }
  } catch (err) {
    if (err.code === 'user_cancelled') return
    toastStore.error('跳转失败')
    console.error('Navigate to genre failed:', err)
  }
}
</script>

<template>
  <div class="animate-[fadeIn_0.5s_ease]">
    <!-- 返回按钮 -->
    <button class="tw-back-btn mb-10" @click="goBack">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M19 12H5M12 5l-7 7 7 7"
        />
      </svg>
      返回
    </button>

    <PageLoad v-if="loading && !metadata" variant="detail" text="正在加载详情" />
    <RequestError
      v-if="error && !loading"
      :message="error"
      :compact="!!metadata"
      @retry="fetchMetadata()"
    />
    <PageLoad v-if="loading && metadata" variant="spinner" text="正在更新详情" />

    <!-- 详情内容 -->
    <template v-if="metadata">
      <!-- 头部信息 -->
      <PersonalResourcePanel :resource="metadata" @updated="applyPersonalState">
        <template #default="{ state, save }">
          <div class="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-10 items-start">
            <!-- 封面和状态按钮 -->
            <div class="flex justify-center">
              <div class="detail-cover-actions flex flex-col gap-[1.2rem] max-w-full">
                <ResourceCover
                  :url="coverUrl"
                  :title="displayedTitle"
                  natural-size
                  image-class="object-contain rounded-2xl shadow-lg"
                  class="detail-cover"
                />
                <PersonalResourceActions :state="state" @change="save" />
              </div>
            </div>

            <!-- 右侧信息 -->
            <div class="flex flex-col min-w-0">
              <!-- AVID 和状态 -->
              <div class="grid grid-cols-2 gap-4 mb-2.5">
                <div
                  class="inline-block px-3.5 py-1.5 rounded-md font-['JetBrains_Mono',monospace] text-[0.9rem] font-semibold text-[var(--accent-primary)] w-fit"
                  style="background: color-mix(in srgb, var(--accent-primary) 15%, transparent)"
                >
                  {{ metadata.avid }}
                </div>
                <div
                  class="inline-block px-3.5 py-1.5 rounded-md font-['JetBrains_Mono',monospace] text-[0.9rem] font-semibold w-fit"
                  :class="
                    metadata.file_exists
                      ? 'text-[var(--accent-primary)]'
                      : 'text-[var(--accent-secondary)]'
                  "
                  style="background: color-mix(in srgb, var(--accent-primary) 15%, transparent)"
                >
                  {{ metadata.file_exists ? '已下载' : '未下载' }}
                </div>
              </div>

              <!-- 标题 -->
              <h1
                class="text-[1.75rem] font-semibold text-[var(--text-primary)] leading-[1.4] mb-6"
              >
                {{ displayedTitle }}
              </h1>

              <!-- 元数据网格 -->
              <div class="grid grid-cols-2 gap-4 mb-8">
                <div v-if="metadata.release_date" class="flex flex-col gap-1">
                  <span class="text-[0.8rem] text-[var(--text-muted)] uppercase tracking-wider"
                    >发行日期</span
                  >
                  <span class="text-base text-[var(--text-primary)]">{{
                    metadata.release_date
                  }}</span>
                </div>
                <div v-if="metadata.duration" class="flex flex-col gap-1">
                  <span class="text-[0.8rem] text-[var(--text-muted)] uppercase tracking-wider"
                    >时长</span
                  >
                  <span class="text-base text-[var(--text-primary)]">{{ metadata.duration }}</span>
                </div>
                <div class="flex flex-col gap-1">
                  <span class="text-[0.8rem] text-[var(--text-muted)] uppercase tracking-wider"
                    >来源</span
                  >
                  <span class="text-base text-[var(--accent-secondary)] font-medium">{{
                    metadata.source
                  }}</span>
                </div>
                <div v-if="fileSize" class="flex flex-col gap-1">
                  <span class="text-[0.8rem] text-[var(--text-muted)] uppercase tracking-wider"
                    >文件大小</span
                  >
                  <span class="text-base text-[var(--text-primary)]">{{ fileSize }}</span>
                </div>
              </div>

              <!-- 操作按钮 -->
              <div
                class="grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-[560px]"
                aria-label="资源操作"
              >
                <ActionMenu
                  :label="refreshing ? '刷新中' : '刷新信息'"
                  :options="refreshOptions"
                  trigger-class="w-full h-14"
                  :disabled="refreshing"
                  @select="handleRefreshOption"
                />

                <AppButton
                  v-if="!metadata.file_exists"
                  tone="coral"
                  class="w-full h-14"
                  :loading="isSubmittingDownload"
                  :disabled="isDownloading"
                  @click="handleDownload"
                >
                  {{ isDownloading ? '下载中...' : '下载视频' }}
                </AppButton>
                <AppButton
                  v-if="metadata.file_exists"
                  tone="coral"
                  class="w-full h-14"
                  @click="openPlayback('local')"
                >
                  <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                  点击播放
                </AppButton>

                <AppButton
                  tone="coral"
                  class="w-full h-14"
                  @click="openPlayback('source')"
                  title="在新标签页播放"
                >
                  <svg
                    class="w-4 h-4 shrink-0"
                    fill="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path d="M8 5v14l11-7z" />
                  </svg>
                  在线播放
                </AppButton>

                <ActionMenu
                  :label="shared ? '移出资源库' : '删除数据'"
                  :options="deleteOptions"
                  trigger-class="w-full h-14"
                  danger
                  align="right"
                  @select="handleDeleteOption"
                />
              </div>
            </div>
          </div>
        </template>
      </PersonalResourcePanel>

      <!-- 详细信息区域 -->
      <div class="flex flex-col gap-8 mt-12">
        <section
          v-if="
            metadata.director ||
            metadata.studio ||
            metadata.label ||
            metadata.actors?.length ||
            metadata.series ||
            metadata.genres?.length
          "
          class="rounded-2xl p-6"
          style="background: var(--bg-overlay); border: 1px solid var(--border-color)"
        >
          <h2
            class="text-[1.1rem] font-semibold text-[var(--text-primary)] mb-5 pb-3"
            style="border-bottom: 1px solid var(--border-color)"
          >
            制作信息
          </h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            <div v-if="metadata.actors?.length" class="flex flex-col gap-1.5">
              <span class="text-[0.8rem] text-[var(--text-muted)]">演员</span>
              <div class="text-[0.95rem] text-[var(--text-primary)] flex flex-wrap gap-2">
                <button
                  v-for="(actor, index) in metadata.actors"
                  :key="index"
                  class="text-[var(--text-primary)] hover:text-[var(--accent-secondary)] cursor-pointer transition-colors duration-200 bg-transparent border-none p-0 font-inherit"
                  @click="navigateToActor(actor)"
                >
                  {{ actor
                  }}<span
                    v-if="index < metadata.actors.length - 1"
                    class="text-[var(--text-muted)] ml-1"
                    >,</span
                  >
                </button>
              </div>
            </div>
            <div v-if="metadata.series" class="flex flex-col gap-1.5">
              <span class="text-[0.8rem] text-[var(--text-muted)]">系列</span>
              <span class="text-[0.95rem] text-[var(--text-primary)]">{{ metadata.series }}</span>
            </div>
            <div v-if="metadata.director" class="flex flex-col gap-1.5">
              <span class="text-[0.8rem] text-[var(--text-muted)]">导演</span>
              <span class="text-[0.95rem] text-[var(--text-primary)]">{{ metadata.director }}</span>
            </div>
            <div v-if="metadata.studio" class="flex flex-col gap-1.5">
              <span class="text-[0.8rem] text-[var(--text-muted)]">制作商</span>
              <span class="text-[0.95rem] text-[var(--text-primary)]">{{ metadata.studio }}</span>
            </div>
            <div v-if="metadata.label" class="flex flex-col gap-1.5">
              <span class="text-[0.8rem] text-[var(--text-muted)]">发行商</span>
              <span class="text-[0.95rem] text-[var(--text-primary)]">{{ metadata.label }}</span>
            </div>
            <div v-if="metadata.genres?.length" class="flex flex-col gap-1.5">
              <span class="text-[0.8rem] text-[var(--text-muted)]">类别</span>
              <div class="text-[0.95rem] text-[var(--text-primary)] flex flex-wrap gap-2">
                <button
                  v-for="(genre, index) in metadata.genres"
                  :key="index"
                  class="text-[var(--text-primary)] hover:text-[var(--accent-secondary)] cursor-pointer transition-colors duration-200 bg-transparent border-none p-0 font-inherit"
                  @click="navigateToGenre(genre)"
                >
                  {{ genre
                  }}<span
                    v-if="index < metadata.genres.length - 1"
                    class="text-[var(--text-muted)] ml-1"
                    >,</span
                  >
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </template>

    <!-- 确认对话框 -->
    <ConfirmDialog
      v-model:show="showConfirmDialog"
      :title="pendingDeleteAction?.title || '确认操作'"
      :message="pendingDeleteAction?.message || ''"
      :type="'danger'"
      :confirm-text="shared ? '确认移出' : '确认删除'"
      cancel-text="取消"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />
  </div>
</template>

<style scoped>
/* 自定义动画 */
@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}
</style>

<style scoped>
.detail-cover-actions {
  width: min-content;
}
.detail-cover {
  width: max-content;
  max-width: 100%;
}
.detail-cover :deep(img) {
  max-height: 310px;
  max-width: min(400px, 100%);
  width: auto;
  height: auto;
}
.detail-cover :deep([role='img']) {
  width: 100%;
  min-width: 12rem;
  height: 225px;
}
@media (max-width: 640px) {
  .detail-cover :deep(img) {
    max-width: calc(100vw - 4rem);
  }
}
</style>
