# 调试和测试接口文档

本文档描述仅在开发/调试模式下可用的特殊接口。这些接口用于测试和开发，不应在生产环境中使用。

---

## 模拟下载接口

### 概述

模拟下载接口允许在不实际下载视频的情况下测试完整的下载流程，包括任务队列、进度更新、WebSocket 通知等功能。

### 启用条件

- **必须在 DEBUG 模式下**：在 `django_backend/.env` 文件中设置 `DEBUG=True`
- 非 DEBUG 模式下调用此接口会返回 `403 Forbidden` 错误

### 端点信息

```
POST /nassav/api/downloads/mock/{avid}
```

### 请求参数

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| avid | string | 是 | 资源 AVID（必须在数据库中存在） |

**请求体（JSON，可选）：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| duration | integer | 否 | 30 | 模拟下载持续时间（秒），范围：1-300 |

### 请求示例

**基本请求（使用默认 30 秒）：**

```bash
curl -X POST http://localhost:8000/nassav/api/downloads/mock/SSIS-465 \
  -H "Content-Type: application/json"
```

**指定持续时间：**

```bash
curl -X POST http://localhost:8000/nassav/api/downloads/mock/SSIS-465 \
  -H "Content-Type: application/json" \
  -d '{
    "duration": 60
  }'
```

**JavaScript 示例：**

```javascript
// 使用默认 30 秒
fetch('/nassav/api/downloads/mock/SSIS-465', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  }
})
.then(response => response.json())
.then(data => console.log(data));

// 指定持续时间
fetch('/nassav/api/downloads/mock/SSIS-465', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    duration: 45
  })
})
.then(response => response.json())
.then(data => console.log(data));
```

### 响应格式

**成功响应（202 Accepted）：**

```json
{
  "code": 202,
  "message": "模拟下载任务已提交",
  "data": {
    "avid": "SSIS-465",
    "task_id": "abc-123-def-456",
    "status": "pending",
    "duration": 30,
    "mock": true
  }
}
```

**错误响应示例：**

| HTTP 状态码 | Code | 说明 | 示例 |
|------------|------|------|------|
| 403 | 403 | DEBUG 模式未启用 | `{"code": 403, "message": "此接口仅在 DEBUG 模式下可用", "data": null}` |
| 404 | 404 | 资源不存在 | `{"code": 404, "message": "SSIS-465 的元数据不存在", "data": null}` |
| 409 | 409 | 任务已存在 | `{"code": 409, "message": "下载任务已存在", "data": null}` |
| 400 | 400 | 参数错误 | `{"code": 400, "message": "持续时间必须在 1-300 秒之间", "data": null}` |
| 500 | 500 | 服务器错误 | `{"code": 500, "message": "提交失败: ...", "data": null}` |

### 功能特性

1. **完整模拟真实下载流程**
   - 任务提交和队列管理
   - 任务锁和去重检查
   - 进度更新（每秒更新一次）
   - WebSocket 实时通知
   - 任务完成/失败通知

2. **进度更新**
   - 百分比从 0% 到 100% 线性递增
   - 模拟下载速度（MB/s）
   - 可通过 WebSocket 或轮询接口获取实时进度

3. **不产生副作用**
   - 不下载任何实际文件
   - 不修改数据库中的 `file_exists` 字段
   - 任务完成后自动清理进度和锁

### 监控进度

模拟下载任务提交后，可以通过以下方式监控进度：

#### 1. WebSocket 实时通知

连接到 WebSocket：

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/tasks/');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'task_started') {
    console.log('任务开始:', data.data);
  }

  if (data.type === 'progress_update') {
    console.log('进度更新:', data.data.progress);
    // { percent: 50.0, speed: "50.0 MB/s" }
  }

  if (data.type === 'task_completed') {
    console.log('任务完成:', data.data);
  }

  if (data.type === 'task_failed') {
    console.log('任务失败:', data.data);
  }
};
```

#### 2. 轮询队列状态

```bash
curl http://localhost:8000/nassav/api/tasks/queue/status
```

响应包含活跃任务的进度信息：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "active_tasks": [
      {
        "task_id": "abc-123-def",
        "avid": "SSIS-465",
        "state": "STARTED",
        "progress": {
          "percent": 45.5,
          "speed": "46.0 MB/s"
        }
      }
    ],
    "pending_tasks": [],
    "active_count": 1,
    "pending_count": 0
  }
}
```

### 使用场景

1. **前端开发和测试**
   - 测试下载按钮和进度条UI
   - 测试 WebSocket 连接和消息处理
   - 测试任务队列显示

2. **后端集成测试**
   - 验证任务队列机制
   - 测试并发任务处理
   - 验证去重逻辑

3. **性能测试**
   - 测试多任务并发
   - 测试 WebSocket 性能
   - 测试 Redis 队列性能

### 配置示例

**启用 DEBUG 模式：**

创建或编辑 `django_backend/.env`：

```bash
# 开发环境配置
DEBUG=True
SECRET_KEY=your-development-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
```

**禁用 DEBUG 模式（生产环境）：**

```bash
# 生产环境配置
DEBUG=False
SECRET_KEY=your-strong-production-secret-key
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

### 注意事项

⚠️ **重要提示：**

1. **仅用于开发/测试**：此接口不应在生产环境中启用
2. **资源必须存在**：只能使用数据库中已存在的 AVID
3. **不产生实际文件**：模拟任务不会创建任何视频文件
4. **遵守任务队列规则**：模拟任务同样受队列和锁的限制
5. **时长限制**：最长 300 秒，防止长时间占用队列

### 与真实下载的对比

| 特性 | 模拟下载 | 真实下载 |
|------|----------|----------|
| 是否下载文件 | ❌ 否 | ✅ 是 |
| 更新进度 | ✅ 是 | ✅ 是 |
| WebSocket 通知 | ✅ 是 | ✅ 是 |
| 任务队列 | ✅ 是 | ✅ 是 |
| 去重检查 | ✅ 是 | ✅ 是 |
| 更新 file_exists | ❌ 否 | ✅ 是 |
| 持续时间 | 自定义（1-300秒） | 实际下载时间 |
| 需要资源存在 | ✅ 是 | ✅ 是 |

### 故障排查

**问题：返回 403 错误**
- 检查 `.env` 文件中 `DEBUG=True`
- 重启 Django 服务器以加载新配置

**问题：返回 404 错误**
- 确认 AVID 在数据库中存在
- 可以先调用 `POST /nassav/api/resource` 添加资源

**问题：返回 409 错误**
- 该 AVID 的任务已在队列中
- 等待当前任务完成或使用不同的 AVID

**问题：进度不更新**
- 检查 Celery Worker 是否运行：`uv run celery -A django_project worker -l info`
- 检查 Redis 服务是否正常
- 查看 Celery Worker 日志

---

## 其他调试功能

### 待添加

未来可能添加的其他调试接口：

- 模拟元数据刮削接口
- 批量数据生成接口
- 缓存清理接口
- 任务队列重置接口

---

**文档更新日期：** 2026-01-02
