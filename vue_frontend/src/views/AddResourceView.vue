<script setup>
import CookieManagementDialog from '../features/cookies/components/CookieManagementDialog.vue'
import AppButton from '../shared/ui/AppButton.vue'
import AppIcon from '../shared/ui/AppIcon.vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useResourceStore } from '../features/resources/stores/resource.js'
import { useToastStore } from '../shared/stores/toast.js'
import { useSettingsStore } from '../features/settings/stores/settings.js'
import { resourceApi } from '../api/index.js'
import { useResourceSubmission } from '../features/resources/composables/useResourceSubmission.js'
import SubmissionResults from '../features/resources/components/SubmissionResults.vue'
import CustomSelect from '../shared/ui/CustomSelect.vue'
import AppInput from '../shared/ui/AppInput.vue'

const router = useRouter()
const resourceStore = useResourceStore()
const toastStore = useToastStore()
const settingsStore = useSettingsStore()

const showCookies = ref(false)
const {
  avid,
  source,
  submitting,
  result,
  sourceOptions,
  parseAvids,
  handleSubmit,
  validationError,
} = useResourceSubmission({ resourceStore, resourceApi, toastStore })

function viewResource() {
  if (result.value?.data?.avid) {
    router.push(`/resource/${result.value.data.avid}`)
  } else if (result.value?.success?.length === 1) {
    // 如果只有一个成功的AVID，跳转到详情页
    router.push(`/resource/${result.value.success[0]}`)
  }
}
</script>

<template>
  <div class="add-view">
    <div class="page-header">
      <h1 class="page-title">添加资源</h1>
      <p class="page-subtitle">支持单个或批量输入视频编号（换行、逗号、空格分隔）</p>
    </div>

    <CookieManagementDialog v-if="showCookies" @close="showCookies = false" />
    <div class="add-form-card">
      <form class="add-form" @submit.prevent="handleSubmit">
        <div class="form-group">
          <label for="add-avids" class="form-label">
            视频编号 (AVID)
            <span v-if="parseAvids().length > 0" class="count-badge">
              已识别 {{ parseAvids().length }} 个
            </span>
          </label>
          <AppInput
            id="add-avids"
            multiline
            :model-value="avid"
            :error="validationError"
            aria-describedby="add-avids-hint"
            placeholder="输入视频编号，如 SNOS-317；多个编号用换行、逗号或空格分隔"
            :disabled="submitting"
            rows="5"
            @update:model-value="avid = $event.toUpperCase()"
          />
          <p id="add-avids-hint" class="form-hint">支持换行、逗号、空格分隔，自动去重</p>
        </div>

        <div class="form-group">
          <label for="add-source" class="form-label">下载源</label>
          <CustomSelect
            id="add-source"
            aria-label="下载源"
            aria-describedby="add-source-hint"
            v-model="source"
            :options="sourceOptions"
            :disabled="submitting"
            class="form-select"
            full-width
          />
          <p id="add-source-hint" class="form-hint">选择自动将依次尝试所有可用源</p>
        </div>

        <div class="flex items-stretch gap-3">
          <AppButton
            type="submit"
            class="flex-1 min-w-0 text-lg flex items-center justify-center gap-2 rounded-lg px-6 py-4"
            :loading="submitting"
            loading-text="提交中"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke-width="2" />
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12 8v8M8 12h8"
              />
            </svg>
            {{ parseAvids().length > 1 ? `批量添加 (${parseAvids().length})` : '添加资源' }}
          </AppButton>
          <AppButton
            variant="neutral"
            class="rounded-lg px-4 shrink-0"
            aria-label="Cookie 设置"
            title="Cookie 设置"
            @click="showCookies = true"
            ><AppIcon name="cookie"
          /></AppButton>
        </div>
      </form>
    </div>

    <SubmissionResults
      :result="result"
      :preferred-title="settingsStore.displayTitle"
      @view="viewResource"
    />

    <div class="tips-section">
      <h2 class="tips-title">使用提示</h2>
      <ul class="tips-list">
        <li>封面图片和元数据会自动保存到本地</li>
        <li>添加成功后，可以在资源详情页提交下载任务</li>
      </ul>
    </div>
  </div>
</template>

<style src="../features/resources/styles/resourceSubmission.css"></style>
