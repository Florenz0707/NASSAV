# NASSAV 前端变更实施计划

## 项目概况

### 技术栈
- **框架**: Vue 3 (Composition API)
- **构建工具**: Vite
- **状态管理**: Pinia
- **路由**: Vue Router
- **HTTP 客户端**: Axios
- **样式**: Tailwind CSS 4.x
- **包管理器**: pnpm

### 项目结构分析
```
vue_frontend/src/
├── api/
│   └── index.js              # API 封装层，统一管理后端接口
├── components/
│   ├── ResourceCard.vue      # 资源卡片组件
│   ├── BatchControls.vue     # 批量操作控制组件
│   ├── ResourcePagination.vue # 分页组件
│   ├── ConfirmDialog.vue     # 确认对话框
│   ├── Toast.vue             # 消息提示
│   └── ...                   # 其他通用组件
├── views/
│   ├── ResourcesView.vue     # 资源列表页
│   ├── ResourceDetailView.vue # 资源详情页
│   ├── DownloadsView.vue     # 下载管理页
│   ├── AddResourceView.vue   # 添加资源页
│   ├── ActorsView.vue        # 演员列表页
│   ├── ActorDetailView.vue   # 演员详情页
│   ├── GenresView.vue        # 类别列表页
│   └── GenreDetailView.vue   # 类别详情页
├── stores/
│   ├── resource.js           # 资源状态管理
│   ├── websocket.js          # WebSocket 连接管理
│   ├── toast.js              # 消息提示状态
│   ├── actorGroups.js        # 演员分组状态
│   └── genreGroups.js        # 类别分组状态
├── router/
│   └── index.js              # 路由配置
└── App.vue                   # 根组件
```

### 核心功能模块
1. **资源管理**: 浏览、搜索、过滤、排序资源
2. **下载管理**: 提交下载任务、监控下载进度
3. **元数据管理**: 自动获取和刷新视频元数据
4. **批量操作**: 支持批量下载、刷新、删除
5. **实时通信**: WebSocket 实时推送任务状态

---

## 待实施变更清单

根据 `plan.md` 的需求，前端需要实施以下 6 个变更：

| 编号 | 功能 | 优先级 | 工作量 | 涉及文件 |
|------|------|--------|--------|----------|
| F1 | 资源卡下载按钮状态优化 | P1 | 低 (1-2h) | ResourceCard.vue |
| F2 | 详情页返回保留页码状态 | P1 | 中 (3-5h) | 5个 View 文件 |
| F3 | 刷新动作多选支持 | P2 | 中 (4-6h) | ResourceCard.vue, ResourceDetailView.vue |
| F4 | 下载页任务标题缓存优化 | P1 | 低 (1-2h) | websocket.js |
| F5 | 批量添加功能 | P2 | 中 (3-4h) | AddResourceView.vue |
| F6 | 批量下载超时动态延长 | P2 | 低 (0.5-1h) | api/index.js |

---

## 详细实施方案

### F1: 资源卡下载按钮状态优化 ⭐ P1

**当前状态分析**:
- ResourceCard.vue 已通过 `resource.has_video` 判断下载状态
- 下载按钮样式未区分已下载和未下载状态
- 已下载资源仍可点击下载按钮

**目标**:
- 未下载: 显示重点色按钮，可点击
- 已下载: 显示灰色按钮，禁用状态

**实施步骤**:

1. **修改文件**: `src/components/ResourceCard.vue`

2. **修改下载按钮 HTML 结构** (约 L250-270):
```vue
<!-- 替换现有的下载按钮 -->
<button
  :class="[
    'px-3.5 py-2 rounded-lg font-medium text-sm transition-all duration-200',
    resource.has_video
      ? 'bg-zinc-600 text-zinc-400 cursor-not-allowed opacity-60'
      : 'bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white hover:shadow-lg hover:-translate-y-0.5'
  ]"
  :disabled="resource.has_video"
  :title="resource.has_video ? '视频已下载' : '提交下载任务'"
  @click.stop="$emit('download', resource.avid)"
>
  {{ resource.has_video ? '✓ 已下载' : '↓ 下载' }}
</button>
```

3. **测试验证**:
   - [ ] 未下载资源显示红色按钮，悬停有动画效果
   - [ ] 已下载资源显示灰色按钮，cursor 为 not-allowed
   - [ ] 已下载资源点击按钮无响应

**预期效果**: 用户可以一眼分辨资源下载状态，避免重复提交下载任务

