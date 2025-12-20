# WebSocket 实时任务通知使用说明

## 概述

本项目已集成 WebSocket 支持，前端可以通过 WebSocket 连接实时接收任务队列状态更新和任务完成通知。

## 技术栈

- **Django Channels**: 提供 WebSocket 支持
- **Redis**: 作为 Channel Layer 的消息代理
- **Celery**: 异步任务队列

## WebSocket 连接

### 连接地址

```
ws://localhost:8000/ws/tasks/
```

或在生产环境中：

```
wss://your-domain.com/ws/tasks/
```

### 前端连接示例 (JavaScript)

```javascript
// 创建 WebSocket 连接
const ws = new WebSocket('ws://localhost:8000/ws/tasks/');

// 连接成功
ws.onopen = function(event) {
    console.log('WebSocket 连接已建立');

    // 请求当前队列状态
    ws.send(JSON.stringify({
        action: 'get_queue_status'
    }));
};

// 接收消息
ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    console.log('收到消息:', message);

    switch(message.type) {
        case 'task_started':
            console.log('任务开始:', message.data);
            // 更新UI显示任务开始
            break;

        case 'task_completed':
            console.log('任务完成:', message.data);
            // 显示完成通知
            break;

        case 'task_failed':
            console.log('任务失败:', message.data);
            // 显示错误通知
            break;

        case 'queue_status':
            console.log('队列状态:', message.data);
            // 更新任务队列UI
            break;
    }
};

// 连接错误
ws.onerror = function(error) {
    console.error('WebSocket 错误:', error);
};

// 连接关闭
ws.onclose = function(event) {
    console.log('WebSocket 连接已关闭');
    // 可以实现自动重连
};
```

## 消息格式

### 接收的消息类型

#### 1. 任务开始通知 (`task_started`)

```json
{
    "type": "task_started",
    "data": {
        "task_id": "abc123...",
        "avid": "SSIS-950",
        "status": "started"
    }
}
```

#### 2. 任务完成通知 (`task_completed`)

```json
{
    "type": "task_completed",
    "data": {
        "task_id": "abc123...",
        "avid": "SSIS-950",
        "status": "success",
        "message": "下载完成"
    }
}
```

#### 3. 任务失败通知 (`task_failed`)

```json
{
    "type": "task_failed",
    "data": {
        "task_id": "abc123...",
        "avid": "SSIS-950",
        "status": "failed",
        "message": "下载失败原因"
    }
}
```

#### 4. 队列状态更新 (`queue_status`)

```json
{
    "type": "queue_status",
    "data": {
        "active_tasks": [
            {
                "task_id": "abc123...",
                "avid": "SSIS-950",
                "worker": "celery@hostname",
                "time_start": 1703001234.567
            }
        ],
        "scheduled_tasks": [
            {
                "task_id": "def456...",
                "avid": "SONE-028",
                "worker": "celery@hostname"
            }
        ],
        "reserved_tasks": []
    }
}
```

### 发送的消息格式

前端可以发送以下消息来请求队列状态：

```json
{
    "action": "get_queue_status"
}
```

## REST API

### 获取任务队列状态

如果不想使用 WebSocket，也可以通过 REST API 获取队列状态：

```
GET /api/tasks/queue/status
```

响应示例：

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "active_tasks": [...],
        "scheduled_tasks": [...],
        "reserved_tasks": [...]
    }
}
```

## 启动服务

### 1. 确保 Redis 运行

```bash
redis-server
```

### 2. 启动 Django 开发服务器 (支持 WebSocket)

使用 Daphne (ASGI 服务器):

```bash
daphne -b 0.0.0.0 -p 8000 django_project.asgi:application
```

或使用 Uvicorn:

```bash
uvicorn django_project.asgi:application --host 0.0.0.0 --port 8000 --reload
```

### 3. 启动 Celery Worker

```bash
celery -A django_project worker -l info
```

## 前端示例：Vue.js

```vue
<template>
  <div class="task-monitor">
    <h2>任务队列状态</h2>

    <div class="active-tasks">
      <h3>正在执行 ({{ activeTasks.length }})</h3>
      <ul>
        <li v-for="task in activeTasks" :key="task.task_id">
          {{ task.avid }} - 正在下载...
        </li>
      </ul>
    </div>

    <div class="waiting-tasks">
      <h3>等待中 ({{ scheduledTasks.length }})</h3>
      <ul>
        <li v-for="task in scheduledTasks" :key="task.task_id">
          {{ task.avid }}
        </li>
      </ul>
    </div>

    <div class="notifications">
      <h3>最近通知</h3>
      <ul>
        <li v-for="(notif, index) in notifications" :key="index" :class="notif.type">
          {{ notif.message }}
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';

const ws = ref(null);
const activeTasks = ref([]);
const scheduledTasks = ref([]);
const reservedTasks = ref([]);
const notifications = ref([]);

