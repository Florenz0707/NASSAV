<template>
  <div id="app">
    <header class="app-header">
      <div class="header-container">
        <router-link to="/" class="logo">
          <h1>NASSAV</h1>
        </router-link>

        <div class="search-box">
          <input
            v-model="inputContent"
            type="text"
            placeholder="输入视频内容"
            class="search-input"
            @keyup.enter="handleAddVideo(inputContent)"
          >
          <button
            class="search-button"
            @click="handleAddVideo(inputContent)"
            :disabled="isAdding"
          >
            {{ isAdding ? '添加中...' : '添加' }}
          </button>
        </div>
      </div>
    </header>

    <main class="app-main">
      <router-view v-slot="{ Component }">
        <keep-alive :include="['HomeView']">
          <component :is="Component" :key="$route.fullPath" />
        </keep-alive>
      </router-view>
    </main>

    <footer class="app-footer">
      <p>© 2025 NASSAV，你的NAS小姐姐助手</p>
    </footer>
  </div>
</template>

<script>
import videosApi from './api/videos'

export default {
  name: 'App',
  data() {
    return {
      inputContent: '',
      isAdding: false
    }
  },
  methods: {
    async handleAddVideo() {
      videosApi.addVideo(this.inputContent.trim())
    }
  }
}
</script>

<style>
/* 全局基础样式 */
:root {
  --primary-color: #ff9bb3;
  --secondary-color: #ff6b8b;
  --accent-color: #ffcdd8;
  --text-color: #5a3a4a;
}

body {
  margin: 0;
  padding: 0;
  font-family: Arial, sans-serif;
  background-color: #fff5f7;
}

#app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* 导航栏样式 */
.app-header {
  background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
  color: white;
  padding: 0;
  box-shadow: 0 4px 15px rgba(255, 107, 139, 0.2);
  position: relative;
}

.header-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.2rem 2rem;
  width: 100%;
}

.logo {
  color: white;
  text-decoration: none;
  flex-shrink: 0;
}

.logo h1 {
  font-size: 1.5rem;
  font-weight: 500;
  margin: 0;
  white-space: nowrap;
}

/* 搜索框样式 - 根据图片调整 */
.search-box {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.search-input {
  padding: 8px 12px;
  border: none;
  border-radius: 20px;
  outline: none;
  font-size: 14px;
  width: 180px;
  height: 36px;
  transition: all 0.3s ease;
  background-color: white;
  color: var(--secondary-color);
}

.search-input::placeholder {
  color: var(--accent-color);
}

.search-button {
  background-color: white;
  color: var(--secondary-color);
  border: none;
  padding: 8px 16px;
  border-radius: 20px;
  height: 36px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.3s ease;
  white-space: nowrap;
}

.search-button:hover {
  background-color: var(--accent-color);
  color: white;
}

/* 主内容区 */
.app-main {
  flex: 1;
  padding: 2rem;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
}

/* 底部样式 */
.app-footer {
  text-align: center;
  padding: 1.2rem;
  background: linear-gradient(135deg, var(--secondary-color), #ff4777);
  color: white;
  font-size: 0.9rem;
}

/* 响应式调整 - 重点修复小屏幕错位问题 */
@media (max-width: 768px) {
  .header-container {
    padding: 1rem;
    flex-wrap: nowrap; /* 防止换行 */
  }

  .logo h1 {
    font-size: 1.2rem;
  }

  .search-box {
    gap: 8px;
  }

  .search-input {
    width: 120px;
    font-size: 13px;
  }

  .search-button {
    padding: 8px 12px;
    font-size: 13px;
  }

  .app-main {
    padding: 1rem;
  }
}

/* 超小屏幕调整 */
@media (max-width: 480px) {
  .header-container {
    padding: 0.8rem;
  }

  .search-input {
    width: 100px;
  }

  .search-button {
    padding: 6px 10px;
  }
}

/* 其他全局样式 */
* {
  box-sizing: border-box;
}

/* 路由过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