---

### F2: 详情页返回保留页码状态 ⭐ P1

**当前状态分析**:
- 各列表页使用本地 ref 管理页码
- 跳转详情页后返回，页码重置为第 1 页
- 用户体验不佳，需要重新翻页

**目标**:
- 从详情页返回列表页时，保留之前的页码
- 页码状态持久化到 URL query 参数
- 支持浏览器前进/后退

**技术方案**: 使用 **URL Query 参数**

**优势**:
- ✅ 刷新页面后状态保留
- ✅ 可分享带页码的链接
- ✅ 符合 RESTful 规范
- ✅ 支持浏览器历史记录

**实施步骤**:

#### 2.1 修改资源列表页 (`ResourcesView.vue`)

**a. 初始化页码从 URL 读取** (约 L90):
```javascript
const route = useRoute()
const router = useRouter()

// 从 URL query 初始化页码和其他状态
const page = ref(parseInt(route.query.page) || 1)
const pageSize = ref(parseInt(route.query.pageSize) || 18)
const searchQuery = ref(route.query.search || '')
const filterStatus = ref(route.query.status || 'all')
const sortBy = ref(route.query.sortBy || 'metadata_create_time')
const sortOrder = ref(route.query.order || 'desc')
```

**b. 监听状态变化并同步到 URL** (onMounted 之后添加):
```javascript
// 状态变化时更新 URL
watch([page, pageSize, searchQuery, filterStatus, sortBy, sortOrder], () => {
  const query = {
    page: page.value,
    pageSize: pageSize.value,
  }
  if (searchQuery.value) query.search = searchQuery.value
  if (filterStatus.value !== 'all') query.status = filterStatus.value
  if (sortBy.value !== 'metadata_create_time') query.sortBy = sortBy.value
  if (sortOrder.value !== 'desc') query.order = sortOrder.value

  router.replace({ query })
}, { deep: true })
```

**c. 修改 ResourceCard 跳转逻辑** (在 template 中):
```vue
<!-- 保留当前 URL 作为 from 参数 -->
<RouterLink
  :to="{
    path: `/resource/${resource.avid}`,
    query: { from: $route.fullPath }
  }"
  class="查看详情按钮样式..."
>
  查看详情
</RouterLink>
```

#### 2.2 修改资源详情页 (`ResourceDetailView.vue`)

**修改返回按钮逻辑** (约 L93):
```javascript
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
```

#### 2.3 同样修改以下页面

**演员列表页** (`ActorsView.vue`):
- 添加页码 URL 同步逻辑
- 修改演员卡片跳转时保留 from 参数

**演员详情页** (`ActorDetailView.vue`):
- 添加返回按钮保留状态逻辑

**类别列表页** (`GenresView.vue`):
- 添加页码 URL 同步逻辑
- 修改类别卡片跳转时保留 from 参数

**类别详情页** (`GenreDetailView.vue`):
- 添加返回按钮保留状态逻辑

**测试验证**:
- [ ] 在资源列表第 3 页点击某个资源
- [ ] 进入详情页，URL 包含 `?from=/resources?page=3&...`
- [ ] 点击返回，回到第 3 页
- [ ] 刷新页面，仍停留在第 3 页
- [ ] 同样测试演员页和类别页

---

### F3: 刷新动作多选支持 ⭐ P2

**当前状态分析**:
- 刷新按钮直接调用 `resourceApi.refresh(avid)`
- 后端刷新逻辑为全量刷新（m3u8 + 元数据）
- 无法细粒度控制刷新范围

**目标**:
- 用户可选择刷新项目：
  - ☑ 刷新 M3U8 链接
  - ☑ 刷新元数据（从源站重新抓取）
  - ☑ 重新翻译标题

**依赖**: 需要后端 B1 实现细粒度刷新 API

**实施步骤**:

#### 3.1 修改 API 层 (`src/api/index.js`)

**更新 refresh 方法签名** (约 L142):
```javascript
export const resourceApi = {
  // ... 其他方法

  // 刷新资源，支持细粒度参数
  refresh: (avid, options = {}) => {
    const params = {
      refresh_m3u8: options.refresh_m3u8 !== false,      // 默认 true
      refresh_metadata: options.refresh_metadata !== false, // 默认 true
      retranslate: options.retranslate || false          // 默认 false
    }
    return api.post(`/resource/refresh/${encodeURIComponent(avid)}`, params)
  },

  // ... 其他方法
}
```

