# 变更实施计划

本文档基于 `abstract.md` 中的变更需求，评估其合理性、可行性和工作量，并详细描述前后端所需的工作计划。

---

## 评估总览

| 序号 | 变更项 | 合理性 | 可行性 | 工作量 | 优先级 |
|------|--------|--------|--------|--------|--------|
| F1 | 资源卡下载按钮状态优化 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 低 | P1 |
| F2 | 详情页返回保留页码状态 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 中 | P1 |
| F3 | 刷新动作多选支持 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 中 | P2 |
| F4 | 下载页任务标题缓存优化 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 低 | P1 |
| F5 | 批量添加功能 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 中 | P2 |
| F6 | 批量下载超时动态延长 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 低 | P2 |
| B1 | 支持细粒度刷新 API | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 中 | P2 |
| B2 | 任务队列显示完整列表 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 中 | P1 |
| B3 | 翻译质量优化 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 高 | P2 |
| B4 | source_title 规范化 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 低 | P3 |

---

## 一、前端变更

### F1: 资源卡下载按钮状态优化

**需求描述**：资源卡更新，调整下载按钮，当未下载时显示重点色、可点击；已下载时显示灰色、不可点击。

**评估**：
- **合理性**：✅ 优秀。明确的视觉反馈有助于用户快速识别资源状态，避免重复下载。
- **可行性**：✅ 高。当前 `ResourceCard.vue` 已有 `resource.has_video` 字段，只需调整样式和交互逻辑。
- **工作量**：🔹 低（约 1-2 小时）

**实施计划**：

1. **修改文件**：[src/components/ResourceCard.vue](vue_frontend/src/components/ResourceCard.vue)

2. **具体改动**：
   ```vue
   <!-- 修改下载按钮样式 -->
   <button
     :class="[
       'download-btn',
       resource.has_video ? 'downloaded' : 'pending'
     ]"
     :disabled="resource.has_video"
     @click="handleDownload"
   >
     {{ resource.has_video ? '已下载' : '下载' }}
   </button>
   ```

3. **样式定义**：
   - `.download-btn.pending`: 使用主题重点色（如 `#ff6b6b`），cursor: pointer
   - `.download-btn.downloaded`: 使用灰色（如 `#71717a`），cursor: not-allowed，添加 opacity

---

### F2: 详情页返回保留页码状态

**需求描述**：从资源详情页回退时，保留页码状态（同样适用于女优页和标签页）。

**评估**：
- **合理性**：✅ 优秀。提升用户浏览体验，避免返回后重新翻页。
- **可行性**：✅ 中高。需要引入状态持久化机制（URL Query 或 Store 持久化）。
- **工作量**：🔸 中（约 3-5 小时）

**实施计划**：

1. **方案选择**：推荐使用 **URL Query 参数** 方案
   - 优势：刷新页面后状态保留，可分享带页码的链接，符合 Web 标准
   - 劣势：URL 会变长

2. **修改文件**：
   - [src/views/ResourcesView.vue](vue_frontend/src/views/ResourcesView.vue)
   - [src/views/ActorsView.vue](vue_frontend/src/views/ActorsView.vue)
   - [src/views/GenresView.vue](vue_frontend/src/views/GenresView.vue)
   - [src/views/ActorDetailView.vue](vue_frontend/src/views/ActorDetailView.vue)
   - [src/views/GenreDetailView.vue](vue_frontend/src/views/GenreDetailView.vue)

3. **核心逻辑**：
   ```javascript
   // 从 URL 读取初始页码
   const route = useRoute()
   const router = useRouter()
   const currentPage = ref(parseInt(route.query.page) || 1)

   // 页码变化时同步到 URL
   watch(currentPage, (newPage) => {
     router.replace({
       query: { ...route.query, page: newPage }
     })
   })

   // 组件挂载时从 URL 恢复状态
   onMounted(() => {
     if (route.query.page) {
       currentPage.value = parseInt(route.query.page)
     }
   })
   ```

