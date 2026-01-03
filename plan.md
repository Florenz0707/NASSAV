# NASSAV 项目开发计划

## 项目概览
NASSAV 是一个功能完整的 AV 资源管理系统，包含 Django 后端（异步下载队列 + WebSocket）和 Vue3 前端（现代化界面），支持多源资源获取、元数据刮削、实时进度追踪等功能。

## TODO 项目分析与优先级排序

根据 TODO.md 中的待办事项，按照**优先级**（第一要素）和**难度**（第二要素）进行排序和评估。

---

## 一、高优先级（P0 - 影响用户体验的核心功能问题）

### 1.1 【BUG修复】视频排序接口返回未下载资源 🔴 P0 难度：★☆☆

**问题描述**：
- 接口 `GET /nassav/api/resources/?sort_by=video_create_time` 被调用时，未下载的视频也会被返回
- 这导致前端按视频创建时间排序时，会显示还没有下载的资源

**问题分析**：
- 在 `views.py` 中的资源列表接口，`video_create_time` 排序逻辑没有正确过滤 `file_exists=False` 的记录
- 或者排序字段 `video_saved_at` 为 NULL 的记录没有被排除

**技术方案**：
1. 在 `django_backend/nassav/views.py` 的 `ResourceListView` 中，当 `sort_by=video_create_time` 时，添加额外的过滤条件：
   ```python
   if sort_by == 'video_create_time':
       queryset = queryset.filter(file_exists=True, video_saved_at__isnull=False)
   ```
2. 或者修改前端，明确在按视频时间排序时，自动设置 `status=downloaded` 参数

**工作量评估**：0.5 小时
- 代码修改：1 处（后端视图）
- 测试：手动测试 + 添加单元测试

**可行性**：✅ 完全可行，逻辑清晰
**优先级理由**：这是一个会导致用户困惑的 BUG，影响排序功能的正确性

---

### 1.2 【BUG修复】Javbus 女优名解析错误 🔴 P0 难度：★★☆

**问题描述**：
- 以 https://www.javbus.com/JUR-448 为例
- 女优名"めぐり（藤浦めぐ）"会被刮削成"めぐり（藤"
- 原因是括号内容被截断

**问题分析**：
- 在 `django_backend/nassav/scraper/Javbus.py` 中，解析演员名称的正则表达式可能匹配有问题
- 当前代码：
  ```python
  actor_matches = re.findall(
      r'<a class="avatar-box"[^>]*>\s*<div[^>]*>\s*'
      r"<img[^>]*>\s*</div>\s*<span>([^<]+)</span>",
      html,
  )
  ```
- `[^<]+` 这个模式在遇到嵌套或特殊字符时可能被截断
- 需要查看实际 HTML 结构确认问题根源

**技术方案**：
1. 使用浏览器开发者工具或 curl 获取 JUR-448 的真实 HTML 源码
2. 分析演员名称的 HTML 结构，确认是否存在嵌套标签或实体编码问题
3. 调整正则表达式或使用 BeautifulSoup 解析：
   ```python
   from bs4 import BeautifulSoup
   soup = BeautifulSoup(html, 'html.parser')
   actor_boxes = soup.select('a.avatar-box span')
   actors = [box.get_text(strip=True) for box in actor_boxes]
   ```
4. 添加 HTML 实体解码处理（如 `&lt;` `&gt;` 等）
5. 添加测试用例，使用 JUR-448 的 HTML 作为测试数据

**工作量评估**：2 小时
- 调研分析：0.5 小时（获取并分析真实 HTML）
- 代码修改：1 小时（修改解析逻辑 + 添加实体解码）
- 测试：0.5 小时（单元测试 + 手动验证多个案例）

**可行性**：✅ 完全可行，已知问题根源
**优先级理由**：数据质量问题，影响演员库的准确性

---

## 二、中优先级（P1 - 改善用户体验的功能增强）

### 2.1 【功能增强】前端增加设置页（Cookie 管理） 🟡 P1 难度：★★☆