#### 3.2 修改资源详情页 (`ResourceDetailView.vue`)

**a. 添加刷新选项状态**:
```javascript
const showRefreshMenu = ref(false)
const refreshOptions = ref({
  m3u8: true,
  metadata: true,
  translate: false
})
const refreshing = ref(false)
```

**b. 修改刷新逻辑**:
```javascript
async function handleRefresh() {
  refreshing.value = true
  try {
    await resourceStore.refreshResource(avid.value, refreshOptions.value)
    await fetchMetadata()
    toastStore.success('刷新成功')
    showRefreshMenu.value = false
  } catch (err) {
    toastStore.error(err.message || '刷新失败')
  } finally {
    refreshing.value = false
  }
}

// 快速刷新（使用默认选项）
async function quickRefresh() {
  refreshOptions.value = { m3u8: true, metadata: true, translate: false }
  await handleRefresh()
}
```

**c. 修改 UI (约 L200-250)**:
```vue
<!-- 刷新按钮组 -->
<div class="relative">
  <div class="flex gap-2">
    <!-- 快速刷新按钮 -->
    <button
      @click="quickRefresh"
      :disabled="refreshing"
      class="flex-1 px-4 py-2.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition disabled:opacity-50"
    >
      {{ refreshing ? '刷新中...' : '快速刷新' }}
    </button>

    <!-- 高级刷新按钮 -->
    <button
      @click="showRefreshMenu = !showRefreshMenu"
      class="px-3 py-2.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition"
      :disabled="refreshing"
    >
      ▾
    </button>
  </div>

  <!-- 刷新选项菜单 -->
  <div
    v-if="showRefreshMenu"
    class="absolute top-full mt-2 right-0 bg-[rgba(18,18,28,0.95)] border border-white/10 rounded-lg shadow-xl p-4 min-w-[240px] z-10"
  >
    <div class="mb-3 font-medium text-white">选择刷新项目</div>

    <label class="flex items-center gap-2 mb-2 cursor-pointer hover:bg-white/5 p-2 rounded">
      <input
        type="checkbox"
        v-model="refreshOptions.m3u8"
        class="w-4 h-4"
      />
      <span class="text-sm text-zinc-300">刷新 M3U8 链接</span>
    </label>

    <label class="flex items-center gap-2 mb-2 cursor-pointer hover:bg-white/5 p-2 rounded">
      <input
        type="checkbox"
        v-model="refreshOptions.metadata"
        class="w-4 h-4"
      />
      <span class="text-sm text-zinc-300">刷新元数据</span>
    </label>

    <label class="flex items-center gap-2 mb-3 cursor-pointer hover:bg-white/5 p-2 rounded">
      <input
        type="checkbox"
        v-model="refreshOptions.translate"
        class="w-4 h-4"
      />
      <span class="text-sm text-zinc-300">重新翻译标题</span>
    </label>

    <button
      @click="handleRefresh"
      :disabled="refreshing"
      class="w-full px-4 py-2 bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white rounded-lg font-medium hover:shadow-lg transition disabled:opacity-50"
    >
      确认刷新
    </button>
  </div>
</div>
```

#### 3.3 修改资源卡片组件 (`ResourceCard.vue`)

**类似地添加刷新选项菜单** (可选，如果空间允许):
- 简化版：只保留快速刷新，不提供选项
- 完整版：参考详情页实现

**测试验证**:
- [ ] 点击"快速刷新"，使用默认选项刷新
- [ ] 点击下拉按钮，显示刷新选项菜单
- [ ] 取消勾选"刷新元数据"，确认后只刷新 M3U8
- [ ] 勾选"重新翻译"，确认后执行翻译任务

---

### F4: 下载页任务标题缓存优化 ⭐ P1

**当前状态分析**:
- `stores/websocket.js` 使用 `metadataCache` (Set) 记录已请求的 AVID
- 无法缓存获取到的标题数据
- 每次 WebSocket 推送新数据时，标题可能丢失

**问题根源**:
- Set 只能记录 AVID，不能存储标题内容
- 异步获取的标题无法持久化

**目标**:
- 使用 Map 缓存 `avid -> title` 映射
- WebSocket 更新时优先使用缓存标题
- 减少重复请求和标题闪烁

**实施步骤**:

#### 4.1 修改 `src/stores/websocket.js`