4. **详情页跳转时保留来源**：
   ```javascript
   // ResourceCard.vue 或列表页跳转时
   router.push({
     path: `/resource/${avid}`,
     query: { from: route.fullPath }
   })

   // ResourceDetailView.vue 返回时
   function goBack() {
     if (route.query.from) {
       router.push(route.query.from)
     } else {
       router.back()
     }
   }
   ```

---

### F3: 刷新动作多选支持

**需求描述**：更新刷新的动作，支持多选：刷新 m3u8、刷新元数据、重新翻译文本。

**评估**：
- **合理性**：✅ 良好。细粒度控制刷新范围，减少不必要的网络请求。
- **可行性**：✅ 中高。需要前后端配合，前端增加 UI 选项，后端增加参数支持。
- **工作量**：🔸 中（约 4-6 小时，含后端配合）

**实施计划**：

1. **修改文件**：
   - [src/views/ResourceDetailView.vue](vue_frontend/src/views/ResourceDetailView.vue)
   - [src/components/ResourceCard.vue](vue_frontend/src/components/ResourceCard.vue)

2. **UI 设计**：
   ```vue
   <!-- 刷新按钮改为下拉菜单或多选弹窗 -->
   <div class="refresh-menu">
     <button @click="showRefreshOptions = !showRefreshOptions">刷新 ▾</button>
     <div v-if="showRefreshOptions" class="refresh-options">
       <label>
         <input type="checkbox" v-model="refreshOptions.m3u8" />
         刷新 M3U8 链接
       </label>
       <label>
         <input type="checkbox" v-model="refreshOptions.metadata" />
         刷新元数据
       </label>
       <label>
         <input type="checkbox" v-model="refreshOptions.translate" />
         重新翻译标题
       </label>
       <button @click="executeRefresh">确认刷新</button>
     </div>
   </div>
   ```

3. **API 调用**：
   ```javascript
   async function executeRefresh() {
     const params = {
       refresh_m3u8: refreshOptions.m3u8,
       refresh_metadata: refreshOptions.metadata,
       retranslate: refreshOptions.translate
     }
     await resourceApi.refresh(avid.value, params)
   }
   ```

---

### F4: 下载页任务标题缓存优化

**需求描述**：下载页的正在下载任务的标题有 bug，有时已经得到了响应却不应用，考虑维护一个哈希表缓存（avid: title）。

**评估**：
- **合理性**：✅ 优秀。解决异步更新问题，提升用户体验。
- **可行性**：✅ 高。当前 `websocket.js` 已有 `metadataCache` (Set)，需要改为 Map。
- **工作量**：🔹 低（约 1-2 小时）

**实施计划**：

1. **修改文件**：[src/stores/websocket.js](vue_frontend/src/stores/websocket.js)

2. **核心改动**：
   ```javascript
   // 将 Set 改为 Map，存储 avid -> title
   const titleCache = ref(new Map())  // 替代原来的 metadataCache

   // 更新任务数据时，先从缓存中应用已有的 title
   function updateTaskData(data) {
     activeTasks.value = (data.active_tasks || []).map(task => ({
       ...task,
       title: task.title || titleCache.value.get(task.avid) || null
     }))
     pendingTasks.value = (data.pending_tasks || []).map(task => ({
       ...task,
       title: task.title || titleCache.value.get(task.avid) || null
     }))
     // ... 其余逻辑
     fetchMissingMetadata()
   }

   // 获取到元数据后缓存
   async function fetchMissingMetadata() {
     for (const task of allTasks) {
       if (!task.title && task.avid && !titleCache.value.has(task.avid)) {
         try {
           const response = await resourceApi.getMetadata(task.avid)
           if (response.data?.title) {
             // 存入缓存
             titleCache.value.set(task.avid, response.data.title)
             // 同步更新当前任务列表
             updateTaskTitle(task.avid, response.data.title)
           }
         } catch (error) {
           // 不从缓存移除，下次重试
         }
       }
     }
   }
   ```

