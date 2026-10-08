<script setup>
import { computed, onBeforeUnmount, ref, toRef, watch } from 'vue'
import { useRecommendationsStore } from '../stores/recommendations.js'
import { useToastStore } from '../../../shared/stores/toast.js'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import SettingsModal from '../../../shared/ui/SettingsModal.vue'
import LoadingSpinner from '../../../shared/ui/LoadingSpinner.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import SearchInput from '../../../shared/ui/SearchInput.vue'
const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '个性化' },
})
const emit = defineEmits(['close'])
const showPersonalizationModal = toRef(props, 'show')
const recommendationStore = useRecommendationsStore()
const toastStore = useToastStore()
function closePersonalizationModal() {
  emit('close')
}
const blacklistSeedType = ref('actor')
const blacklistSearch = ref('')
const blacklistBlockedOnly = ref(true)
const blacklistLoading = ref(false)
const blacklistItems = ref([])
const blacklistPagination = ref(null)
const blacklistSubmittingKey = ref('')
const blacklistCache = new Map()
const blacklistGuard = createRequestGuard()
let blacklistSearchTimer = null
const blacklistTabs = [
  { value: 'actor', label: '演员黑名单' },
  { value: 'genre', label: '类别黑名单' },
  { value: 'resource', label: '资源黑名单' },
]

const normalizedBlacklistSearch = computed(() =>
  blacklistSeedType.value === 'resource'
    ? blacklistSearch.value.trim().toUpperCase()
    : blacklistSearch.value.trim()
)
function formatSeedSourceMapping(item) {
  const mapping = item?.source_mapping
  if (!mapping || typeof mapping !== 'object') return ''

  const sourceName = String(mapping.source_name || '')
    .trim()
    .toUpperCase()
  const sourceSeedName = String(mapping.source_seed_name || '').trim()
  const sourceSeedSlug = String(mapping.source_seed_slug || '').trim()
  const aliases = Array.isArray(mapping.aliases)
    ? mapping.aliases
        .map((alias) => String(alias || '').trim())
        .filter((alias) => Boolean(alias))
        .slice(0, 3)
    : []

  const segments = []
  if (sourceName) segments.push(sourceName)
  if (sourceSeedName) segments.push(sourceSeedName)
  if (sourceSeedSlug) segments.push(`slug:${sourceSeedSlug}`)
  if (aliases.length) segments.push(`alias:${aliases.join(' / ')}`)

  return segments.join(' · ')
}

function buildBlacklistCacheKey() {
  return JSON.stringify({
    type: blacklistSeedType.value,
    search: normalizedBlacklistSearch.value,
    blockedOnly: blacklistSeedType.value === 'resource' ? true : blacklistBlockedOnly.value,
  })
}

function invalidateBlacklistCache(seedType = '') {
  if (!seedType || seedType === blacklistSeedType.value) {
    blacklistGuard.invalidate()
    blacklistLoading.value = false
  }
  const keys = Array.from(blacklistCache.keys())
  for (const key of keys) {
    if (!seedType || key.includes(`"type":"${seedType}"`)) {
      blacklistCache.delete(key)
    }
  }
}

async function loadBlacklistItems() {
  const request = blacklistGuard.begin()
  const cacheKey = buildBlacklistCacheKey()
  const cached = blacklistCache.get(cacheKey)
  if (cached) {
    blacklistItems.value = cached.items
    blacklistPagination.value = cached.pagination
    blacklistLoading.value = false
    return
  }

  blacklistLoading.value = true
  try {
    const params =
      blacklistSeedType.value === 'resource'
        ? { page: 1, page_size: 200 }
        : {
            page: 1,
            page_size: 200,
            order_by: blacklistBlockedOnly.value ? 'name' : 'count',
            order: blacklistBlockedOnly.value ? 'asc' : 'desc',
          }
    if (normalizedBlacklistSearch.value) params.search = normalizedBlacklistSearch.value
    const { items: list, pagination } = await recommendationStore.loadBlacklist(
      blacklistSeedType.value,
      params,
      blacklistBlockedOnly.value
    )

    if (!blacklistGuard.current(request)) return
    blacklistItems.value = list
    blacklistPagination.value = pagination
    blacklistCache.set(cacheKey, {
      items: list.map((item) => ({ ...item })),
      pagination: pagination ? { ...pagination } : null,
    })
  } catch (err) {
    if (!blacklistGuard.current(request)) return
    toastStore.error(err.message || '加载黑名单列表失败')
    blacklistItems.value = []
    blacklistPagination.value = null
  } finally {
    if (blacklistGuard.current(request)) blacklistLoading.value = false
  }
}

