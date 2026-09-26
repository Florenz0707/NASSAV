<script setup>
import { computed } from 'vue'
import { useResourceStore } from '../stores/resource'
import { scrapeJobLabel, TERMINAL_JOB_STATES } from '../stores/scrapeJobState'

const resourceStore = useResourceStore()
const jobs = computed(() => resourceStore.visibleScrapeJobs.slice(0, 12))

function elapsed(job) {
  if (!job.updated_at || TERMINAL_JOB_STATES.has(job.state)) return ''
  return `${Math.max(0, Math.floor(Date.now() / 1000 - job.updated_at))} 秒前更新`
}
</script>

<template>
  <section
    v-if="jobs.length"
    class="mb-6 rounded-lg border border-white/10 bg-secondary p-4 shadow-md"
    aria-label="资源任务进度"
  >
    <h2 class="mb-3 text-base font-semibold text-primary">资源任务</h2>
    <ul class="space-y-2">
      <li
        v-for="job in jobs"
        :key="job.task_id"
        class="flex items-center justify-between gap-3 rounded-lg border border-white/10 p-3"
      >
        <div class="min-w-0">
          <p class="truncate text-sm font-medium text-primary">
            {{ job.avid }} · {{ job.action === 'add' ? '添加' : '刷新' }}
          </p>
          <p class="text-sm text-secondary">
            {{ scrapeJobLabel(job)
            }}<span v-if="elapsed(job)" class="ml-2 text-muted">{{ elapsed(job) }}</span>
          </p>
          <p v-if="job.state === 'failed' && job.message" class="text-sm text-accent-danger">
            {{ job.message }}
          </p>
        </div>
        <button
          v-if="TERMINAL_JOB_STATES.has(job.state)"
          type="button"
          class="rounded-lg px-3 py-2 text-sm text-secondary transition-colors duration-200 hover:bg-white/10"
          @click="resourceStore.dismissScrapeJob(job.task_id)"
        >
          关闭
        </button>
      </li>
    </ul>
  </section>
</template>