**a. 替换缓存数据结构** (约 L22):
```javascript
// 替换原来的 Set
// const metadataCache = ref(new Set())

// 改为 Map，存储 avid -> { title, timestamp }
const titleCache = ref(new Map())
```

**b. 修改 updateTaskData 函数** (约 L176):
```javascript
function updateTaskData(data) {
  // 更新任务列表时，先从缓存应用标题
  activeTasks.value = (data.active_tasks || []).map(task => ({
    ...task,
    title: task.title || titleCache.value.get(task.avid)?.title || null
  }))

  pendingTasks.value = (data.pending_tasks || []).map(task => ({
    ...task,
    title: task.title || titleCache.value.get(task.avid)?.title || null
  }))

  activeCount.value = data.active_count || 0
  pendingCount.value = data.pending_count || 0
  totalCount.value = data.total_count || 0

  // 检查并补充缺失的元数据
  fetchMissingMetadata()
}
```

**c. 修改 fetchMissingMetadata 函数** (约 L207):
```javascript
async function fetchMissingMetadata() {
  const allTasks = [...activeTasks.value, ...pendingTasks.value]

  for (const task of allTasks) {
    // 如果任务没有 title 且缓存中也没有
    if (!task.title && task.avid && !titleCache.value.has(task.avid)) {
      try {
        console.log(`[WebSocket] 获取元数据: ${task.avid}`)
        const response = await resourceApi.getMetadata(task.avid)

        if (response.data && response.data.title) {
          // 存入缓存
          titleCache.value.set(task.avid, {
            title: response.data.title,
            timestamp: Date.now()
          })

          // 立即更新当前任务列表
          updateTaskTitle(task.avid, response.data.title)
        }
      } catch (error) {
        console.error(`[WebSocket] 获取元数据失败 (${task.avid}):`, error)
        // 不存入缓存，允许下次重试
      }
    }
  }
}

// 辅助函数：更新指定 AVID 的标题
function updateTaskTitle(avid, title) {
  const activeIndex = activeTasks.value.findIndex(t => t.avid === avid)
  if (activeIndex !== -1) {
    activeTasks.value[activeIndex].title = title
  }

  const pendingIndex = pendingTasks.value.findIndex(t => t.avid === avid)
  if (pendingIndex !== -1) {
    pendingTasks.value[pendingIndex].title = title
  }
}
```

**d. 添加缓存清理机制** (可选优化):
```javascript
// 定期清理过期缓存（超过 1 小时的条目）
function cleanupCache() {
  const now = Date.now()
  const maxAge = 60 * 60 * 1000 // 1 小时

  for (const [avid, data] of titleCache.value.entries()) {
    if (now - data.timestamp > maxAge) {
      titleCache.value.delete(avid)
    }
  }
}

// 每 10 分钟清理一次
let cleanupTimer = setInterval(cleanupCache, 10 * 60 * 1000)

// 断开连接时清理定时器
function disconnect() {
  // ... 原有逻辑
  if (cleanupTimer) {
    clearInterval(cleanupTimer)
    cleanupTimer = null
  }
}
```

**e. 导出新的接口**:
```javascript
return {
  // ... 原有导出
  titleCache,  // 导出供调试使用
  updateTaskData
}
```

**测试验证**:
- [ ] 提交多个下载任务
- [ ] 打开下载页，观察任务标题显示
- [ ] WebSocket 推送新状态时，标题不应闪烁或消失
- [ ] 刷新页面，重新获取元数据后标题应正确显示

---

### F5: 批量添加功能 ⭐ P2

**当前状态分析**:
- `AddResourceView.vue` 只支持单个 AVID 添加
- 批量添加需求：一次性输入多个 AVID

**目标**:
- 添加"批量添加"模式切换
- 支持多种格式输入：
  - 换行分隔: `ABC-001\nDEF-002`
  - 逗号分隔: `ABC-001, DEF-002`
  - 空格分隔: `ABC-001 DEF-002`
  - 混合格式
- 显示已识别的 AVID 数量
- 提交后显示成功/失败统计

**实施步骤**:

#### 5.1 修改 `src/views/AddResourceView.vue`

**a. 添加批量模式状态** (约 L15):
```javascript
const mode = ref('single')  // 'single' | 'batch'
const batchAvids = ref('')
const batchSubmitting = ref(false)
const batchResult = ref(null)
```