async function toggleSeedBlocked(item) {
  const seedType = blacklistSeedType.value
  const queryKey = buildBlacklistCacheKey()
  const itemKey =
    seedType === 'resource' ? `${seedType}:${item?.avid || ''}` : `${seedType}:${item?.id || ''}`
  if (!itemKey || itemKey.endsWith(':')) return
  const submitKey = itemKey
  if (blacklistSubmittingKey.value) return

  blacklistSubmittingKey.value = submitKey
  try {
    if (seedType === 'resource') {
      await recommendationStore.setAvidBlocked(item.avid, !item.is_blocked)
      toastStore.success(
        item.is_blocked ? `已移除资源 ${item.avid} 的屏蔽` : `已将资源 ${item.avid} 加入黑名单`
      )
    } else {
      await recommendationStore.setSeedBlocked(seedType, item.id, !item.is_blocked)
      toastStore.success(
        item.is_blocked
          ? `已移除${seedType === 'actor' ? '演员' : '类别'}屏蔽`
          : `已加入${seedType === 'actor' ? '演员' : '类别'}屏蔽`
      )
    }

    invalidateBlacklistCache(seedType)
    if (queryKey !== buildBlacklistCacheKey()) return
    blacklistItems.value = blacklistItems.value
      .map((entry) =>
        (seedType === 'resource' ? entry.avid === item.avid : entry.id === item.id)
          ? {
              ...entry,
              is_blocked: !item.is_blocked,
            }
          : entry
      )
      .filter(
        (entry) => !(seedType !== 'resource' && blacklistBlockedOnly.value && !entry.is_blocked)
      )
  } catch (err) {
    toastStore.error(err.message || '更新屏蔽状态失败')
  } finally {
    blacklistSubmittingKey.value = ''
  }
}

async function addResourceBlacklist() {
  const avid = normalizedBlacklistSearch.value
  if (!avid) return
  const submitKey = `resource:${avid}`
  if (blacklistSubmittingKey.value) return

  blacklistSubmittingKey.value = submitKey
  try {
    await recommendationStore.setAvidBlocked(avid, true)
    toastStore.success(`已将资源 ${avid} 加入黑名单`)
    invalidateBlacklistCache('resource')
    await loadBlacklistItems()
  } catch (err) {
    toastStore.error(err.message || '添加资源黑名单失败')
  } finally {
    blacklistSubmittingKey.value = ''
  }
}

watch(
  showPersonalizationModal,
  (visible) => {
    if (visible) {
      loadBlacklistItems()
    } else {
      blacklistGuard.invalidate()
      clearTimeout(blacklistSearchTimer)
      blacklistLoading.value = false
    }
  },
  { immediate: true }
)

watch([blacklistSeedType, blacklistBlockedOnly], () => {
  clearTimeout(blacklistSearchTimer)
  if (blacklistSeedType.value === 'resource' && !blacklistBlockedOnly.value) {
    blacklistBlockedOnly.value = true
    return
  }
  if (!showPersonalizationModal.value) return
  loadBlacklistItems()
})