**问题描述**：
- 需要增加设置页，主要用于迁移 Cookie 设置功能
- 并加入 Cookie 展示功能（查看当前已设置的 Cookie）

**当前状态**：
- Cookie 设置功能目前在"添加资源"页面（`AddResourceView.vue`）中
- 用户需要在添加资源时才能设置 Cookie，体验不友好
- 缺少查看已设置 Cookie 的功能

**技术方案**：
1. **后端改动**（如需要）：
   - 检查是否已有 `GET /nassav/api/source/cookie` 接口用于获取已设置的 Cookie 列表
   - 如无，需添加该接口：
     ```python
     # views.py
     class SourceCookieListView(APIView):
         def get(self, request):
             cookies = SourceCookie.objects.all()
             serializer = SourceCookieSerializer(cookies, many=True)
             return Response({"code": 200, "data": serializer.data})
     ```

2. **前端改动**：
   - 创建新路由 `/settings` 和对应组件 `SettingsView.vue`
   - 在设置页中添加 Cookie 管理模块：
     - 展示当前所有源的 Cookie 设置状态（表格形式）
     - 每个源支持：查看、编辑、删除、自动获取
   - 修改导航栏，添加"设置"入口
   - 从 `AddResourceView.vue` 中移除或保留 Cookie 弹窗（保留可以作为快捷方式）

3. **UI 设计**：
   ```
   设置页布局：
   - 左侧侧边栏：Cookie 管理、其他设置（预留）
   - 右侧主内容区：
     - Cookie 管理表格
       | 下载源 | Cookie 状态 | 更新时间 | 操作 |
       |--------|------------|----------|------|
       | MissAV | ✅ 已设置  | 2026-01-03 | 查看/编辑/删除 |
       | Jable  | ❌ 未设置  | -        | 设置/自动获取 |
   ```

**工作量评估**：3.5 小时
- 后端接口（如需要）：0.5 小时
- 前端页面开发：2.5 小时
  - 路由和组件骨架：0.5 小时
  - Cookie 管理表格：1.5 小时
  - 导航栏修改：0.5 小时
- 测试：0.5 小时

**可行性**：✅ 完全可行，UI 设计和接口都比较清晰
**优先级理由**：改善 Cookie 管理体验，符合用户习惯（设置应该独立出来）

---

### 2.2 【功能增强】获取 Javbus 女优头像 🟡 P1 难度：★★★

**问题描述**：
- Javbus HTML 中包含女优头像：`<img src="/pics/actress/305_a.jpg" title="めぐり（藤浦めぐ）">`
- 可以提取并保存女优头像，用于前端演员库展示

**技术方案**：
1. **后端改动**：
   - 在 `Actor` 模型中添加头像字段：
     ```python
     class Actor(models.Model):
         name = models.CharField(max_length=200, unique=True, db_index=True)
         avatar_url = models.URLField(blank=True, null=True)  # 新增
         avatar_filename = models.CharField(max_length=255, blank=True, null=True)  # 新增
         updated_at = models.DateTimeField(auto_now=True)  # 新增
     ```
   - 在 `Javbus.py` 中提取头像 URL：
     ```python
     # 在 parse_html 方法中添加
     actor_avatars = {}
     avatar_matches = re.findall(
         r'<img src="(/pics/actress/[^"]+)"\s+title="([^"]+)"',
         html
     )
     for avatar_path, actor_name in avatar_matches:
         actor_avatars[actor_name] = f"https://{self.domain}{avatar_path}"
     scrape_data['actor_avatars'] = actor_avatars
     ```
   - 在保存演员时同步保存头像信息（异步下载或保存 URL）
   - 添加演员头像 API：`GET /nassav/api/actors/{id}/avatar`

2. **前端改动**：
   - 在演员列表和演员详情中显示头像
   - 如果没有头像，使用默认占位图

3. **数据库迁移**：
   - 创建 Django migration 添加新字段
   - 编写脚本批量更新现有演员的头像（从已有的刮削数据）

