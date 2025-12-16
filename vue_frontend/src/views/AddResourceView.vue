<script setup>
import {ref, onMounted} from 'vue'
import {useRouter} from 'vue-router'
import {useResourceStore} from '../stores/resource'
import {useToastStore} from '../stores/toast'
import LoadingSpinner from '../components/LoadingSpinner.vue'

const router = useRouter()
const resourceStore = useResourceStore()
const toastStore = useToastStore()

const avid = ref('')
const source = ref('any')
const submitting = ref(false)
const result = ref(null)

onMounted(async () => {
  await resourceStore.fetchSources()
})

async function handleSubmit() {
  if (!avid.value.trim()) {
    toastStore.warning('请输入视频编号')
    return
  }

  submitting.value = true
  result.value = null

  try {
    const response = await resourceStore.addResource(avid.value.trim().toUpperCase(), source.value)
    result.value = {
      success: true,
      data: response.data
    }
    toastStore.success(`${avid.value} 添加成功`)
  } catch (err) {
    if (err.code === 409) {
      result.value = {
        success: false,
        exists: true,
        data: err.data
      }
      toastStore.info('资源已存在')
    } else {
      result.value = {
        success: false,
        message: err.message
      }
      toastStore.error(err.message || '添加失败')
    }
  } finally {
    submitting.value = false
  }
}

function viewResource() {
  if (result.value?.data?.avid) {
    router.push(`/resource/${result.value.data.avid}`)
  }
}

function addAnother() {
  avid.value = ''
  source.value = 'any'
  result.value = null
}
</script>

<template>
  <div class="add-view">
    <div class="page-header">
      <h1 class="page-title">添加资源</h1>
      <p class="page-subtitle">输入视频编号，系统将自动获取信息并下载封面</p>
    </div>

    <div class="add-form-card">
      <form @submit.prevent="handleSubmit" class="add-form">
        <div class="form-group">
          <label class="form-label">视频编号 (AVID)</label>
          <input
              v-model="avid"
              type="text"
              placeholder="例如: SSIS-469"
              class="form-input"
              :disabled="submitting"
              @input="avid = avid.toUpperCase()"
          />
          <p class="form-hint">支持多种格式，如 SSIS-469、ABP-123 等</p>
        </div>

        <div class="form-group">
          <label class="form-label">下载源</label>
          <select v-model="source" class="form-select" :disabled="submitting">
            <option value="any">自动选择 (遍历所有源)</option>
            <option v-for="s in resourceStore.sources" :key="s" :value="s.toLowerCase()">
              {{ s }}
            </option>
          </select>
          <p class="form-hint">选择自动将依次尝试所有可用源</p>
        </div>

        <button
            type="submit"
            class="btn btn-primary btn-large btn-full"
            :disabled="submitting || !avid.trim()"
        >
          <LoadingSpinner v-if="submitting" size="small"/>
          <template v-else>
            <span class="btn-icon">⊕</span>
            添加资源
          </template>
        </button>
      </form>
    </div>

    <Transition name="result">
      <div v-if="result" class="result-card" :class="{ success: result.success, exists: result.exists }">
        <div class="result-header">
          <div class="result-icon">{{ result.success ? '✓' : result.exists ? 'ℹ' : '✕' }}</div>
          <h3 class="result-title">
            {{ result.success ? '添加成功' : result.exists ? '资源已存在' : '添加失败' }}
          </h3>
        </div>

        <div v-if="result.data" class="result-details">
          <div class="result-item">
            <span class="result-label">编号</span>
            <span class="result-value avid">{{ result.data.avid }}</span>
          </div>
          <div class="result-item" v-if="result.data.title">
            <span class="result-label">标题</span>
            <span class="result-value">{{ result.data.title }}</span>
          </div>
          <div class="result-item" v-if="result.data.source">
            <span class="result-label">来源</span>
            <span class="result-value source">{{ result.data.source }}</span>
          </div>
          <div class="result-checks" v-if="result.success || result.exists">
            <div class="check-item" :class="{ done: result.data.cover_downloaded }">
              <span class="check-icon">{{ result.data.cover_downloaded ? '✓' : '○' }}</span>
              封面下载
            </div>
            <div class="check-item" :class="{ done: result.data.metadata_saved }">
              <span class="check-icon">{{ result.data.metadata_saved ? '✓' : '○' }}</span>
              元数据保存
            </div>
            <div class="check-item" :class="{ done: result.data.scraped }">
              <span class="check-icon">{{ result.data.scraped ? '✓' : '○' }}</span>
              信息刮削
            </div>
          </div>
        </div>

        <p v-else-if="result.message" class="result-message">{{ result.message }}</p>

        <div class="result-actions">
          <button class="btn btn-primary" @click="viewResource" v-if="result.data">
            查看详情
          </button>
          <button class="btn btn-secondary" @click="addAnother">
            继续添加
          </button>
        </div>
      </div>
    </Transition>

    <div class="tips-section">
      <h3 class="tips-title">使用提示</h3>
      <ul class="tips-list">
        <li>系统会自动从选定的下载源获取视频信息</li>
        <li>封面图片和元数据会自动保存到本地</li>
        <li>添加成功后，可以在资源详情页提交下载任务</li>
        <li>如果指定源无法获取，可尝试选择"自动选择"</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.add-view {
  max-width: 640px;
  margin: 0 auto;
  animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.page-header {
  text-align: center;
  margin-bottom: 2.5rem;
}

.page-title {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.page-subtitle {
  color: var(--text-muted);
  font-size: 1rem;
}

.add-form-card {
  background: var(--card-bg);
  border-radius: 20px;
  border: 1px solid var(--border-color);
  padding: 2rem;
  margin-bottom: 2rem;
}

.add-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-label {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary);
}

.form-input,
.form-select {
  padding: 1rem 1.25rem;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  color: var(--text-primary);
  font-size: 1rem;
  transition: all 0.2s ease;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.1);
}

