<script setup>
import {RouterView} from 'vue-router'
import Navbar from './components/Navbar.vue'
import Toast from './components/Toast.vue'
</script>

<template>
  <div class="app">
    <div class="background-pattern"></div>
    <Navbar/>
    <main class="main-content">
      <RouterView v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component"/>
        </transition>
      </RouterView>
    </main>
    <Toast/>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  position: relative;
}

.background-pattern {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: radial-gradient(ellipse at 20% 20%, rgba(120, 119, 198, 0.15) 0%, transparent 50%),
  radial-gradient(ellipse at 80% 80%, rgba(255, 119, 115, 0.1) 0%, transparent 50%),
  radial-gradient(ellipse at 50% 50%, rgba(78, 205, 196, 0.08) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}

.main-content {
  position: relative;
  z-index: 1;
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.page-enter-active,
.page-leave-active {
  transition: all 0.3s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}
</style>
