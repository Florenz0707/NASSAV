<script setup>
import ContinueWatchingPanel from '../features/playback/components/ContinueWatchingPanel.vue'
import AppIcon from '../shared/ui/AppIcon.vue'
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="animate-[fadeIn_0.5s_ease] min-h-full flex flex-col relative overflow-hidden">
    <!-- Decorative Background Grid -->
    <div
      class="fixed inset-0 z-[-1] opacity-[0.03] pointer-events-none"
      style="
        background-image: radial-gradient(var(--decoration-color) 1px, transparent 1px);
        background-size: 30px 30px;
      "
    />

    <!-- Hero Section -->
    <section class="relative z-10 py-20 px-4">
      <div class="relative max-w-7xl mx-auto">
        <div class="max-w-2xl">
          <h1 class="flex flex-col gap-3 mb-8">
            <span class="home-title w-fit text-7xl font-bold tracking-tight">NASSAV</span>
            <span class="text-3xl font-semibold tracking-wide" style="color: var(--text-muted)"
              >视频资源管理系统</span
            >
          </h1>
          <p class="text-2xl leading-relaxed mb-10 max-w-[500px]" style="color: var(--text-muted)">
            打造您的私人影音库
            <br />
            <span class="text-xl opacity-90">高效管理 · 自动刮削 · 极速下载</span>
          </p>
          <div class="flex gap-5 flex-wrap">
            <RouterLink
              to="/add"
              class="tw-btn-primary px-8 py-4 rounded-xl text-lg text-on-accent"
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
              添加资源
            </RouterLink>
            <RouterLink
              to="/resources"
              class="tw-btn-outline-muted gap-3 px-8 py-4 rounded-xl text-lg"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <rect x="3" y="3" width="7" height="7" stroke-width="2" rx="1" />
                <rect x="14" y="3" width="7" height="7" stroke-width="2" rx="1" />
                <rect x="3" y="14" width="7" height="7" stroke-width="2" rx="1" />
                <rect x="14" y="14" width="7" height="7" stroke-width="2" rx="1" />
              </svg>
              浏览资源库
            </RouterLink>
          </div>
        </div>
      </div>
    </section>

    <ContinueWatchingPanel />

    <!-- Features Grid (Decorative) -->
    <section class="relative z-10 px-4 pb-20 max-w-7xl mx-auto w-full">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <!-- Card 1 -->
        <div
          class="p-8 rounded-2xl bg-secondary border border-[var(--border-color)] backdrop-blur-sm hover:bg-surface-subtle/[0.04] transition-all duration-300 group hover:-translate-y-1"
        >
          <div
            class="w-14 h-14 rounded-2xl home-icon home-icon--coral flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 border border-[var(--border-color)]"
          >
            <AppIcon name="bolt" class="w-8 h-8" />
          </div>
          <h2 class="text-xl font-semibold mb-3" style="color: var(--feature-title-color)">
            极速下载引擎
          </h2>
          <p class="text-muted leading-relaxed text-sm">
            内置多线程下载器，支持断点续传与自动合并。智能队列管理，让资源获取更高效。
          </p>
        </div>

        <!-- Card 2 -->
        <div
          class="p-8 rounded-2xl bg-secondary border border-[var(--border-color)] backdrop-blur-sm hover:bg-surface-subtle/[0.04] transition-all duration-300 group hover:-translate-y-1"
        >
          <div
            class="w-14 h-14 rounded-2xl home-icon home-icon--teal flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 border border-[var(--border-color)]"
          >
            <AppIcon name="target" class="w-8 h-8" />
          </div>
          <h2 class="text-xl font-semibold mb-3" style="color: var(--feature-title-color)">
            智能元数据刮削
          </h2>
          <p class="text-muted leading-relaxed text-sm">
            自动匹配影片信息，获取高清封面、演员阵容与标签分类。让您的媒体库井井有条。
          </p>
        </div>

        <!-- Card 3 -->
        <div
          class="p-8 rounded-2xl bg-secondary border border-[var(--border-color)] backdrop-blur-sm hover:bg-surface-subtle/[0.04] transition-all duration-300 group hover:-translate-y-1"
        >
          <div
            class="w-14 h-14 rounded-2xl home-icon home-icon--purple flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 border border-[var(--border-color)]"
          >
            <AppIcon name="palette" class="w-8 h-8" />
          </div>
          <h2 class="text-xl font-semibold mb-3" style="color: var(--feature-title-color)">
            沉浸式体验
          </h2>
          <p class="text-muted leading-relaxed text-sm">
            精心设计的现代化 UI，流畅的交互动画。支持深色模式，提供舒适的视觉享受。
          </p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-title {
  background: var(--brand-gradient);
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
}
.home-icon {
  color: var(--home-icon-color);
  background: color-mix(in srgb, var(--home-icon-color) 12%, var(--bg-secondary));
  border-color: color-mix(in srgb, var(--home-icon-color) 30%, transparent);
}
.home-icon--coral {
  --home-icon-color: var(--accent-primary-text);
}
.home-icon--teal {
  --home-icon-color: var(--accent-tertiary-text);
}
.home-icon--purple {
  --home-icon-color: var(--genre-tag-text);
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
</style>