**工作量评估**：6 小时
- 后端开发：4 小时
  - 数据库模型修改和迁移：1 小时
  - 刮削器修改：1 小时
  - 头像下载和存储逻辑：1.5 小时
  - API 接口：0.5 小时
- 前端开发：1.5 小时
- 数据迁移脚本：0.5 小时

**可行性**：✅ 完全可行，但需要处理存储和性能问题
**注意事项**：
- 头像文件可能较多，需要考虑存储空间（建议：只保存 URL，按需加载）
- 跨域问题：Javbus 图片可能有防盗链，需要通过后端代理或设置 Referer
- 考虑缓存策略（头像一般不变）

**优先级理由**：提升界面美观度和用户体验，但非核心功能

---

### 2.3 【功能增强】使用 Javbus 获取封面图 🟡 P1 难度：★★☆

**问题描述**：
- 当前封面图来源于各个下载源（MissAV、Jable 等）
- 可以改为从 Javbus 获取封面图，统一来源，质量可能更稳定

**当前状态分析**：
- 封面图已存储在 `resource/cover/{AVID}.jpg`
- 元数据中包含 `cover_filename` 字段
- 当前封面获取流程：在添加资源时，从选定的 source 下载封面

**技术方案**：
1. **在 Javbus 刮削器中提取封面 URL**：
   ```python
   # Javbus.py parse_html 方法中添加
   cover_match = re.search(
       r'<a[^>]*class="bigImage"[^>]*href="([^"]+)"', html
   )
   if cover_match:
       scrape_data['cover_url'] = cover_match.group(1)
   ```

2. **修改封面下载逻辑**：
   - 在 `services.py` 或 `tasks.py` 中
   - 优先使用 Javbus 的封面 URL
   - 如果 Javbus 没有，再回退到 source 的封面

3. **支持封面刷新**：
   - 在刷新元数据时，同步更新封面（如果 Javbus 提供了更高质量的）

**工作量评估**：3 小时
- 刮削器修改：1 小时
- 封面下载逻辑修改：1.5 小时
- 测试：0.5 小时

**可行性**：✅ 完全可行
**潜在问题**：
- Javbus 封面可能有防盗链（需要设置 Referer）
- 封面尺寸和质量可能与各个源不同
- 需要考虑兼容性（如果 Javbus 无封面，要有降级方案）

**优先级理由**：统一封面来源有利于维护，但不是紧急需求

---

## 三、低优先级（P2 - 长期优化和架构改进）

### 3.1 【架构优化】`avid: title` 缓存更新机制 🟢 P2 难度：★★★

**问题描述**：
- `avid: title` 缓存有时太顽固，无法及时更新
- 当标题被修改（如翻译更新）后，前端显示的可能还是旧标题

**问题分析**：
- 前端可能使用了 localStorage 或 sessionStorage 缓存
- 后端可能使用了 Redis 缓存或内存缓存
- 缓存失效策略不够智能

**技术方案**（需深入调研）：
1. **前端缓存问题**：
   - 检查前端代码（stores/ 或 components/）是否有缓存逻辑
   - 使用 Pinia 的 `$reset()` 或设置合理的缓存过期时间
   - 在标题更新后，主动清除缓存：
     ```javascript
     // 在刷新元数据成功后
     resourceStore.invalidateTitleCache(avid)
     ```

2. **后端缓存问题**：
   - 检查是否使用了 Django 的缓存框架或 Redis
   - 在更新资源标题后，主动删除缓存键：
     ```python
     from django.core.cache import cache
     cache.delete(f"resource_title_{avid}")
     ```
   - 或使用数据库信号（`post_save`）自动清除缓存

3. **使用 ETag 机制**：
   - 后端在资源更新后，更新 ETag
   - 前端根据 ETag 判断是否需要刷新缓存

**工作量评估**：4 小时
- 调研现有缓存机制：1 小时
- 前端缓存优化：1.5 小时
- 后端缓存优化：1.5 小时
- 测试：0.5 小时（需要模拟各种更新场景）