---

### F5: 增加批量添加功能

**需求描述**：增加批量添加资源功能。

**评估**：
- **合理性**：✅ 良好。提高效率，适合批量导入场景。
- **可行性**：✅ 高。后端已有 `/api/resources/batch` 接口支持。
- **工作量**：🔸 中（约 3-4 小时）

**实施计划**：

1. **修改文件**：[src/views/AddResourceView.vue](vue_frontend/src/views/AddResourceView.vue)

2. **UI 设计**：
   ```vue
   <!-- 添加切换模式 -->
   <div class="mode-toggle">
     <button :class="{ active: mode === 'single' }" @click="mode = 'single'">
       单个添加
     </button>
     <button :class="{ active: mode === 'batch' }" @click="mode = 'batch'">
       批量添加
     </button>
   </div>

   <!-- 批量添加输入框 -->
   <div v-if="mode === 'batch'" class="batch-input">
     <textarea
       v-model="batchAvids"
       placeholder="输入多个 AVID，每行一个或用逗号/空格分隔&#10;例如：&#10;ABC-001&#10;DEF-002, GHI-003"
       rows="8"
     ></textarea>
     <div class="batch-info">
       已识别 {{ parsedAvids.length }} 个 AVID
     </div>
   </div>
   ```

3. **逻辑实现**：
   ```javascript
   const batchAvids = ref('')

   const parsedAvids = computed(() => {
     return batchAvids.value
       .split(/[\n,\s]+/)
       .map(s => s.trim().toUpperCase())
       .filter(s => s.length > 0)
   })

   async function handleBatchSubmit() {
     const avids = parsedAvids.value
     if (avids.length === 0) return

     submitting.value = true
     const results = await resourceApi.batchAdd(avids, source.value)
     // 显示结果摘要
     const success = results.filter(r => r.code === 200 || r.code === 201)
     const failed = results.filter(r => r.code >= 400)
     toastStore.info(`成功 ${success.length}，失败 ${failed.length}`)
   }
   ```

---

### F6: 批量下载超时动态延长

**需求描述**：批量下载的超时应该根据任务数而延长。

**评估**：
- **合理性**：✅ 良好。避免大批量任务因超时而失败。
- **可行性**：✅ 高。前端 API 调用层修改即可。
- **工作量**：🔹 低（约 0.5-1 小时）

**实施计划**：

1. **修改文件**：[src/api/index.js](vue_frontend/src/api/index.js)（或 resourceApi 所在文件）

2. **实现方案**：
   ```javascript
   // 批量下载 API
   async function batchSubmitDownload(avids) {
     // 基础超时 10 秒，每个任务增加 2 秒
     const timeout = 10000 + avids.length * 2000
     return await axios.post('/api/downloads/batch_submit', { avids }, { timeout })
   }

   // 批量添加资源
   async function batchAdd(avids, source) {
     const timeout = 15000 + avids.length * 3000  // 每个资源需要更多时间抓取
     return await axios.post('/api/resources/batch', {
       operations: avids.map(avid => ({ action: 'add', avid, source }))
     }, { timeout })
   }
   ```

---

## 二、后端变更

### B1: 支持细粒度刷新 API

**需求描述**：支持刷新 API（刷新 m3u8、刷新元数据、重新翻译文本），可在原有 API 上增加参数或分离成新 API。

**评估**：
- **合理性**：✅ 良好。细粒度控制减少不必要的网络请求和处理开销。
- **可行性**：✅ 中高。需要修改现有 `RefreshResourceView` 和批量操作逻辑。
- **工作量**：🔸 中（约 4-6 小时）

**实施计划**：

