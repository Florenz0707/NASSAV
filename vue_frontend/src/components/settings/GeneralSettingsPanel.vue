<script setup>
import CustomSelect from '../CustomSelect.vue'

const props = defineProps({
  settings: {
    type: Object,
    required: true,
  },
  previewFont: {
    type: String,
    required: true,
  },
  displayTitleOptions: {
    type: Array,
    required: true,
  },
  searchResultDisplayOptions: {
    type: Array,
    required: true,
  },
  availableFonts: {
    type: Array,
    required: true,
  },
})

const emit = defineEmits(['update:previewFont', 'save'])
</script>

<template>
  <div>
    <div class="mb-6">
      <h2 class="text-xl font-semibold text-[var(--text-primary)] mb-2">通用设置</h2>
      <p class="text-sm text-[var(--text-muted)]">配置系统的通用参数</p>
    </div>

    <div class="space-y-6">
      <div class="p-4 rounded-xl bg-white/[0.02] border border-[var(--border-white-5)]">
        <h3 class="text-sm font-medium text-[var(--text-muted)] mb-4 uppercase tracking-wider">
          显示设置
        </h3>
        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-[var(--text-primary)] font-medium">主题模式</div>
              <div class="text-sm text-[var(--text-muted)]">切换深色模式或浅色模式</div>
            </div>
            <div class="flex gap-2">
              <button
                class="px-4 py-2 rounded-lg text-sm transition-all"
                :class="
                  settings.colorMode === 'light'
                    ? 'bg-[var(--accent-primary)] text-white'
                    : 'bg-[var(--bg-white-5)] text-[var(--text-muted)] hover:bg-[var(--bg-white-10)]'
                "
                @click="settings.colorMode = 'light'"
              >
                ☀️ 浅色
              </button>
              <button
                class="px-4 py-2 rounded-lg text-sm transition-all"
                :class="
                  settings.colorMode === 'dark'
                    ? 'bg-[var(--accent-primary)] text-white'
                    : 'bg-[var(--bg-white-5)] text-[var(--text-muted)] hover:bg-[var(--bg-white-10)]'
                "
                @click="settings.colorMode = 'dark'"
              >
                🌙 深色
              </button>
            </div>
          </div>

          <div
            class="flex items-center justify-between pt-4 border-t border-[var(--border-white-5)]"
          >
            <div>
              <div class="text-[var(--text-primary)] font-medium">显示女优头像</div>
              <div class="text-sm text-[var(--text-muted)]">在列表和详情页中渲染女优头像图片</div>
            </div>
            <button
              class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none"
              :style="
                settings.showActorAvatar
                  ? 'background: var(--accent-primary);'
                  : 'background: var(--bg-secondary);'
              "
              @click="settings.showActorAvatar = !settings.showActorAvatar"
            >
              <span
                class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
                :class="settings.showActorAvatar ? 'translate-x-6' : 'translate-x-1'"
              />
            </button>
          </div>

          <div
            class="flex items-center justify-between pt-4 border-t border-[var(--border-white-5)]"
          >
            <div>
              <div class="text-[var(--text-primary)] font-medium">标题显示字段</div>
              <div class="text-sm text-[var(--text-muted)]">选择在资源列表中显示的标题类型</div>
            </div>
            <CustomSelect
              :model-value="settings.displayTitle"
              :options="displayTitleOptions"
              class="min-w-[10rem]"
              @update:model-value="settings.displayTitle = $event"
            />
          </div>

          <div
            class="flex items-center justify-between pt-4 border-t border-[var(--border-white-5)]"
          >
            <div>
              <div class="text-[var(--text-primary)] font-medium">搜索结果展示样式</div>
              <div class="text-sm text-[var(--text-muted)]">
                控制推荐页搜索结果使用标准网格还是两列瀑布流
              </div>
            </div>
            <CustomSelect
              :model-value="settings.searchResultDisplayStyle"
              :options="searchResultDisplayOptions"
              class="min-w-[12rem]"
              @update:model-value="settings.searchResultDisplayStyle = $event"
            />
          </div>

          <div class="pt-4 border-t border-[var(--border-white-5)]">
            <div class="flex items-center justify-between mb-4">
              <div>
                <div class="text-[var(--text-primary)] font-medium">字体样式</div>
                <div class="text-sm text-[var(--text-muted)]">选择应用的全局字体样式</div>
              </div>
              <CustomSelect
                :model-value="previewFont"
                :options="
                  availableFonts.map((font) => ({
                    value: font.value,
                    label: `${font.label}${font.isDefault ? '（默认）' : ''}`,
                  }))
                "
                class="min-w-[14rem]"
                @update:model-value="emit('update:previewFont', $event)"
              />
            </div>

            <div class="p-4 rounded-lg bg-white/[0.02] border border-[var(--border-white-5)]">
              <div class="text-xs text-[var(--text-muted)] mb-2">预览效果：</div>
              <div
                class="text-[var(--text-primary)] leading-relaxed"
                :style="{
                  fontFamily: `'${previewFont}', 'Mplus2', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', 'Hiragino Sans GB', Roboto, 'Noto Sans CJK', sans-serif`,
                }"
              >
                <p class="mb-2">
                  中文：最棒的不倫生活。不論是做愛、還是日常、全都是為了我讓人陷入愛人沼澤…。
                </p>
                <p class="mb-2">
                  日本語：最高すぎた不倫生活。セックスも、日常も、全てでオレをダメにする愛人沼で溶かされて…。
                </p>
                <p class="mb-2">
                  English: That adulterous life was just too incredible. I melted away in the
                  lover's quagmire…
                </p>
                <p>数字：0123456789</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="flex pt-4 justify-end min-w-full">
        <button
          class="px-6 py-2.5 text-white rounded-xl font-medium transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_4px_12px_rgba(255,107,107,0.3)]"
          style="background: var(--accent-primary)"
          @click="emit('save')"
        >
          保存设置
        </button>
      </div>
    </div>
  </div>
</template>
