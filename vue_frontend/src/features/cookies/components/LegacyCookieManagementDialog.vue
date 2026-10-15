<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { sourceApi } from '../../../api/index.js'
import { useToastStore } from '../../../shared/stores/toast.js'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import CookieManagementPanel from './CookieManagementPanel.vue'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import AppInput from '../../../shared/ui/AppInput.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
const emit = defineEmits(['close'])
const toastStore = useToastStore()
const sources = ref([])
const loading = ref(true)
const loadError = ref('')
let disposed = false
onBeforeUnmount(() => {
  disposed = true
})
// 弹窗状态
const showViewModal = ref(false)
const showEditModal = ref(false)
const showDeleteConfirm = ref(false)
const currentSource = ref(null)
const editCookieValue = ref('')
const cookieError = ref(''),
  savingCookie = ref(false)
watch(editCookieValue, () => {
  cookieError.value = ''
})
const editUserAgentValue = ref('')
const viewCookieValue = ref('')

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
  loadError.value = ''
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
        verifiedDirectReuse: item.verified_direct_reuse,
        sessionExpired: item.session_expired,
      }
    })

    // 4. 合并数据
    if (disposed) return
    sources.value = availableSources.map((sourceName) => {
      const cookieInfo = cookieMap[sourceName.toLowerCase()]
      return {
        name: sourceName,
        hasCookie: !!cookieInfo,
        lastUpdate: cookieInfo ? formatTime(cookieInfo.mtime) : null,
        cookie: cookieInfo ? cookieInfo.cookie : null,
        verifiedDirectReuse: cookieInfo ? cookieInfo.verifiedDirectReuse : false,
        sessionExpired: cookieInfo ? cookieInfo.sessionExpired : false,
      }
    })
  } catch (err) {
    if (disposed) return
    loadError.value = err.message || '加载数据失败'
    toastStore.error(loadError.value)
  } finally {
    if (!disposed) loading.value = false
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
  editUserAgentValue.value = ''
  showEditModal.value = true
}

// 保存 Cookie
const saveCookie = async () => {
  if (!currentSource.value || savingCookie.value) return
  savingCookie.value = true
  cookieError.value = ''
  try {
    await sourceApi.setCookie({
      source: currentSource.value.name,
      cookie: editCookieValue.value,
      user_agent: editUserAgentValue.value || null,
    })
    toastStore.success('Cookie 设置成功')
    showEditModal.value = false
    if (!disposed) loadData()
  } catch (err) {
    cookieError.value = err.message || '设置失败'
    toastStore.error(cookieError.value)
  } finally {
    savingCookie.value = false
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
    if (!disposed) loadData()
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
    if (!disposed) loadData()
  } catch (err) {
    toastStore.error(err.message || '清除失败')
  }
}

const copyCookie = async () => {
  const text = viewCookieValue.value || ''
  if (!text) {
    toastStore.warning('暂无可复制内容')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    toastStore.success('Cookie 已复制到剪贴板')
  } catch (_error) {
    try {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.focus()
      textarea.select()
      const copied = document.execCommand('copy')
      document.body.removeChild(textarea)
      if (copied) toastStore.success('Cookie 已复制到剪贴板')
      else toastStore.error('复制失败，请手动复制')
    } catch (__error) {
      toastStore.error('复制失败，请手动复制')
    }
  }
}

onMounted(loadData)
</script>
<template>
  <SettingsModal :show="true" title="Cookie 设置" @close="emit('close')">
    <RequestError v-if="loadError" :message="loadError" compact @retry="loadData" />
    <CookieManagementPanel
      v-if="loading || !loadError || sources.length"
      :loading="loading"
      :sources="sources"
      @view="viewCookie"
      @edit="openEditModal"
      @delete="confirmDelete"
    />
  </SettingsModal>
  <!-- 查看 Cookie 弹窗 -->
  <SettingsModal
    :show="showViewModal"
    :title="`查看 Cookie - ${currentSource?.name || ''}`"
    @close="showViewModal = false"
  >
    <div
      class="bg-secondary rounded-xl p-4 font-mono text-sm text-primary break-all max-h-[400px] overflow-y-auto border border-[var(--border-color)]"
    >
      {{ viewCookieValue || '无内容' }}
    </div>

    <template #footer>
      <div class="flex items-center justify-between">
        <AppButton variant="neutral" @click="copyCookie">复制</AppButton>
        <AppButton variant="neutral" @click="showViewModal = false">关闭</AppButton>
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
    <AppInput
      v-model="editCookieValue"
      multiline
      :rows="7"
      class="font-mono text-sm"
      aria-label="Cookie 字符串"
      :error="cookieError"
      :disabled="savingCookie"
      placeholder="粘贴浏览器中的 Cookie 字符串"
    />

    <label for="cookie-user-agent" class="block text-sm text-[var(--text-secondary)] mt-4 mb-2">
      User-Agent（可选）
    </label>
    <AppInput
      id="cookie-user-agent"
      v-model="editUserAgentValue"
      :disabled="savingCookie"
      placeholder="粘贴与 Cookie 配套的浏览器 User-Agent"
    />
    <p class="text-xs text-[var(--text-muted)] mt-2">
      留空保存会清除以前的配套 UA；手动输入不代表已验证可直连。
    </p>

    <template #footer>
      <div class="flex justify-between items-center">
        <AppButton variant="neutral" @click="autoFetchCookie()"> 自动获取 </AppButton>
        <AppButton :loading="savingCookie" loading-text="保存中" @click="saveCookie"
          >保存</AppButton
        >
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
</template>