watch(blacklistSearch, () => {
  blacklistGuard.invalidate()
  clearTimeout(blacklistSearchTimer)
  if (!showPersonalizationModal.value) return
  blacklistSearchTimer = setTimeout(loadBlacklistItems, 300)
})
onBeforeUnmount(() => {
  blacklistGuard.invalidate()
  clearTimeout(blacklistSearchTimer)
})
defineExpose({ invalidate: invalidateBlacklistCache })
</script>
<template>
  <SettingsModal
    :show="showPersonalizationModal"
    :title="title"
    :max-width-class="$slots.preferences ? 'max-w-6xl max-h-[85dvh] overflow-y-auto' : 'max-w-4xl'"
    @close="closePersonalizationModal"
  >
    <div
      :class="$slots.preferences ? 'grid grid-cols-1 lg:grid-cols-[18rem_minmax(0,1fr)] gap-6' : ''"
    >
      <section v-if="$slots.preferences" class="min-w-0">
        <h3 class="text-lg font-semibold text-primary mb-3">推荐偏好</h3>
        <slot name="preferences" />
      </section>
      <section class="min-w-0">
        <h3 v-if="$slots.preferences" class="text-lg font-semibold text-primary mb-3">黑名单</h3>
        <div class="blacklist-tabs header-tabs">
          <button
            v-for="tab in blacklistTabs"
            :key="tab.value"
            class="blacklist-tab"
            :class="{ active: blacklistSeedType === tab.value }"
            @click="blacklistSeedType = tab.value"
          >
            {{ tab.label }}
          </button>
        </div>

        <div class="blacklist-modal">
          <div class="blacklist-toolbar">
            <SearchInput
              v-model="blacklistSearch"
              :placeholder="
                blacklistSeedType === 'actor'
                  ? '搜索演员名'
                  : blacklistSeedType === 'genre'
                    ? '搜索类别名'
                    : '输入 AVID，例如 IPZZ-001'
              "
            />

            <label v-if="blacklistSeedType !== 'resource'" class="pretty-toggle">
              <input
                v-model="blacklistBlockedOnly"
                type="checkbox"
                :disabled="blacklistSeedType === 'resource'"
              />
              <span class="pretty-toggle-track">
                <span class="pretty-toggle-thumb" />
              </span>
              <span class="pretty-toggle-label">仅看已屏蔽</span>
            </label>
          </div>

          <div
            v-if="blacklistSeedType === 'resource' && normalizedBlacklistSearch"
            class="blacklist-add-strip"
          >
            <div class="blacklist-add-copy">
              <span>将当前 AVID 直接加入资源黑名单</span>
            </div>
            <button
              class="blacklist-action-btn is-block"
              :disabled="blacklistSubmittingKey === `resource:${normalizedBlacklistSearch}`"
              @click="addResourceBlacklist"
            >
              {{
                blacklistSubmittingKey === `resource:${normalizedBlacklistSearch}` ? '...' : '屏蔽'
              }}
            </button>
          </div>

          <div class="blacklist-summary">
            <span>
              当前类型：
              {{
                blacklistSeedType === 'actor'
                  ? '演员'
                  : blacklistSeedType === 'genre'
                    ? '类别'
                    : '资源'
              }}
            </span>
            <span v-if="blacklistPagination">
              {{ blacklistSeedType === 'resource' ? '屏蔽条目' : '总条目' }}
              {{ blacklistPagination.total }}
            </span>
            <span>当前展示 {{ blacklistItems.length }}</span>
          </div>

          <div v-if="blacklistLoading" class="blacklist-loading">
            <LoadingSpinner size="medium" text="正在读取..." />
          </div>

          <div v-else-if="!blacklistItems.length" class="blacklist-empty">
            {{ blacklistBlockedOnly ? '当前没有已屏蔽项。' : '没有匹配到可操作的条目。' }}
          </div>

          <div v-else class="blacklist-list">
            <div
              v-for="item in blacklistItems"
              :key="`${blacklistSeedType}-${item.avid || item.id}`"
              class="blacklist-row"
            >
              <div class="blacklist-main">
                <div class="blacklist-name">
                  {{ item.name || item.title || item.avid }} （{{
                    blacklistSeedType === 'resource' ? '' : `${item.resource_count ?? 0}个资源`
                  }}
                  {{ `${item.is_blocked ? '已屏蔽' : '未屏蔽'}` }}）
                </div>
                <div
                  v-if="blacklistSeedType !== 'resource' && formatSeedSourceMapping(item)"
                  class="blacklist-mapping"
                >
                  映射：{{ formatSeedSourceMapping(item) }}
                </div>
              </div>

              <button
                class="blacklist-action-btn"
                :class="item.is_blocked ? 'is-unblock' : 'is-block'"
                :disabled="
                  blacklistSubmittingKey ===
                  `${blacklistSeedType}:${blacklistSeedType === 'resource' ? item.avid : item.id}`
                "
                @click="toggleSeedBlocked(item)"
              >
                {{
                  blacklistSubmittingKey ===
                  `${blacklistSeedType}:${blacklistSeedType === 'resource' ? item.avid : item.id}`
                    ? '...'
                    : item.is_blocked
                      ? '取消'
                      : '屏蔽'
                }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
    <template #footer>
      <div class="blacklist-footer">
        <AppButton variant="neutral" @click="closePersonalizationModal">关闭</AppButton>
      </div>
    </template>
  </SettingsModal>
</template>
<style scoped>
.blacklist-modal {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.blacklist-toolbar {
  display: flex;
  flex-direction: column;
  align-items: left;
  gap: 1rem;
}

.blacklist-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.7rem;
}

.blacklist-tab {
  min-height: 2.3rem;
  border: 1px solid color-mix(in srgb, var(--neutral-color) 10%, transparent);
  border-radius: 60px;
  padding: 0 1rem;
  background: color-mix(in srgb, var(--neutral-color) 4%, transparent);
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 400;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.blacklist-tab.active {
  border-color: color-mix(in srgb, var(--accent-secondary) 32%, transparent);
  background: color-mix(in srgb, var(--accent-secondary) 12%, transparent);
  color: var(--text-inverse);
}

.header-tabs {
  margin-left: 0.5rem;
}

.blacklist-search {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  width: 100%;
  margin: left -0.5rem;
}

.blacklist-search-label {
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 600;
}

.blacklist-search input {
  min-height: 2.8rem;
  border: 1px solid color-mix(in srgb, var(--neutral-color) 12%, transparent);
  border-radius: 0.95rem;
  background: color-mix(in srgb, var(--neutral-color) 4%, transparent);
  padding: 0 0.9rem;
  color: var(--text-primary);
}

.pretty-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.7rem;
  cursor: pointer;
  user-select: none;
}

.pretty-toggle input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.pretty-toggle-track {
  position: relative;
  display: inline-flex;
  width: 2.7rem;
  height: 1.2rem;
  align-items: center;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--neutral-color) 12%, transparent);
  background: color-mix(in srgb, var(--neutral-color) 8%, transparent);
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.pretty-toggle-thumb {
  position: absolute;
  left: 0.2rem;
  width: 1.05rem;
  height: 1.05rem;
  border-radius: 999px;
  background: var(--text-inverse);
  box-shadow: 0 4px 10px color-mix(in srgb, var(--shadow-ink) 20%, transparent);
  transition: transform 0.2s ease;
}