.form-input::placeholder {
  color: var(--text-muted);
}

.form-select {
  cursor: pointer;
}

.form-select option {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-hint {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.875rem 1.5rem;
  border: none;
  border-radius: 12px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-large {
  padding: 1.1rem 2rem;
  font-size: 1.05rem;
}

.btn-full {
  width: 100%;
}

.btn-primary {
  background: linear-gradient(135deg, var(--accent-primary), #ff5252);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(255, 107, 107, 0.3);
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.12);
}

.btn-icon {
  font-size: 1.2rem;
}

.result-card {
  background: var(--card-bg);
  border-radius: 20px;
  border: 1px solid var(--border-color);
  padding: 2rem;
  margin-bottom: 2rem;
}

.result-card.success {
  border-color: rgba(46, 213, 115, 0.3);
}

.result-card.exists {
  border-color: rgba(78, 205, 196, 0.3);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.result-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  background: rgba(255, 107, 107, 0.15);
  color: var(--accent-primary);
}

.result-card.success .result-icon {
  background: rgba(46, 213, 115, 0.15);
  color: #2ed573;
}

.result-card.exists .result-icon {
  background: rgba(78, 205, 196, 0.15);
  color: var(--accent-tertiary);
}

.result-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.result-details {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.result-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.result-label {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.result-value {
  font-size: 1rem;
  color: var(--text-primary);
}

.result-value.avid {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: var(--accent-primary);
}

.result-value.source {
  color: var(--accent-secondary);
}

.result-checks {
  display: flex;
  gap: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}

.check-item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  color: var(--text-muted);
}

.check-item.done {
  color: #2ed573;
}

.check-icon {
  font-size: 0.9rem;
}

.result-message {
  color: var(--text-muted);
  margin-bottom: 1.5rem;
}

.result-actions {
  display: flex;
  gap: 1rem;
}

.result-enter-active {
  animation: slideUp 0.4s ease;
}

.result-leave-active {
  animation: slideUp 0.3s ease reverse;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.tips-section {
  background: rgba(78, 205, 196, 0.05);
  border: 1px solid rgba(78, 205, 196, 0.1);
  border-radius: 16px;
  padding: 1.5rem;
}

.tips-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--accent-tertiary);
  margin-bottom: 1rem;
}

.tips-list {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tips-list li {
  font-size: 0.9rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.tips-list li::marker {
  color: var(--accent-tertiary);
}
</style>