1. **API 设计**（推荐在原 API 上增加参数）：
   ```
   POST /nassav/api/resource/refresh/{avid}
   Content-Type: application/json

   {
     "refresh_m3u8": true,      // 是否刷新 m3u8 链接
     "refresh_metadata": true,  // 是否刷新元数据（从 source 重新抓取）
     "retranslate": false       // 是否重新翻译标题
   }
   ```

2. **修改文件**：[nassav/views.py](django_backend/nassav/views.py#L803)

3. **实现逻辑**：
   ```python
   class RefreshResourceView(APIView):
       def post(self, request, avid):
           avid = avid.upper()
           # 解析参数，默认全部刷新
           refresh_m3u8 = request.data.get('refresh_m3u8', True)
           refresh_metadata = request.data.get('refresh_metadata', True)
           retranslate = request.data.get('retranslate', False)

           resource = AVResource.objects.filter(avid=avid).first()
           if not resource:
               return build_response(404, '资源不存在', None)

           result = {}

           # 刷新元数据和 m3u8
           if refresh_metadata or refresh_m3u8:
               source = resource.source
               if not source:
                   return build_response(400, '没有 source 信息', None)
               info, downloader, html = source_manager.get_info_from_source(avid, source)
               if refresh_metadata:
                   # 更新元数据字段
                   result['metadata_refreshed'] = True
               if refresh_m3u8:
                   resource.m3u8 = info.get('m3u8', resource.m3u8)
                   result['m3u8_refreshed'] = True
               resource.save()

           # 重新翻译
           if retranslate:
               from .tasks import translate_title_task
               translate_title_task.delay(avid)
               result['translation_queued'] = True

           return build_response(200, 'success', result)
   ```

4. **批量操作支持**：同样在 `ResourcesBatchOperationView` 中增加参数支持。

---

### B2: 任务队列显示完整列表

**需求描述**：目前的 `task_status` 只显示一个活跃中任务和一个排队中任务，无论有多少任务正在排队都只显示一个。

**评估**：
- **合理性**：✅ 优秀。用户需要了解完整的队列状态。
- **可行性**：✅ 中高。当前实现已返回列表，可能是数据截断或前端显示问题。
- **工作量**：🔸 中（约 2-4 小时，需要调试定位）

**分析**：

查看 [nassav/tasks.py](django_backend/nassav/tasks.py#L146-L210) 中的 `get_task_queue_status()` 函数，当前实现确实返回完整的 `active_tasks` 和 `pending_tasks` 列表。问题可能在于：

1. **Celery inspect 的限制**：`insp.active()` / `insp.scheduled()` / `insp.reserved()` 可能只返回部分任务
2. **消息广播时数据被截断**

**实施计划**：

1. **修改文件**：
   - [nassav/tasks.py](django_backend/nassav/tasks.py)
   - [nassav/consumers.py](django_backend/nassav/consumers.py)

2. **改进方案**：
   ```python
   # 方案 A: 使用 Redis 维护完整任务列表
   def add_task_to_queue(avid: str, task_id: str):
       """添加任务到 Redis 队列记录"""
       redis_client = get_redis_client()
       queue_key = "nassav:task_queue"
       redis_client.hset(queue_key, avid.upper(), json.dumps({
           'task_id': task_id,
           'avid': avid.upper(),
           'state': 'PENDING',
           'created_at': time.time()
       }))

   def remove_task_from_queue(avid: str):
       """从 Redis 队列记录中移除任务"""
       redis_client = get_redis_client()
       queue_key = "nassav:task_queue"
       redis_client.hdel(queue_key, avid.upper())

   def get_full_task_queue():
       """获取完整任务队列"""
       redis_client = get_redis_client()
       queue_key = "nassav:task_queue"
       all_tasks = redis_client.hgetall(queue_key)
       # 解析并返回完整列表
       return [json.loads(v) for v in all_tasks.values()]
   ```

3. **在任务提交和完成时更新队列**：
   - `submit_download_task()`: 调用 `add_task_to_queue()`
   - `download_video_task()` 完成时: 调用 `remove_task_from_queue()`

4. **WebSocket 推送完整列表**：
   ```python
   def send_queue_status():
       queue = get_full_task_queue()
       # 区分 active 和 pending
       active = [t for t in queue if t['state'] == 'STARTED']
       pending = [t for t in queue if t['state'] == 'PENDING']
       send_task_update('queue_status', {
           'active_tasks': active,
           'pending_tasks': pending,
           'active_count': len(active),
           'pending_count': len(pending),
           'total_count': len(queue)
       })
   ```

---

### B3: 翻译质量优化

**需求描述**：翻译质量很差，可能是 prompt 问题。

**评估**：
- **合理性**：✅ 优秀。翻译质量直接影响用户体验。
- **可行性**：⚠️ 中等。翻译质量受模型能力、prompt 设计、后处理等多因素影响。
- **工作量**：🔺 高（约 4-8 小时，含测试调优）

**问题分析**：

根据示例：
```
原标题: 大嫌いな変態上司の乳首こねくりハラスメントでチクイキするまで毎日イジくり犯●れた私… 北野未奈
翻译结果包含: "中文翻译：", "注：日语中的某些词汇..."
```

主要问题：
1. **模型输出了额外的解释文本**：prompt 需要更强调"只返回翻译结果"
2. **部分日语词汇未翻译**：模型能力限制或 prompt 不够明确

**实施计划**：

1. **修改文件**：
   - [nassav/translator/OllamaTranslator.py](django_backend/nassav/translator/OllamaTranslator.py)
   - [config/config.yaml](django_backend/config/config.yaml)

2. **优化 Prompt**：
   ```python
   # 方案 1: 更明确的指令
   prompt_template = """你是一个专业的日语翻译。请将以下日语标题翻译成简体中文。

   要求：
   1. 只输出翻译后的中文标题，不要添加任何解释、注释或其他内容
   2. 人名保留日语读音的中文对应写法
   3. 确保翻译完整，不遗漏任何内容

   日语标题：{text}

   中文翻译："""

   # 方案 2: Few-shot 示例
   prompt_template = """将日语标题翻译成中文，只返回翻译结果。

   示例：
   日语：美人OL強制ザーメン搾り
   中文：美人OL强制精液榨取

   日语：{text}
   中文："""
   ```

3. **后处理清洗**：
   ```python
   def clean_translation(text: str) -> str:
       """清洗翻译结果，移除多余内容"""
       if not text:
           return text

       # 移除常见的前缀
       prefixes = ['中文翻译：', '中文：', '翻译：', '译文：']
       for prefix in prefixes:
           if text.startswith(prefix):
               text = text[len(prefix):]

       # 移除解释性后缀（如 "注：..." "备注：..."）
       for marker in ['注：', '备注：', '说明：', '\n\n']:
           idx = text.find(marker)
           if idx > 0:
               text = text[:idx]

       return text.strip()
   ```

4. **模型参数调整**：
   ```python
   'options': {
       'temperature': 0.05,  # 进一步降低随机性
       'top_p': 0.8,
       'top_k': 10,
       'num_predict': 200,  # 限制输出长度
   }
   ```

5. **考虑更换/升级模型**：
   - 当前使用 `qwen2.5:7b`，可尝试 `qwen2.5:14b` 或 `qwen2.5:32b`（如硬件允许）
   - 或尝试其他翻译专用模型

---

### B4: source_title 规范化

**需求描述**：维护 source_title，如果不以 avid.upper 开头则手动补充，同时添加现有标题批处理脚本。

**评估**：
- **合理性**：✅ 良好。统一标题格式，便于搜索和展示。
- **可行性**：✅ 高。数据库已有 `source_title` 字段。
- **工作量**：🔹 低（约 1-2 小时）

**实施计划**：

1. **修改文件**：
   - [nassav/services.py](django_backend/nassav/services.py)（保存资源时处理）
   - 新建 [scripts/fix_source_titles.py](django_backend/scripts/fix_source_titles.py)

2. **保存时自动处理**：
   ```python
   def normalize_source_title(avid: str, source_title: str) -> str:
       """规范化 source_title，确保以 AVID 开头"""
       if not source_title:
           return source_title
       avid_upper = avid.upper()
       if not source_title.upper().startswith(avid_upper):
           return f"{avid_upper} {source_title}"
       return source_title
   ```

3. **批处理脚本**：
   ```python
   # scripts/fix_source_titles.py
   """修复现有资源的 source_title 格式"""

   from nassav.models import AVResource

   def fix_all_source_titles():
       resources = AVResource.objects.exclude(source_title__isnull=True).exclude(source_title='')
       fixed = 0
       for r in resources:
           avid_upper = r.avid.upper()
           if r.source_title and not r.source_title.upper().startswith(avid_upper):
               r.source_title = f"{avid_upper} {r.source_title}"
               r.save(update_fields=['source_title'])
               fixed += 1
               print(f"Fixed: {r.avid}")
       print(f"Total fixed: {fixed}")

   if __name__ == '__main__':
       fix_all_source_titles()
   ```

---

## 三、实施时间线

### 第一周（P1 优先级）

| 天数 | 任务 | 预计耗时 |
|------|------|----------|
| Day 1 | F1 资源卡下载按钮状态优化 | 2h |
| Day 1 | F4 下载页任务标题缓存优化 | 2h |
| Day 2-3 | F2 详情页返回保留页码状态 | 4h |
| Day 3-4 | B2 任务队列显示完整列表 | 4h |

### 第二周（P2 优先级）

| 天数 | 任务 | 预计耗时 |
|------|------|----------|
| Day 1-2 | B1 支持细粒度刷新 API | 5h |
| Day 2-3 | F3 刷新动作多选支持（前端部分） | 3h |
| Day 3-4 | B3 翻译质量优化 | 6h |
| Day 4 | F5 批量添加功能 | 3h |
| Day 4 | F6 批量下载超时动态延长 | 1h |

### 第三周（P3 优先级 + 测试）

| 天数 | 任务 | 预计耗时 |
|------|------|----------|
| Day 1 | B4 source_title 规范化 | 2h |
| Day 2-3 | 集成测试 & Bug 修复 | 6h |
| Day 4 | 文档更新 | 2h |

---

## 四、风险与注意事项

1. **B2 任务队列显示**：需要先确认是后端数据问题还是前端显示问题，建议先通过日志排查。

2. **B3 翻译质量**：翻译质量优化可能需要多轮测试调优，建议准备一组测试用例（如 20 个典型标题）作为评估基准。

3. **F2 页码状态保留**：如果同时有搜索、筛选等状态需要保留，建议统一设计状态管理方案。

4. **API 兼容性**：新增参数时保持向后兼容，旧版前端调用应能正常工作。

---

## 五、测试检查清单

### 前端测试
- [ ] F1: 未下载资源卡显示彩色下载按钮，可点击
- [ ] F1: 已下载资源卡显示灰色下载按钮，不可点击
- [ ] F2: 从详情页返回列表页，页码保持
- [ ] F2: 刷新页面后页码从 URL 恢复
- [ ] F3: 刷新菜单可多选，API 调用正确
- [ ] F4: 下载页任务标题及时显示，不闪烁
- [ ] F5: 批量添加可解析多种格式输入
- [ ] F6: 批量操作超时合理

### 后端测试
- [ ] B1: 单独刷新 m3u8 / 元数据 / 翻译均正常
- [ ] B2: 队列中有多个任务时全部返回
- [ ] B3: 翻译结果无多余文本，质量提升
- [ ] B4: 新保存和批处理的 source_title 格式正确
