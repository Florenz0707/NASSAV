// Samples belong only to DownloadsView DEBUG_MODE, never to a real queue.
export function createTaskDebugData() {
  const tasks = [
    {
      id: 'd1',
      type: 'download',
      avid: 'DEMO-001',
      title: '雨后森林的清晨',
      coverScene: 'forest',
      state: 'running',
      percent: 45,
      speed: '5.2 MB/s',
      downloaded: '452 MB',
      total: '1 GB',
      updated: '14:32:10',
    },
    {
      id: 's1',
      type: 'scrape',
      avid: 'DEMO-002',
      title: '',
      coverScene: '',
      state: 'running',
      action: 'add',
      stage: 'metadata',
      updated: '14:31:48',
    },
    {
      id: 'd2',
      type: 'download',
      avid: 'DEMO-003',
      title: '山间来信：沿着溪流走向远方',
      coverScene: 'mountain',
      state: 'queued',
      percent: 0,
      updated: '14:31:20',
    },
    {
      id: 's2',
      type: 'scrape',
      avid: 'DEMO-004',
      title: '暮色中的海岸',
      coverScene: 'coast',
      state: 'failed',
      action: 'refresh',
      stage: 'metadata',
      error: '来源请求超时，已有资源未覆盖',
      updated: '14:30:12',
    },
    {
      id: 'd3',
      type: 'download',
      avid: 'DEMO-005',
      title: '城市夜行：最后一班列车',
      coverScene: 'city',
      state: 'succeeded',
      percent: 100,
      downloaded: '800 MB',
      total: '800 MB',
      updated: '14:29:03',
    },
    {
      id: 's3',
      type: 'scrape',
      avid: 'DEMO-006',
      title: '海边的一日',
      coverScene: 'coast',
      state: 'succeeded',
      action: 'add',
      stage: 'translation_completed',
      translation: { state: 'completed' },
      updated: '14:28:51',
    },
  ]
  const now = Date.now() / 1000
  return tasks.map((task, index) => ({
    ...task,
    taskType: task.type,
    hasResource:
      task.type === 'download' || task.state === 'succeeded' || task.action === 'refresh',
    timeline: [
      { label: '任务已排队', at: now - 300 - index * 30 },
      { label: task.type === 'download' ? '下载' : '获取元数据', at: now - 180 - index * 30 },
      ...(task.state === 'succeeded'
        ? [{ label: task.type === 'scrape' ? '翻译完成' : '下载完成', at: now - 60 - index * 30 }]
        : task.state === 'failed'
          ? [{ label: '刮削失败', state: 'failed', at: now - 60 - index * 30 }]
          : []),
    ],
  }))
}
