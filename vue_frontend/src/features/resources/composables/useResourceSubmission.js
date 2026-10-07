import { computed, onMounted, ref, watch } from 'vue'
import { summarizeSubmissionJobs } from '../lib/submissionResults.js'
export function useResourceSubmission({ resourceStore, resourceApi, toastStore }) {
  const validationError = ref('')
  const avid = ref('')
  watch(avid, () => {
    validationError.value = ''
  })
  const source = ref('any')
  const submitting = ref(false)
  const result = ref(null)
  watch(
    () => resourceStore.visibleScrapeJobs,
    (jobs) => {
      if (!result.value?.jobs) return
      result.value = {
        ...result.value,
        ...summarizeSubmissionJobs(result.value.jobs, jobs, result.value.submissionFailed),
      }
    }
  )
  const sourceOptions = computed(() => [
    { value: 'any', label: '自动' },
    ...resourceStore.sources.map((item) => ({
      value: item.toLowerCase(),
      label: item,
    })),
  ])

  onMounted(async () => {
    await resourceStore.fetchSources()
  })

  // 解析输入的 AVID 列表
  function parseAvids() {
    return avid.value
      .split(/[\n,\s]+/) // 按换行、逗号、空格分割
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s.length > 0) // 过滤空字符串
      .filter((v, i, arr) => arr.indexOf(v) === i) // 去重
  }

  async function handleSubmit() {
    if (submitting.value) return
    const avids = parseAvids()
    if (avids.length === 0) {
      validationError.value = '请输入至少一个视频编号，例如 SNOS-317'
      toastStore.warning('请输入视频编号')
      return
    }

    submitting.value = true
    result.value = null
    try {
      if (avids.length === 1) {
        await resourceStore.addResource(avids[0], source.value)
        return
      }

      const actions = avids.map((item) => ({ action: 'add', avid: item, source: source.value }))
      const response = await resourceApi.submitScrapeBatch(actions)
      const results = response.data?.results || []
      resourceStore.registerScrapeBatch(results)
      const queued = results.filter((item) => item.code === 202).map((item) => item.avid)
      const exists = results.filter((item) => item.code === 409).map((item) => item.avid)
      const failed = results.filter((item) => item.code >= 400 && item.code !== 409)
      result.value = {
        queued,
        exists,
        failed,
        success: [],
        total: avids.length,
        jobs: results
          .filter((item) => item.code === 202)
          .map((item) => ({ avid: item.avid, job_id: item.job_id, task_id: item.task_id })),
        submissionFailed: failed,
      }
      if (exists.length) toastStore.info(`${exists.length} 个资源已存在`)
    } catch (err) {
      if (err.code === 409 && avids.length === 1) {
        result.value = {
          success: [],
          queued: [],
          exists: avids,
          failed: [],
          total: 1,
          data: { avid: avids[0] },
        }
        toastStore.info('资源已存在')
      } else {
        result.value = {
          success: [],
          queued: [],
          exists: [],
          failed: avids.map((item) => ({
            avid: item,
            code: err.code || 500,
            message: err.message || '提交失败',
          })),
          total: avids.length,
        }
        toastStore.error(err.message || '提交失败')
      }
    } finally {
      submitting.value = false
    }
  }

  return {
    avid,
    source,
    submitting,
    result,
    sourceOptions,
    parseAvids,
    handleSubmit,
    validationError,
  }
}