**可行性**：⚠️ 中等可行，需要先定位问题根源
**优先级理由**：影响较小，且可以通过手动刷新页面解决

---

### 3.2 【架构优化】增强配置灵活性与热更新 🟢 P2 难度：★★★★

**问题描述**：
- 希望配置更灵活，尽量可以做到不重启热更新
- 增强前端配置功能

**当前状态**：
- 配置文件：`django_backend/config/config.yaml`
- 配置加载：Django 启动时通过 `settings.py` 加载
- 配置项：Proxy、Scraper、Source、DisplayTitle、Translator 等

**技术方案**：
1. **后端配置热更新**：
   - 方案 A：使用 Django 信号 + 文件监听
     ```python
     # 使用 watchdog 库监听 config.yaml 变化
     from watchdog.observers import Observer
     from watchdog.events import FileSystemEventHandler

     class ConfigReloadHandler(FileSystemEventHandler):
         def on_modified(self, event):
             if 'config.yaml' in event.src_path:
                 reload_config()
     ```
   - 方案 B：定期轮询配置文件的修改时间
   - 方案 C：提供 API 接口手动触发配置重载：
     ```python
     POST /nassav/api/admin/reload-config
     ```

2. **配置管理后台（前端）**：
   - 在设置页中添加"配置管理"模块
   - 可视化编辑配置（下拉选择、开关、输入框）
   - 支持实时保存并应用配置（调用后端重载接口）
   - 配置项分类：
     - 下载源权重设置
     - 刮削器域名设置
     - 翻译器模型选择
     - 显示标题类型（source_title / translated_title / title）
     - 代理设置

3. **配置验证和回滚**：
   - 修改配置前备份
   - 配置格式验证（YAML schema）
   - 如果配置导致服务异常，自动回滚

**工作量评估**：12 小时（大型改动）
- 后端热更新机制：4 小时
- 配置 API 接口：2 小时
- 前端配置管理 UI：5 小时
- 测试和文档：1 小时

**可行性**：⚠️ 中等可行，架构改动较大
**潜在风险**：
- 热更新可能导致进程状态不一致（尤其是 Celery Worker）
- 配置错误可能导致服务崩溃
- 需要完善的错误处理和降级机制

**优先级理由**：属于"锦上添花"的功能，当前可以通过重启服务解决

---

## 四、开发计划时间表

### 第一阶段（本周，约 8 小时）- 紧急 BUG 修复

| 任务 | 优先级 | 难度 | 预计工作量 | 负责人 | 状态 |
|------|--------|------|-----------|--------|------|
| 修复视频排序接口返回未下载资源 | P0 | ★☆☆ | 0.5h | - | 待开始 |
| 修复 Javbus 女优名解析错误 | P0 | ★★☆ | 2h | - | 待开始 |

**目标**：解决影响用户体验的核心 BUG

---

### 第二阶段（下周，约 10 小时）- 功能增强

| 任务 | 优先级 | 难度 | 预计工作量 | 负责人 | 状态 |
|------|--------|------|-----------|--------|------|
| 前端增加设置页（Cookie 管理） | P1 | ★★☆ | 3.5h | - | 待开始 |
| 使用 Javbus 获取封面图 | P1 | ★★☆ | 3h | - | 待开始 |

**目标**：改善用户体验，完善功能

---

### 第三阶段（中期，约 10 小时）- 功能增强与优化

| 任务 | 优先级 | 难度 | 预计工作量 | 负责人 | 状态 |
|------|--------|------|-----------|--------|------|
| 获取 Javbus 女优头像 | P1 | ★★★ | 6h | - | 待开始 |
| 优化 `avid: title` 缓存更新机制 | P2 | ★★★ | 4h | - | 待开始 |

**目标**：提升界面美观度，优化缓存机制

---

### 第四阶段（长期，约 12 小时）- 架构优化

