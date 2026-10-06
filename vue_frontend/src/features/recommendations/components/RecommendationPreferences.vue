<script setup>
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
const typePreference = defineModel('typePreference')
const actorPreference = defineModel('actorPreference')
const genrePreference = defineModel('genrePreference')
const limit = defineModel('limit')
const typePreferenceOptions = [
  { value: 'actor_heavy', label: '演员' },
  { value: 'balanced', label: '平衡' },
  { value: 'genre_heavy', label: '类别' },
]
const actorPreferenceOptions = [
  { value: 'familiar', label: '熟悉' },
  { value: 'balanced', label: '平衡' },
  { value: 'rare', label: '少见' },
]
const genrePreferenceOptions = [
  { value: 'familiar', label: '熟悉' },
  { value: 'balanced', label: '平衡' },
  { value: 'rare', label: '少见' },
]
const limitOptions = [
  { value: 12, label: '12' },
  { value: 24, label: '24' },
  { value: 36, label: '36' },
]
</script>
<template>
  <section class="meta-strip">
    <div class="meta-card">
      <label for="recommendation-type" class="meta-label">种子偏好</label>
      <div class="meta-control">
        <CustomSelect
          id="recommendation-type"
          aria-label="种子偏好"
          v-model="typePreference"
          :options="typePreferenceOptions"
          class="meta-select"
          full-width
        />
      </div>
      <p class="meta-desc">控制演员种子与类别种子的整体权重倾向。</p>
    </div>
    <div class="meta-card strategy-card">
      <label for="recommendation-actor" class="meta-label">演员偏好</label>
      <div class="meta-control">
        <CustomSelect
          id="recommendation-actor"
          aria-label="演员偏好"
          v-model="actorPreference"
          :options="actorPreferenceOptions"
          class="meta-select"
          full-width
        />
      </div>
      <p class="meta-desc">控制演员种子“熟悉/平衡/少见”偏好，叠加种子轮换抑制。</p>
    </div>
    <div class="meta-card strategy-card">
      <label for="recommendation-genre" class="meta-label">类别偏好</label>
      <div class="meta-control">
        <CustomSelect
          id="recommendation-genre"
          aria-label="类别偏好"
          v-model="genrePreference"
          :options="genrePreferenceOptions"
          class="meta-select"
          full-width
        />
      </div>
      <p class="meta-desc">控制类别种子“熟悉/平衡/少见”偏好，叠加种子轮换抑制。</p>
    </div>
    <div class="meta-card">
      <label for="recommendation-limit" class="meta-label">返回数量</label>
      <div class="meta-control">
        <CustomSelect
          id="recommendation-limit"
          aria-label="返回数量"
          v-model="limit"
          :options="limitOptions"
          class="meta-select"
          full-width
        />
      </div>
      <p class="meta-desc">默认返回 24 条推荐结果。</p>
    </div>
  </section>
</template>