**b. 添加 AVID 解析逻辑**:
```javascript
// 解析批量输入的 AVID 列表
const parsedAvids = computed(() => {
  if (mode.value !== 'batch') return []

  return batchAvids.value
    .split(/[\n,\s]+/)           // 按换行、逗号、空格分割
    .map(s => s.trim().toUpperCase())
    .filter(s => s.length > 0)   // 过滤空字符串
    .filter((v, i, arr) => arr.indexOf(v) === i)  // 去重
})

// 批量添加处理
async function handleBatchSubmit() {
  const avids = parsedAvids.value
  if (avids.length === 0) {
    toastStore.warning('请输入至少一个视频编号')
    return
  }

  batchSubmitting.value = true
  batchResult.value = null

  try {
    const response = await resourceApi.batch({
      action: 'add',
      avids: avids,
      source: source.value
    })

    // 解析返回结果
    const results = response.data?.results || []
    const success = results.filter(r => r.code >= 200 && r.code < 300).length
    const failed = results.filter(r => r.code >= 400).length
    const exists = results.filter(r => r.code === 409).length

    batchResult.value = {
      success: true,
      total: avids.length,
      successCount: success,
      failedCount: failed,
      existsCount: exists,
      results: results
    }

    toastStore.success(`批量添加完成：成功 ${success}，已存在 ${exists}，失败 ${failed}`)
  } catch (err) {
    batchResult.value = {
      success: false,
      message: err.message
    }
    toastStore.error(err.message || '批量添加失败')
  } finally {
    batchSubmitting.value = false
  }
}

// 重置批量表单
function resetBatch() {
  batchAvids.value = ''
  batchResult.value = null
}
```

**c. 修改 UI 结构** (约 L145):
```vue
<div class="add-form-card">
  <!-- 模式切换 -->
  <div class="mode-toggle mb-6 flex gap-2 p-1 bg-[rgba(18,18,28,0.6)] rounded-xl w-fit">
    <button
      @click="mode = 'single'"
      :class="[
        'px-6 py-2 rounded-lg font-medium transition',
        mode === 'single'
          ? 'bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white'
          : 'text-zinc-400 hover:text-white'
      ]"
    >
      单个添加
    </button>
    <button
      @click="mode = 'batch'"
      :class="[
        'px-6 py-2 rounded-lg font-medium transition',
        mode === 'batch'
          ? 'bg-gradient-to-br from-[#ff6b6b] to-[#ff5252] text-white'
          : 'text-zinc-400 hover:text-white'
      ]"
    >
      批量添加
    </button>
  </div>

  <!-- 单个添加表单 -->
  <form v-if="mode === 'single'" @submit.prevent="handleSubmit" class="add-form">
    <!-- 原有的单个添加表单内容 -->
    <!-- ... -->
  </form>

  <!-- 批量添加表单 -->
  <form v-else @submit.prevent="handleBatchSubmit" class="add-form">
    <div class="form-group">
      <label class="form-label">批量输入视频编号</label>
      <textarea
        v-model="batchAvids"
        :disabled="batchSubmitting"
        rows="10"
        placeholder="输入多个 AVID，支持以下格式：&#10;&#10;• 每行一个：&#10;  ABC-001&#10;  DEF-002&#10;&#10;• 逗号分隔：ABC-001, DEF-002, GHI-003&#10;&#10;• 空格分隔：ABC-001 DEF-002 GHI-003&#10;&#10;• 混合格式（自动识别）"
        class="form-input font-mono text-sm"
      ></textarea>

      <!-- AVID 统计 -->
      <div v-if="parsedAvids.length > 0" class="mt-2 text-sm text-zinc-400">
        已识别 <span class="text-[#ff6b6b] font-semibold">{{ parsedAvids.length }}</span> 个视频编号
      </div>
    </div>

    <div class="form-group">
      <label class="form-label">下载源</label>
      <select
        v-model="source"
        :disabled="batchSubmitting"
        class="form-input"
      >
        <option value="any">自动选择</option>
        <option v-for="s in resourceStore.sources" :key="s" :value="s">
          {{ s }}
        </option>
      </select>
    </div>

    <div class="form-actions">
      <button
        type="submit"
        :disabled="batchSubmitting || parsedAvids.length === 0"
        class="submit-btn"
      >
        {{ batchSubmitting ? '提交中...' : `添加 ${parsedAvids.length} 个资源` }}
      </button>

      <button
        type="button"
        @click="resetBatch"
        :disabled="batchSubmitting"
        class="secondary-btn"
      >
        清空
      </button>
    </div>
  </form>

  <!-- 批量结果展示 -->
  <div v-if="batchResult" class="mt-6 p-4 bg-[rgba(18,18,28,0.6)] rounded-xl">
    <div class="text-lg font-semibold mb-3">批量添加结果</div>

    <div class="grid grid-cols-3 gap-4 mb-4">
      <div class="stat-card">
        <div class="stat-value text-green-500">{{ batchResult.successCount }}</div>
        <div class="stat-label">成功</div>
      </div>
      <div class="stat-card">
        <div class="stat-value text-blue-500">{{ batchResult.existsCount }}</div>
        <div class="stat-label">已存在</div>
      </div>
      <div class="stat-card">
        <div class="stat-value text-red-500">{{ batchResult.failedCount }}</div>
        <div class="stat-label">失败</div>
      </div>
    </div>

    <!-- 详细结果列表（可折叠） -->
    <details class="mt-4">
      <summary class="cursor-pointer text-sm text-zinc-400 hover:text-white">
        查看详细结果
      </summary>
      <div class="mt-2 max-h-60 overflow-y-auto">
        <div
          v-for="(result, index) in batchResult.results"
          :key="index"
          class="flex items-center justify-between py-2 px-3 hover:bg-white/5 rounded"
        >
          <span class="font-mono text-sm">{{ result.avid }}</span>
          <span
            :class="[
              'text-xs px-2 py-1 rounded',
              result.code < 300 ? 'bg-green-500/20 text-green-400' :
              result.code === 409 ? 'bg-blue-500/20 text-blue-400' :
              'bg-red-500/20 text-red-400'
            ]"
          >
            {{ result.message || (result.code < 300 ? '成功' : result.code === 409 ? '已存在' : '失败') }}
          </span>
        </div>
      </div>
    </details>

    <div class="mt-4 flex gap-2">
      <button @click="resetBatch" class="secondary-btn">
        继续添加
      </button>
      <RouterLink to="/resources" class="submit-btn">
        查看资源库
      </RouterLink>
    </div>
  </div>
</div>
```