| 任务 | 优先级 | 难度 | 预计工作量 | 负责人 | 状态 |
|------|--------|------|-----------|--------|------|
| 增强配置灵活性与热更新 | P2 | ★★★★ | 12h | - | 待规划 |

**目标**：提升系统可维护性和灵活性

---

## 五、风险评估与注意事项

### 5.1 技术风险

1. **Javbus 反爬虫机制**：
   - 获取封面和头像时可能遇到 Cloudflare 防护
   - 建议使用 curl_cffi 保持一致性
   - 设置合理的 User-Agent 和 Referer

2. **数据库迁移风险**：
   - 添加演员头像字段需要数据库迁移
   - 建议先在开发环境测试，确保不影响现有数据

3. **缓存一致性问题**：
   - 多处缓存（前端、后端、Redis）需要统一管理
   - 建议使用事件总线或发布订阅模式同步缓存失效

### 5.2 性能考量

1. **演员头像存储**：
   - 如果保存本地，需要考虑存储空间（建议：只保存 URL）
   - 如果代理加载，需要考虑带宽和延迟（建议：使用 CDN 或缓存）

2. **封面图下载**：
   - 从 Javbus 获取封面可能比从原 source 慢
   - 建议异步下载，不阻塞主流程

3. **配置热更新**：
   - 文件监听可能消耗 CPU（建议：使用定时轮询或手动触发）
   - Celery Worker 配置更新需要重启才能生效（当前无法热更新）

### 5.3 兼容性

1. **降级方案**：
   - Javbus 封面/头像获取失败时，回退到原有逻辑
   - 配置热更新失败时，保持当前配置不变

2. **数据迁移兼容性**：
   - 新增字段使用 `null=True, blank=True` 确保兼容性
   - 提供数据修复脚本，批量更新历史数据

---

## 六、总结

### 6.1 开发优先级总览

```
P0（紧急）：
  1. 修复视频排序接口 BUG（0.5h）⭐
  2. 修复女优名解析错误（2h）⭐

P1（重要）：
  3. 前端设置页 + Cookie 管理（3.5h）
  4. Javbus 封面图获取（3h）
  5. Javbus 女优头像获取（6h）

P2（优化）：
  6. 缓存更新机制优化（4h）
  7. 配置灵活性与热更新（12h）
```

### 6.2 总工作量

- **第一阶段（P0）**：2.5 小时 - 本周内完成
- **第二阶段（P1 前半）**：6.5 小时 - 下周完成
- **第三阶段（P1 后半 + P2 前半）**：10 小时 - 两周内完成
- **第四阶段（P2 后半）**：12 小时 - 长期规划

**总计**：约 31 小时

### 6.3 建议的迭代顺序

1. **立即行动**：修复 P0 的两个 BUG（2.5h）
2. **下周发布**：完成设置页和封面图获取（6.5h）
3. **月底前**：完成女优头像和缓存优化（10h）
4. **季度目标**：配置热更新（12h，可拆分为多个 Sprint）

### 6.4 可选扩展

如果时间充裕，可以考虑以下额外功能：
- 演员头像批量更新脚本（2h）
- 配置导入/导出功能（1.5h）
- 配置版本管理（Git 集成）（4h）
- WebSocket 推送配置变更通知（2h）

---

## 附录：相关文件路径

### 后端关键文件
- 视图：`django_backend/nassav/views.py`
- 模型：`django_backend/nassav/models.py`
- Javbus 刮削器：`django_backend/nassav/scraper/Javbus.py`
- 配置文件：`django_backend/config/config.yaml`
- 任务队列：`django_backend/nassav/tasks.py`

### 前端关键文件
- 添加资源页：`vue_frontend/src/views/AddResourceView.vue`
- 演员列表：`vue_frontend/src/views/ActorsView.vue`
- 路由配置：`vue_frontend/src/router/`
- API 调用：`vue_frontend/src/api/`

---

**生成时间**：2026-01-03
**项目版本**：基于当前 main 分支
**文档维护**：随项目进展更新此计划