.pretty-toggle input:checked + .pretty-toggle-track {
  border-color: color-mix(in srgb, var(--accent-secondary) 28%, transparent);
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-danger));
  color: var(--on-accent);
}

.pretty-toggle input:checked + .pretty-toggle-track .pretty-toggle-thumb {
  transform: translateX(1.1rem);
}

.pretty-toggle-label {
  color: var(--text-secondary);
  font-size: 0.92rem;
  font-weight: 600;
}

.blacklist-add-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border: 1px solid color-mix(in srgb, var(--accent-secondary) 14%, transparent);
  border-radius: 1rem;
  background: color-mix(in srgb, var(--accent-secondary) 6%, transparent);
  padding: 0.9rem 1rem;
}

.blacklist-add-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.18rem;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.blacklist-add-copy strong {
  color: var(--text-primary);
  font-size: 0.96rem;
}

.blacklist-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1rem;
  color: var(--text-muted);
  font-size: 0.86rem;
}

.blacklist-loading,
.blacklist-empty {
  display: flex;
  min-height: 13rem;
  align-items: center;
  justify-content: center;
  border-radius: 1rem;
  border: 1px dashed color-mix(in srgb, var(--neutral-color) 12%, transparent);
  background: color-mix(in srgb, var(--neutral-color) 2.5%, transparent);
  color: var(--text-secondary);
}

.blacklist-list {
  display: flex;
  max-height: 13rem;
  flex-direction: column;
  gap: 0.75rem;
  overflow-y: auto;
  padding-right: 0.2rem;
}

.blacklist-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border: 1px solid color-mix(in srgb, var(--neutral-color) 8%, transparent);
  border-radius: 1rem;
  background: color-mix(in srgb, var(--neutral-color) 3%, transparent);
  padding: 0.95rem 1rem;
}

.blacklist-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.3rem;
}

.blacklist-name {
  color: var(--text-primary);
  font-weight: 700;
  word-break: break-word;
}

.blacklist-mapping {
  color: var(--text-muted);
  font-size: 0.82rem;
  word-break: break-word;
}

.blacklist-action-btn {
  min-width: 5.5rem;
  min-height: 1.5rem;
  border-radius: 0.9rem;
  padding: 0.3rem 1.7rem;
  font-size: 1rem;
  font-weight: 500;
  transition:
    transform 0.2s ease,
    opacity 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.blacklist-action-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.blacklist-action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.blacklist-action-btn.is-block {
  border: none;
  background: var(--accent-primary);
  color: var(--on-accent);
}

.blacklist-action-btn.is-unblock {
  border: 1px solid color-mix(in srgb, var(--accent-danger) 22%, transparent);
  background: color-mix(in srgb, var(--accent-danger) 10%, transparent);
  color: var(--accent-danger);
}

.blacklist-footer {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 960px) {
  .blacklist-toolbar,
  .blacklist-row {
    flex-direction: column;
    align-items: stretch;
  }

  .blacklist-search {
    width: 100%;
  }

  .blacklist-action-btn,
  .blacklist-add-strip {
    width: 100%;
  }

  .header-tabs {
    margin-left: 0;
  }
}
</style>