**测试验证**:
- [ ] 点击"批量添加"切换模式
- [ ] 输入多行 AVID，显示正确的识别数量
- [ ] 输入逗号分隔的 AVID，正确解析
- [ ] 提交后显示成功/失败统计
- [ ] 查看详细结果列表

---

### F6: 批量下载超时动态延长 ⭐ P2

**当前状态分析**:
- `api/index.js` 中 axios 实例配置了固定的 30 秒超时
- 批量操作（如批量下载）在任务数量多时可能超时

**目标**:
- 根据任务数量动态计算超时时间
- 公式: `baseTimeout + count * timeoutPerItem`

**实施步骤**:

#### 6.1 修改 `src/api/index.js`

**a. 更新批量下载方法** (约 L164):
```javascript
export const downloadApi = {
  // ... 其他方法

  // 批量提交下载任务，动态超时
  batchSubmit: (avids) => {
    // 基础超时 10 秒，每个任务增加 2 秒
    const timeout = 10000 + avids.length * 2000
    console.log(`[API] 批量下载 ${avids.length} 个任务，超时设置: ${timeout}ms`)

    return api.post('/downloads/batch_submit', { avids }, { timeout })
  }
}
```

**b. 更新资源批量操作方法** (约 L150):
```javascript
export const resourceApi = {
  // ... 其他方法

  // 批量操作，动态超时
  batch: (payload) => {
    const avids = payload.avids || []
    let baseTimeout = 15000  // 基础 15 秒
    let timeoutPerItem = 3000  // 每个资源 3 秒

    // 根据操作类型调整
    if (payload.action === 'add') {
      timeoutPerItem = 5000  // 添加操作需要抓取元数据，更耗时
    } else if (payload.action === 'refresh') {
      timeoutPerItem = 4000
    }

    const timeout = baseTimeout + avids.length * timeoutPerItem
    console.log(`[API] 批量${payload.action} ${avids.length} 个任务，超时: ${timeout}ms`)

    return api.post('/resources/batch', payload, { timeout })
  }
}
```

**测试验证**:
- [ ] 批量下载 5 个任务，超时应为 20 秒
- [ ] 批量下载 20 个任务，超时应为 50 秒
- [ ] 批量添加 10 个资源，超时应为 65 秒
- [ ] 请求不应在合理时间内超时

---

## 实施时间线

