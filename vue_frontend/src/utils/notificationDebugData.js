// Imported only by the DEV notification preview. No store/API writes.
export function notificationDebugData() {
  return [
    {
      id: 'n1',
      day: '今天',
      time: '14:32',
      title: '下载失败 · 山间来信',
      message: '连接中断，已保留下载进度。',
      avid: 'DEMO-003',
      severity: 'danger',
      unread: true,
      targetLabel: '查看任务',
    },
    {
      id: 'n2',
      day: '今天',
      time: '14:28',
      title: '批量添加结束',
      message: '12 项资源：成功 10、失败 2。',
      severity: 'danger',
      unread: true,
      targetLabel: '查看批次',
      failures: ['DEMO-007 · 来源超时', 'DEMO-008 · 未找到资源'],
    },
    {
      id: 'n3',
      day: '今天',
      time: '14:20',
      title: '下载完成 · 雨后森林的清晨',
      message: '1 GB · 资源已就绪。',
      avid: 'DEMO-001',
      severity: 'success',
      unread: false,
      targetLabel: '查看资源',
    },
    {
      id: 'n4',
      day: '昨天',
      time: '18:05',
      title: '翻译成功 · 海边的一日',
      message: '标题翻译已完成。',
      avid: 'DEMO-006',
      severity: 'success',
      unread: true,
      targetLabel: '查看资源',
    },
  ]
}
