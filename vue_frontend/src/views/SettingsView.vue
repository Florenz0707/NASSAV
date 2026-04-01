<script setup>
import { computed, ref, onMounted } from 'vue'
import { sourceApi } from '../api'
import { useToastStore } from '../stores/toast'
import { useSettingsStore } from '../stores/settings'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { AVAILABLE_FONTS } from '../config/fonts'
import SettingsSidebarMenu from '../components/settings/SettingsSidebarMenu.vue'
import SettingsModal from '../components/settings/SettingsModal.vue'
import CookieManagementPanel from '../components/settings/CookieManagementPanel.vue'
import GeneralSettingsPanel from '../components/settings/GeneralSettingsPanel.vue'

const toastStore = useToastStore()
const settingsStore = useSettingsStore()

// 当前选中的设置菜单项
const activeMenu = ref('general')

// 字体预览（临时变量，用于预览效果）
const previewFont = ref('Mplus2')
const displayTitleOptions = [
  { value: 'translated_title', label: '翻译标题' },
  { value: 'source_title', label: '源站标题' },
  { value: 'original_title', label: '原始标题' },
]
const searchResultDisplayOptions = [
  { value: 'grid', label: '标准网格' },
  { value: 'masonry', label: '两列瀑布流' },
]

// 设置菜单项
const menuItems = [
  { id: 'general', name: '通用设置', icon: '⚙️' },
  { id: 'cookies', name: 'Cookie 管理', icon: '🍪' },
]

// 下载源列表数据
const sources = ref([])
const loading = ref(true)

// 弹窗状态
const showViewModal = ref(false)
const showEditModal = ref(false)
const showDeleteConfirm = ref(false)
const currentSource = ref(null)
const editCookieValue = ref('')
const viewCookieValue = ref('')

// 选择菜单项
const selectMenu = (menuId) => {
  activeMenu.value = menuId
}

// 格式化时间
const formatTime = (isoString) => {
  if (!isoString) return null
  try {
    const date = new Date(isoString)
    return date
      .toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })
      .replace(/\//g, '-')
  } catch (_e) {
    return isoString
  }
}

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    // 1. 获取所有可用源列表
    const sourcesResponse = await sourceApi.getList()
    const availableSources = sourcesResponse.data || []

    // 2. 获取已设置的 Cookie 列表
    const cookiesResponse = await sourceApi.getCookies()
    const cookieData = cookiesResponse.data || []

    // 3. 构建 Cookie 映射表（source -> cookie info）
    // 使用小写作为 key 以支持大小写不敏感匹配
    const cookieMap = {}
    cookieData.forEach((item) => {
      cookieMap[item.source.toLowerCase()] = {
        cookie: item.cookie,
        mtime: item.mtime,
      }
    })

    // 4. 合并数据
    sources.value = availableSources.map((sourceName) => {
      const cookieInfo = cookieMap[sourceName.toLowerCase()]
      return {
        name: sourceName,
        hasCookie: !!cookieInfo,
        lastUpdate: cookieInfo ? formatTime(cookieInfo.mtime) : null,
        cookie: cookieInfo ? cookieInfo.cookie : null,
      }
    })
  } catch (err) {
    console.error('加载 Cookie 数据失败:', err)
    toastStore.error(err.message || '加载数据失败')
  } finally {
    loading.value = false
  }
}

// 查看 Cookie
const viewCookie = (source) => {
  currentSource.value = source
  viewCookieValue.value = source.cookie || ''
  showViewModal.value = true
}

// 打开编辑弹窗
const openEditModal = (source) => {
  currentSource.value = source
  editCookieValue.value = source.cookie || ''
  showEditModal.value = true
}

// 保存 Cookie
const saveCookie = async () => {
  if (!currentSource.value) return
  try {
    await sourceApi.setCookie({
      source: currentSource.value.name,
      cookie: editCookieValue.value,
    })
    toastStore.success('Cookie 设置成功')
    showEditModal.value = false
    loadData()
  } catch (err) {
    toastStore.error(err.message || '设置失败')
  }
}

// 自动获取 Cookie
const autoFetchCookie = async (source) => {
  const targetSource = source || currentSource.value
  if (!targetSource) return

  try {
    await sourceApi.setCookie({
      source: targetSource.name,
      auto: true,
    })
    toastStore.success('已触发自动获取 Cookie')
    showEditModal.value = false
    loadData()
  } catch (err) {
    toastStore.error(err.message || '自动获取失败')
  }
}

// 确认删除
const confirmDelete = (source) => {
  currentSource.value = source
  showDeleteConfirm.value = true
}

// 执行删除
const handleDelete = async () => {
  if (!currentSource.value) return
  try {
    await sourceApi.deleteCookie(currentSource.value.name)
    toastStore.success('Cookie 已清除')
    loadData()
  } catch (err) {
    toastStore.error(err.message || '清除失败')
  }
}

