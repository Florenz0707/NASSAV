import { onScopeDispose, ref, watch } from 'vue'

// Track the submitted job, not another scrape of the same resource.
export function useResourceAdds({ added, jobs, submit, onAdded, onError, onExisting }) {
  const adding = ref(new Set())
  const pending = ref(new Map())
  let active = true
  const remove = (avid) => {
    pending.value = new Map([...pending.value].filter(([key]) => key !== avid))
    adding.value = new Set([...adding.value].filter((key) => key !== avid))
  }
  const saved = (item) => {
    remove(item.avid)
    added.value = new Set(added.value).add(item.avid)
    Promise.resolve(onAdded(item)).catch(() => {})
  }
  watch([jobs, pending], ([snapshots, requests]) => {
    for (const [avid, request] of requests) {
      const candidates = [...snapshots, request.snapshot].filter(
        (job) =>
          job && (request.jobId ? job.job_id === request.jobId : job.task_id === request.taskId)
      )
      const job = candidates.sort((a, b) => (b.version || 0) - (a.version || 0))[0]
      if (!job) continue
      if (job.resource_saved || job.resource_avid || job.state === 'succeeded') saved(request.item)
      else if (['failed', 'cancelled'].includes(job.state)) remove(avid)
    }
  })
  async function add(item) {
    if (!active || !item?.avid || adding.value.has(item.avid) || added.value.has(item.avid)) return
    adding.value = new Set(adding.value).add(item.avid)
    try {
      const response = await submit(item.avid, item)
      if (!active) return
      const data = response.data || {}
      const jobId = data.job_id || data.job?.job_id
      const taskId = data.task_id || data.job?.task_id
      if (!jobId && !taskId) throw new Error('添加任务未返回有效标识')
      pending.value = new Map(pending.value).set(item.avid, {
        item,
        jobId,
        taskId,
        snapshot: data.job,
      })
    } catch (error) {
      if (!active) return
      if (error.httpStatus === 409 || error.code === 409 || error?.response?.status === 409) {
        onExisting(item)
        saved(item)
      } else {
        remove(item.avid)
        onError(error)
      }
    }
  }
  onScopeDispose(() => {
    active = false
  })
  return { adding, add }
}