### 第一周：P1 优先级（高价值、低风险）

| 日期 | 任务 | 预计耗时 | 状态 |
|------|------|---------|------|
| Day 1 上午 | F1: 资源卡下载按钮状态优化 | 1-2h | ⬜ |
| Day 1 下午 | F4: 下载页任务标题缓存优化 | 1-2h | ⬜ |
| Day 2-3 | F2: 详情页返回保留页码状态 | 3-5h | ⬜ |
| Day 3 下午 | **测试 & Bug 修复** | 2h | ⬜ |

### 第二周：P2 优先级（功能增强）

| 日期 | 任务 | 预计耗时 | 状态 |
|------|------|---------|------|
| Day 1 | F6: 批量下载超时动态延长 | 0.5-1h | ⬜ |
| Day 1-2 | F5: 批量添加功能 | 3-4h | ⬜ |
| Day 2 下午 | 等待后端 B1 实现 | - | ⬜ |
| Day 3-4 | F3: 刷新动作多选支持 | 4-6h | ⬜ |
| Day 4 下午 | **集成测试** | 2h | ⬜ |

### 总计工作量
- **总预计时间**: 约 16-22 小时
- **实际工作日**: 约 2 周（考虑后端协作和测试）

---

## 测试检查清单

### F1: 资源卡下载按钮状态优化
- [ ] 未下载资源：按钮显示红色渐变，文本为"↓ 下载"
- [ ] 未下载资源：按钮可点击，悬停有动画效果
- [ ] 已下载资源：按钮显示灰色，文本为"✓ 已下载"
- [ ] 已下载资源：按钮禁用，cursor 为 not-allowed
- [ ] 已下载资源：点击按钮无响应

### F2: 详情页返回保留页码状态
- [ ] 资源列表页：翻到第 3 页，URL 包含 `?page=3`
- [ ] 资源列表页：点击某个资源卡片，进入详情页
- [ ] 资源详情页：URL 包含 `?from=/resources?page=3...`
- [ ] 资源详情页：点击返回按钮
- [ ] 返回后仍在第 3 页，资源列表未重置
- [ ] 刷新浏览器，页面仍停留在第 3 页
- [ ] 同样测试演员页、类别页
- [ ] 浏览器前进/后退按钮工作正常

### F3: 刷新动作多选支持
- [ ] 详情页显示"快速刷新"和下拉按钮
- [ ] 点击"快速刷新"，使用默认选项（m3u8+元数据）
- [ ] 点击下拉按钮，显示刷新选项菜单
- [ ] 取消勾选"刷新元数据"，只勾选"刷新 M3U8"
- [ ] 点击"确认刷新"，后端收到正确参数
- [ ] 勾选"重新翻译"，翻译任务已提交
- [ ] 刷新完成后菜单自动关闭

### F4: 下载页任务标题缓存优化
- [ ] 提交 5 个下载任务
- [ ] 打开下载页，所有任务标题正确显示
- [ ] WebSocket 推送新状态，标题不闪烁
- [ ] 刷新页面，标题从后端重新获取
- [ ] 同一任务不会重复请求元数据
- [ ] 控制台无重复的"获取元数据"日志

### F5: 批量添加功能
- [ ] 点击"批量添加"切换模式
- [ ] 输入多行 AVID（换行分隔），显示识别数量
- [ ] 输入逗号分隔的 AVID，正确解析
- [ ] 输入混合格式（换行+逗号+空格），正确解析
- [ ] 自动去重，不会提交重复的 AVID
- [ ] 提交后显示成功/已存在/失败统计
- [ ] 展开详细结果，每个 AVID 状态正确
- [ ] 点击"继续添加"，表单清空
- [ ] 点击"查看资源库"，跳转到列表页

### F6: 批量下载超时动态延长
- [ ] 批量下载 3 个任务，16 秒内完成不超时
- [ ] 批量下载 10 个任务，30 秒内完成不超时
- [ ] 批量添加 5 个资源，40 秒内完成不超时
- [ ] 控制台打印正确的超时设置
- [ ] 网络慢时不会提前超时

---

## 风险评估与应对

### 风险 1: F2 状态持久化可能导致 URL 过长
**影响**: 当同时保留多个 query 参数时，URL 可能变得很长
**应对**:
- 只保留核心参数（page, search, status）
- 使用短参数名（p, q, s）
- 必要时使用 SessionStorage 作为备选方案