const connectWebSocket = () => {
  ws.value = new WebSocket('ws://localhost:8000/ws/tasks/');

  ws.value.onopen = () => {
    console.log('WebSocket 已连接');
  };

  ws.value.onmessage = (event) => {
    const message = JSON.parse(event.data);

    switch(message.type) {
      case 'task_started':
        notifications.value.unshift({
          type: 'info',
          message: `任务开始: ${message.data.avid}`
        });
        break;

      case 'task_completed':
        notifications.value.unshift({
          type: 'success',
          message: `任务完成: ${message.data.avid}`
        });
        break;

      case 'task_failed':
        notifications.value.unshift({
          type: 'error',
          message: `任务失败: ${message.data.avid} - ${message.data.message}`
        });
        break;

      case 'queue_status':
        activeTasks.value = message.data.active_tasks;
        scheduledTasks.value = message.data.scheduled_tasks;
        reservedTasks.value = message.data.reserved_tasks;
        break;
    }

    // 保留最近20条通知
    if (notifications.value.length > 20) {
      notifications.value.pop();
    }
  };

  ws.value.onerror = (error) => {
    console.error('WebSocket 错误:', error);
  };

  ws.value.onclose = () => {
    console.log('WebSocket 连接关闭，5秒后重连...');
    setTimeout(connectWebSocket, 5000);
  };
};

onMounted(() => {
  connectWebSocket();
});

onUnmounted(() => {
  if (ws.value) {
    ws.value.close();
  }
});
</script>

<style scoped>
.task-monitor {
  padding: 20px;
}

.notifications .info { color: blue; }
.notifications .success { color: green; }
.notifications .error { color: red; }
</style>
```

## 前端示例：React

```jsx
import React, { useState, useEffect, useCallback } from 'react';

function TaskMonitor() {
  const [ws, setWs] = useState(null);
  const [activeTasks, setActiveTasks] = useState([]);
  const [scheduledTasks, setScheduledTasks] = useState([]);
  const [notifications, setNotifications] = useState([]);

  const connectWebSocket = useCallback(() => {
    const websocket = new WebSocket('ws://localhost:8000/ws/tasks/');

    websocket.onopen = () => {
      console.log('WebSocket connected');
    };

    websocket.onmessage = (event) => {
      const message = JSON.parse(event.data);

      switch(message.type) {
        case 'task_started':
          setNotifications(prev => [{
            type: 'info',
            message: `任务开始: ${message.data.avid}`
          }, ...prev.slice(0, 19)]);
          break;

        case 'task_completed':
          setNotifications(prev => [{
            type: 'success',
            message: `任务完成: ${message.data.avid}`
          }, ...prev.slice(0, 19)]);
          break;

        case 'task_failed':
          setNotifications(prev => [{
            type: 'error',
            message: `任务失败: ${message.data.avid}`
          }, ...prev.slice(0, 19)]);
          break;

        case 'queue_status':
          setActiveTasks(message.data.active_tasks);
          setScheduledTasks(message.data.scheduled_tasks);
          break;
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    websocket.onclose = () => {
      console.log('WebSocket closed, reconnecting in 5s...');
      setTimeout(connectWebSocket, 5000);
    };

    setWs(websocket);
  }, []);

  useEffect(() => {
    connectWebSocket();

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [connectWebSocket]);

  return (
    <div className="task-monitor">
      <h2>任务队列状态</h2>

      <div className="active-tasks">
        <h3>正在执行 ({activeTasks.length})</h3>
        <ul>
          {activeTasks.map(task => (
            <li key={task.task_id}>{task.avid} - 正在下载...</li>
          ))}
        </ul>
      </div>

      <div className="waiting-tasks">
        <h3>等待中 ({scheduledTasks.length})</h3>
        <ul>
          {scheduledTasks.map(task => (
            <li key={task.task_id}>{task.avid}</li>
          ))}
        </ul>
      </div>

      <div className="notifications">
        <h3>最近通知</h3>
        <ul>
          {notifications.map((notif, index) => (
            <li key={index} className={notif.type}>
              {notif.message}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default TaskMonitor;
```

## 注意事项

1. **CORS 设置**: 如果前端和后端不在同一域，需要在 Django settings 中配置 CORS。

2. **认证**: 当前 WebSocket 连接不需要认证。如果需要认证，可以在 `consumers.py` 中添加认证逻辑。

3. **重连机制**: 前端应该实现自动重连机制，以处理网络中断的情况。

4. **性能**: WebSocket 连接会占用服务器资源，请根据实际负载调整 Redis 和 Celery 配置。

5. **生产环境**: 在生产环境中，建议使用 Nginx 作为反向代理，配置 WebSocket 支持：

```nginx
location /ws/ {
    proxy_pass http://localhost:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

## 测试

可以使用浏览器控制台测试 WebSocket 连接：

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/tasks/');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
ws.send(JSON.stringify({action: 'get_queue_status'}));
```

## 故障排查

1. **连接失败**:
   - 确认 Redis 服务正在运行
   - 确认使用 ASGI 服务器 (Daphne/Uvicorn) 而不是 Django runserver

2. **收不到消息**:
   - 检查 Celery worker 是否正常运行
   - 查看服务器日志确认消息是否发送

3. **频繁断开**:
   - 检查防火墙设置
   - 增加 WebSocket 超时时间
