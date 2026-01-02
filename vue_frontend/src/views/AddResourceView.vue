<script setup>
import {onMounted, ref} from 'vue'
import {useRouter} from 'vue-router'
import {useResourceStore} from '../stores/resource'
import {useToastStore} from '../stores/toast'
import {resourceApi, sourceApi} from '../api'
import LoadingSpinner from '../components/LoadingSpinner.vue'

const router = useRouter()
const resourceStore = useResourceStore()
const toastStore = useToastStore()

const avid = ref('')
const source = ref('any')
const submitting = ref(false)
const result = ref(null)
const showCookieModal = ref(false)
const cookieForm = ref({
	source: '',
	cookie: ''
})
const savingCookie = ref(false)

onMounted(async () => {
	await resourceStore.fetchSources()
})

// 解析输入的 AVID 列表
function parseAvids() {
	return avid.value
		.split(/[\n,\s]+/)           // 按换行、逗号、空格分割
		.map(s => s.trim().toUpperCase())
		.filter(s => s.length > 0)   // 过滤空字符串
		.filter((v, i, arr) => arr.indexOf(v) === i)  // 去重
}

async function handleSubmit() {
	const avids = parseAvids()
	if (avids.length === 0) {
		toastStore.warning('请输入视频编号')
		return
	}

	submitting.value = true
	result.value = null

	try {
		if (avids.length === 1) {
			// 单个添加
			const response = await resourceStore.addResource(avids[0], source.value)
			let data = response && response.data ? response.data : null
			if (data && data.resource) data = data.resource

			try {
				if (data && data.avid) {
					const metaResp = await resourceApi.getMetadata(data.avid)
					if (metaResp && metaResp.data) {
						data = Object.assign({}, data, metaResp.data)
					}
				}
			} catch (e) {}

			result.value = {
				success: [avids[0]],
				exists: [],
				failed: [],
				total: 1,
				data
			}
			toastStore.success(`${avids[0]} 添加成功`)
		} else {
			// 批量添加 - 根据接口文档构建actions数组
			const actions = avids.map(avid => ({
				action: 'add',
				avid: avid,
				source: source.value
			}))

			const response = await resourceApi.batch({
				actions: actions
			})

			const data = response?.data || {}
			const results = data.results || []

			// 解析批量结果
			const success = []
			const exists = []
			const failed = []

			results.forEach(result => {
				// 根据后端接口规范判断结果
				if (result.code === 200 && result.message === 'already exists') {
					// add 操作：资源已存在
					exists.push(result.avid)
				} else if (result.code === 201 || (result.code === 200 && (result.message === 'refreshed' || result.message === 'deleted'))) {
					// 201: 创建成功
					// 200 + refreshed/deleted: 刷新/删除成功
					success.push(result.avid)
				} else if (result.code === 404 || result.code >= 400) {
					// 404 或其他错误码：操作失败
					failed.push(result.avid)
				} else {
					// 其他 2xx 状态码视为成功
					success.push(result.avid)
				}
			})

			result.value = {
				success,
				exists,
				failed,
				total: avids.length
			}

			const successCount = success.length
			const existsCount = exists.length
			const failedCount = failed.length

			if (successCount > 0) {
				toastStore.success(`成功添加 ${successCount} 个资源`)
			}
			if (existsCount > 0) {
				toastStore.info(`${existsCount} 个资源已存在`)
			}
			if (failedCount > 0) {
				toastStore.warning(`${failedCount} 个资源添加失败`)
			}
		}
	} catch (err) {
		if (err.code === 409) {
			result.value = {
				success: [],
				exists: [avids[0]],
				failed: [],
				total: 1,
				data: (err && err.data && err.data.resource) ? err.data.resource : err.data
			}
			toastStore.info('资源已存在')
		} else {
			result.value = {
				success: [],
				exists: [],
				failed: avids,
				total: avids.length
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
	} else if (result.value?.success?.length === 1) {
		// 如果只有一个成功的AVID，跳转到详情页
		router.push(`/resource/${result.value.success[0]}`)
	}
}

function addAnother() {
	avid.value = ''
	source.value = 'any'
	result.value = null
}

function openCookieModal() {
	cookieForm.value = {
		source: resourceStore.sources[0] || '',
		cookie: ''
	}
	showCookieModal.value = true
}

function closeCookieModal() {
	showCookieModal.value = false
	cookieForm.value = {source: '', cookie: ''}
}

async function saveCookie() {
	if (!cookieForm.value.source || !cookieForm.value.cookie.trim()) {
		toastStore.warning('请填写完整信息')
		return
	}

	savingCookie.value = true
	try {
		const resp = await sourceApi.setCookie({source: cookieForm.value.source, cookie: cookieForm.value.cookie})
		const isSuccessCode = resp && (resp.code === 0 || (typeof resp.code === 'number' && resp.code >= 200 && resp.code < 300))
		if (isSuccessCode) {
			toastStore.success(`${cookieForm.value.source} Cookie 已保存`)
			closeCookieModal()
		} else {
			toastStore.error((resp && resp.message) || '保存失败')
		}
	} catch (err) {
		if (err && err.httpStatus) {
			toastStore.error(err.message || `HTTP ${err.httpStatus}`)
		} else if (err && err.name === 'TypeError' && err.message.includes('fetch')) {
			toastStore.error('网络连接失败，请检查服务器状态')
		} else {
			toastStore.error(err.message || '保存失败')
		}
	} finally {
		savingCookie.value = false
	}
}
</script>

<template>
	<div class="add-view">
		<div class="page-header">
			<h1 class="page-title">添加资源</h1>
			<p class="page-subtitle">支持单个或批量输入视频编号（换行、逗号、空格分隔）</p>
		</div>

		<div class="add-form-card">
			<form @submit.prevent="handleSubmit" class="add-form">
				<div class="form-group">
					<label class="form-label">
						视频编号 (AVID)
						<span v-if="parseAvids().length > 0" class="count-badge">
							已识别 {{ parseAvids().length }} 个
						</span>
					</label>
					<textarea
						v-model="avid"
						placeholder="支持多种格式：&#10;单个: SSIS-469&#10;多个: ABC-001, DEF-002&#10;或换行/空格分隔"
						class="form-textarea"
						:disabled="submitting"
						rows="5"
						@input="avid = avid.toUpperCase()"
					></textarea>
					<p class="form-hint">支持换行、逗号、空格分隔，自动去重</p>
				</div>

				<div class="form-group">
					<label class="form-label">下载源</label>
					<select v-model="source" class="form-select" :disabled="submitting">
						<option value="any">自动</option>
						<option v-for="s in resourceStore.sources" :key="s" :value="s.toLowerCase()">
							{{ s }}
						</option>
					</select>
					<p class="form-hint">选择自动将依次尝试所有可用源</p>
				</div>

				<button
					type="submit"
					class="btn btn-primary btn-large btn-full"
					:disabled="submitting || parseAvids().length === 0"
				>
					<LoadingSpinner v-if="submitting" size="small"/>
					<template v-else>
						<span class="btn-icon">⊕</span>
						{{ parseAvids().length > 1 ? `批量添加 (${parseAvids().length})` : '添加资源' }}
					</template>
				</button>
			</form>
		</div>

		<!-- 添加结果 -->
		<Transition name="result">
			<div v-if="result && result.total === 1 && result.data" class="result-card" :class="{ success: result.success.length > 0, exists: result.exists.length > 0 }">
				<div class="result-header">
					<div class="result-icon">{{ result.success.length > 0 ? '✓' : result.exists.length > 0 ? 'ℹ' : '✕' }}</div>
					<h3 class="result-title">
						{{ result.success.length > 0 ? '添加成功' : result.exists.length > 0 ? '资源已存在' : '添加失败' }}
					</h3>
				</div>

				<div class="result-details">
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
					<div class="result-checks" v-if="result.success.length > 0 || result.exists.length > 0">
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

				<div class="result-actions">
					<button class="btn btn-primary" @click="viewResource">
						查看详情
					</button>
					<button class="btn btn-secondary" @click="addAnother">
						继续添加
					</button>
				</div>
			</div>
		</Transition>

		<!-- 批量添加结果 -->
		<Transition name="result">
			<div v-if="result && (result.total > 1 || !result.data)" class="batch-result-card">
				<div class="batch-result-header">
					<h3 class="batch-result-title">
						{{ result.total > 1 ? '批量添加完成' : '添加完成' }}
					</h3>
					<div class="batch-result-stats">
						<div class="stat-item success">
							<span class="stat-icon">✓</span>
							<span class="stat-label">成功</span>
							<span class="stat-value">{{ result.success.length }}</span>
						</div>
						<div class="stat-item exists">
							<span class="stat-icon">ℹ</span>
							<span class="stat-label">已存在</span>
							<span class="stat-value">{{ result.exists.length }}</span>
						</div>
						<div class="stat-item failed">
							<span class="stat-icon">✕</span>
							<span class="stat-label">失败</span>
							<span class="stat-value">{{ result.failed.length }}</span>
						</div>
					</div>
				</div>

				<div class="batch-result-details">
					<div v-if="result.success.length > 0" class="result-group">
						<h4 class="result-group-title success">✓ 成功添加 ({{ result.success.length }})</h4>
						<div class="result-group-list">
							<span v-for="avid in result.success" :key="avid" class="result-tag success">{{ avid }}</span>
						</div>
					</div>

					<div v-if="result.exists.length > 0" class="result-group">
						<h4 class="result-group-title exists">ℹ 已存在 ({{ result.exists.length }})</h4>
						<div class="result-group-list">
							<span v-for="avid in result.exists" :key="avid" class="result-tag exists">{{ avid }}</span>
						</div>
					</div>

					<div v-if="result.failed.length > 0" class="result-group">
						<h4 class="result-group-title failed">✕ 添加失败 ({{ result.failed.length }})</h4>
						<div class="result-group-list">
							<span v-for="avid in result.failed" :key="avid" class="result-tag failed">{{ avid }}</span>
						</div>
					</div>
				</div>

				<div class="result-actions">
					<button class="btn btn-primary" @click="viewResource" v-if="result.success.length === 1">
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
				<li>支持单个或批量输入，系统自动识别</li>
				<li>批量添加支持换行、逗号、空格分隔</li>
				<li>封面图片和元数据会自动保存到本地</li>
				<li>添加成功后，可以在资源详情页提交下载任务</li>
				<li>如果指定源无法获取，可尝试选择"自动选择"</li>
			</ul>
		</div>

		<div class="cookie-section">
			<button class="btn btn-secondary btn-cookie" @click="openCookieModal">
				<span class="btn-icon">🍪</span>
				Cookie 设置
			</button>
			<p class="cookie-hint">某些源可能需要设置 Cookie 才能正常访问</p>
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

/* 模式切换按钮 */
.mode-switch {
	display: flex;
	gap: 1rem;
	margin-bottom: 2rem;
	justify-content: center;
}

.mode-btn {
	flex: 1;
	max-width: 200px;
	display: flex;
	align-items: center;
	justify-content: center;
	gap: 0.5rem;
	padding: 0.875rem 1.5rem;
	border: 2px solid var(--border-color);
	background: var(--card-bg);
	border-radius: 12px;
	color: var(--text-secondary);
	font-size: 1rem;
	font-weight: 500;
	cursor: pointer;
	transition: all 0.2s ease;
}

.mode-btn:hover:not(:disabled) {
	border-color: var(--primary-color);
	color: var(--primary-color);
	background: rgba(255, 107, 107, 0.05);
}

.mode-btn.active {
	border-color: var(--primary-color);
	background: var(--primary-color);
	color: white;
}

.mode-btn:disabled {
	opacity: 0.5;
	cursor: not-allowed;
}

.mode-icon {
	font-size: 1.2rem;
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
	display: flex;
	align-items: center;
	gap: 0.5rem;
}

.count-badge {
	display: inline-block;
	padding: 0.125rem 0.5rem;
	background: rgba(255, 107, 107, 0.15);
	color: var(--primary-color);
	border-radius: 8px;
	font-size: 0.75rem;
	font-weight: 600;
}

.form-input,
.form-select,
.form-textarea {
	padding: 1rem 1.25rem;
	background: rgba(0, 0, 0, 0.2);
	border: 1px solid var(--border-color);
	border-radius: 12px;
	color: var(--text-primary);
	font-size: 1rem;
	transition: all 0.2s ease;
	font-family: inherit;
}

.form-textarea {
	resize: vertical;
	line-height: 1.6;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
	outline: none;
	border-color: var(--accent-primary);
	box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.1);
}

.form-input::placeholder,
.form-textarea::placeholder {
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
	transform: translateY(-1px);
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

/* 批量添加结果样式 */
.batch-result-card {
	background: var(--card-bg);
	border-radius: 20px;
	border: 1px solid var(--border-color);
	padding: 2rem;
	margin-bottom: 2rem;
}

.batch-result-header {
	margin-bottom: 1.5rem;
}

.batch-result-title {
	font-size: 1.5rem;
	font-weight: 600;
	color: var(--text-primary);
	margin-bottom: 1rem;
}

.batch-result-stats {
	display: flex;
	gap: 1rem;
	flex-wrap: wrap;
}

.stat-item {
	flex: 1;
	min-width: 140px;
	display: flex;
	align-items: center;
	gap: 0.75rem;
	padding: 1rem 1.25rem;
	background: rgba(0, 0, 0, 0.2);
	border-radius: 12px;
	border: 1px solid var(--border-color);
}

.stat-item.success {
	border-color: rgba(46, 213, 115, 0.3);
	background: rgba(46, 213, 115, 0.05);
}

.stat-item.exists {
	border-color: rgba(52, 152, 219, 0.3);
	background: rgba(52, 152, 219, 0.05);
}

.stat-item.failed {
	border-color: rgba(231, 76, 60, 0.3);
	background: rgba(231, 76, 60, 0.05);
}

.stat-icon {
	font-size: 1.5rem;
}

.stat-item.success .stat-icon {
	color: #2ed573;
}

.stat-item.exists .stat-icon {
	color: #3498db;
}

.stat-item.failed .stat-icon {
	color: #e74c3c;
}

.stat-label {
	color: var(--text-muted);
	font-size: 0.875rem;
}

.stat-value {
	margin-left: auto;
	font-size: 1.5rem;
	font-weight: 700;
	color: var(--text-primary);
}

.batch-result-details {
	display: flex;
	flex-direction: column;
	gap: 1.5rem;
	margin-bottom: 1.5rem;
}

.result-group {
	display: flex;
	flex-direction: column;
	gap: 0.75rem;
}

.result-group-title {
	font-size: 0.875rem;
	font-weight: 600;
	margin: 0;
}

.result-group-title.success {
	color: #2ed573;
}

.result-group-title.exists {
	color: #3498db;
}

.result-group-title.failed {
	color: #e74c3c;
}

.result-group-list {
	display: flex;
	flex-wrap: wrap;
	gap: 0.5rem;
}

.result-tag {
	display: inline-block;
	padding: 0.375rem 0.75rem;
	border-radius: 8px;
	font-size: 0.8rem;
	font-weight: 500;
	font-family: 'Courier New', monospace;
}

.result-tag.success {
	background: rgba(46, 213, 115, 0.15);
	color: #2ed573;
	border: 1px solid rgba(46, 213, 115, 0.3);
}

.result-tag.exists {
	background: rgba(52, 152, 219, 0.15);
	color: #3498db;
	border: 1px solid rgba(52, 152, 219, 0.3);
}

.result-tag.failed {
	background: rgba(231, 76, 60, 0.15);
	color: #e74c3c;
	border: 1px solid rgba(231, 76, 60, 0.3);
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

.cookie-section {
	text-align: center;
	padding: 1.5rem 0;
}

.btn-cookie {
	margin-bottom: 0.5rem;
}

.cookie-hint {
	font-size: 0.85rem;
	color: var(--text-muted);
	margin: 0;
}

/* 模态框样式 */
.modal-overlay {
	position: fixed;
	top: 0;
	left: 0;
	right: 0;
	bottom: 0;
	background: rgba(0, 0, 0, 0.6);
	display: flex;
	align-items: center;
	justify-content: center;
	z-index: 1000;
	padding: 1rem;
}

.modal-content {
	background: var(--card-bg);
	border-radius: 20px;
	border: 1px solid var(--border-color);
	width: 100%;
	max-width: 500px;
	max-height: 90vh;
	overflow-y: auto;
	box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 1.5rem 2rem 1rem;
	border-bottom: 1px solid var(--border-color);
}

.modal-title {
	font-size: 1.25rem;
	font-weight: 600;
	color: var(--text-primary);
	margin: 0;
}

.modal-close {
	width: 32px;
	height: 32px;
	border: none;
	background: rgba(255, 255, 255, 0.1);
	border-radius: 50%;
	color: var(--text-muted);
	font-size: 1.25rem;
	cursor: pointer;
	transition: all 0.2s ease;
	display: flex;
	align-items: center;
	justify-content: center;
}

.modal-close:hover {
	background: rgba(255, 255, 255, 0.15);
	color: var(--text-primary);
}

.modal-form {
	padding: 1.5rem 2rem 2rem;
	display: flex;
	flex-direction: column;
	gap: 1.25rem;
}

.form-textarea {
	padding: 1rem 1.25rem;
	background: rgba(0, 0, 0, 0.2);
	border: 1px solid var(--border-color);
	border-radius: 12px;
	color: var(--text-primary);
	font-size: 0.95rem;
	font-family: 'JetBrains Mono', monospace;
	resize: vertical;
	transition: all 0.2s ease;
	min-height: 100px;
}

.form-textarea:focus {
	outline: none;
	border-color: var(--accent-primary);
	box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.1);
}

.form-textarea::placeholder {
	color: var(--text-muted);
	font-family: inherit;
}

.modal-actions {
	display: flex;
	gap: 1rem;
	justify-content: flex-end;
	padding-top: 1rem;
	border-top: 1px solid var(--border-color);
}

.modal-enter-active {
	animation: modalIn 0.3s ease;
}

.modal-leave-active {
	animation: modalIn 0.25s ease reverse;
}

@keyframes modalIn {
	from {
		opacity: 0;
		transform: scale(0.95);
	}
	to {
		opacity: 1;
		transform: scale(1);
	}
}

@media (max-width: 600px) {
	.modal-overlay {
		padding: 0.5rem;
	}

	.modal-header,
	.modal-form {
		padding-left: 1.5rem;
		padding-right: 1.5rem;
	}

	.modal-actions {
		flex-direction: column;
	}
}
</style>