### 风险 2: F3 依赖后端 B1 实现
**影响**: 后端未实现时前端无法完整测试
**应对**:
- 先完成前端 UI 开发
- 使用 mock 数据进行前端测试
- 与后端开发同步进度

### 风险 3: F4 缓存可能占用过多内存
**影响**: 长时间使用后，titleCache 可能积累大量条目
**应对**:
- 实现缓存清理机制（见实施方案）
- 设置缓存过期时间（1 小时）
- 限制缓存最大条目数（可选）

### 风险 4: 浏览器兼容性问题
**影响**: 某些新特性可能在旧浏览器不可用
**应对**:
- 使用 Vite 默认的 polyfill 配置
- 主要支持现代浏览器（Chrome/Edge/Firefox 最近 2 个版本）
- 必要时添加 feature detection

---

## 开发规范

### 代码风格
- 使用 Vue 3 Composition API
- 遵循项目现有的命名约定
- 组件名使用 PascalCase
- 文件名使用 PascalCase.vue
- 变量名使用 camelCase

### Git 提交规范
```
feat(F1): 优化资源卡下载按钮状态显示
feat(F2): 添加页码状态持久化到 URL
feat(F3): 支持细粒度刷新选项
feat(F4): 优化下载任务标题缓存逻辑
feat(F5): 添加批量添加资源功能
feat(F6): 批量操作超时动态延长
fix: 修复某某问题
docs: 更新文档
test: 添加测试用例
```

### 调试技巧
1. **使用 Vue Devtools**: 检查组件状态和 Pinia store
2. **Console 日志**: 关键操作添加 `console.debug`
3. **Network 面板**: 检查 API 请求和响应
4. **WebSocket 监控**: 在 Chrome DevTools -> Network -> WS 查看消息

---

## 后续优化建议

### 性能优化
1. **虚拟滚动**: 资源列表超过 100 项时使用虚拟列表
2. **图片懒加载**: ResourceCard 已实现，可进一步优化
3. **组件懒加载**: 路由级别的代码分割（已实现）

### 用户体验优化
1. **骨架屏**: 加载状态显示骨架屏而非空白
2. **乐观更新**: 操作后立即更新 UI，不等待后端响应
3. **离线支持**: 使用 Service Worker 缓存静态资源

### 功能增强
1. **高级搜索**: 支持多条件组合搜索
2. **自定义视图**: 用户可选择卡片大小、列数
3. **快捷键**: 添加键盘快捷键支持

---

## 联调接口文档

### F3 所需后端接口

**刷新资源（细粒度）**
```
POST /nassav/api/resource/refresh/{avid}
Content-Type: application/json

Request Body:
{
  "refresh_m3u8": true,      // 是否刷新 m3u8 链接
  "refresh_metadata": true,  // 是否刷新元数据
  "retranslate": false       // 是否重新翻译
}

Response:
{
  "code": 200,
  "message": "success",
  "data": {
    "m3u8_refreshed": true,
    "metadata_refreshed": true,
    "translation_queued": false
  }
}
```

### F5 所需后端接口

**批量添加资源**
```
POST /nassav/api/resources/batch
Content-Type: application/json

Request Body:
{
  "action": "add",
  "avids": ["ABC-001", "DEF-002", "GHI-003"],
  "source": "javbus"  // 可选，默认 "any"
}

Response:
{
  "code": 200,
  "message": "success",
  "data": {
    "results": [
      { "avid": "ABC-001", "code": 201, "message": "created" },
      { "avid": "DEF-002", "code": 409, "message": "already exists" },
      { "avid": "GHI-003", "code": 500, "message": "fetch failed" }
    ]
  }
}
```

---

## 总结

本实施计划涵盖了 6 个前端变更需求，总工作量约 **16-22 小时**，分为两周完成。

### 关键要点
1. **F1、F4、F6** 为低复杂度任务，可快速完成
2. **F2** 需要修改多个页面，但逻辑统一
3. **F3** 依赖后端接口，需要协作开发
4. **F5** 是最复杂的新功能，需要仔细设计 UI

### 实施顺序建议
1. 先完成 P1 任务（F1, F2, F4），快速提升体验
2. 然后完成独立任务（F6），降低风险
3. 最后完成依赖任务（F3, F5），联调测试

### 成功标准
- [ ] 所有测试用例通过
- [ ] 无严重 Bug 或性能问题
- [ ] 用户体验明显提升
- [ ] 代码质量符合规范