// 保存设置
const handleSaveSettings = async () => {
  try {
    // 应用预览字体到全局设置
    settingsStore.fontFamily = previewFont.value
    await settingsStore.saveSettings()
    toastStore.success('设置已保存')
  } catch (err) {
    toastStore.error(err.message || '保存设置失败')
  }
}

// 组件挂载时加载数据
onMounted(async () => {
  loadData()
  await settingsStore.loadSettings()
  // 初始化预览字体为当前设置
  previewFont.value = settingsStore.fontFamily
})

const cookieTextareaStyle = computed(() => {
  if (settingsStore.colorMode === 'light') {
    return {
      background: 'rgba(255, 255, 255, 0.96)',
      border: '1px solid rgba(15, 23, 42, 0.12)',
      color: '#1f2937',
    }
  }
  return {
    background: 'rgba(0, 0, 0, 0.4)',
    border: '1px solid var(--border-color)',
    color: 'var(--text-primary)',
  }
})
</script>

<template>
  <div class="settings-page">
    <!-- Header -->
    <div class="mb-8">
      <h1 class="text-[2rem] font-bold text-[var(--text-primary)] mb-2">系统设置</h1>
      <p class="text-[var(--text-muted)] text-base">配置系统参数和管理 Cookie</p>
    </div>

    <!-- Main Content: Left Menu + Right Panel -->
    <div class="flex gap-6">
      <!-- Left Sidebar Menu -->
      <div class="w-64 flex-shrink-0">
        <SettingsSidebarMenu :items="menuItems" :active-id="activeMenu" @select="selectMenu" />
      </div>

      <!-- Right Content Panel -->
      <div class="flex-1">
        <div class="tw-surface-overlay rounded-xl p-6">
          <!-- Cookie 管理面板 -->
          <CookieManagementPanel
            v-if="activeMenu === 'cookies'"
            :loading="loading"
            :sources="sources"
            @view="viewCookie"
            @edit="openEditModal"
            @delete="confirmDelete"
          />

          <!-- 通用设置面板 -->
          <GeneralSettingsPanel
            v-else-if="activeMenu === 'general'"
            :settings="settingsStore"
            :preview-font="previewFont"
            :display-title-options="displayTitleOptions"
            :search-result-display-options="searchResultDisplayOptions"
            :available-fonts="AVAILABLE_FONTS"
            @update:preview-font="previewFont = $event"
            @save="handleSaveSettings"
          />
        </div>
      </div>
    </div>

    <!-- 查看 Cookie 弹窗 -->
    <SettingsModal
      :show="showViewModal"
      :title="`查看 Cookie - ${currentSource?.name || ''}`"
      @close="showViewModal = false"
    >
      <div
        class="bg-black/40 rounded-xl p-4 font-mono text-sm text-[var(--text-muted)] break-all max-h-[400px] overflow-y-auto border border-white/5"
      >
        {{ viewCookieValue || '无内容' }}
      </div>

      <template #footer>
        <div class="flex justify-end">
          <button class="tw-btn-muted" @click="showViewModal = false">关闭</button>
        </div>
      </template>
    </SettingsModal>

    <!-- 编辑 Cookie 弹窗 -->
    <SettingsModal
      :show="showEditModal"
      :title="`设置 Cookie - ${currentSource?.name || ''}`"
      @close="showEditModal = false"
    >
      <p class="text-sm text-[var(--text-muted)] mb-4">
        请输入从浏览器获取的 Cookie 字符串。通常包含 PHPSESSID 等字段。
      </p>
      <textarea
        v-model="editCookieValue"
        class="w-full h-48 rounded-xl p-4 font-mono text-sm focus:outline-none transition-all resize-none"
        :style="cookieTextareaStyle"
        placeholder="粘贴 Cookie 字符串到这里..."
      />

      <template #footer>
        <div class="flex justify-between items-center">
          <button
            class="px-4 py-2 rounded-xl bg-white/5 text-[var(--text-muted)] text-sm border border-white/[0.08] hover:bg-white/10 hover:text-[var(--text-primary)] transition-all"
            @click="autoFetchCookie()"
          >
            ✨ 自动获取
          </button>
          <div class="flex gap-3">
            <button class="tw-btn-muted" @click="showEditModal = false">取消</button>
            <button class="tw-btn-settings-primary" @click="saveCookie">保存设置</button>
          </div>
        </div>
      </template>
    </SettingsModal>

    <!-- 删除确认 -->
    <ConfirmDialog
      v-model:show="showDeleteConfirm"
      title="清除 Cookie"
      :message="`确定要清除 ${currentSource?.name} 的 Cookie 吗？清除后可能无法正常访问该源。`"
      confirm-text="确定清除"
      type="danger"
      @confirm="handleDelete"
    />
  </div>
</template>

<style scoped>
.settings-page {
  animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 响应式布局 */
@media (max-width: 768px) {
  .flex {
    flex-direction: column;
  }

  .w-64 {
    width: 100%;
  }
}
</style>
