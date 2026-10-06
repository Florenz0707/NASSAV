import api from './client.js'
import { logger } from '../shared/lib/logger.js'

export const downloadApi = {
  // 获取视频文件路径
  getFilePath: (avid) => api.get('/downloads/abspath', { params: { avid } }),

  // 提交下载任务
  submitDownload: (avid) => api.post(`/downloads/${encodeURIComponent(avid)}`),

  // 删除下载的视频
  deleteFile: (avid) => api.delete(`/downloads/${encodeURIComponent(avid)}`),
  // 批量提交下载任务（动态超时）
  batchSubmit: (avids) => {
    // 基础超时 10 秒，每个任务增加 2 秒
    const timeout = 10000 + avids.length * 2000
    logger.debug(`[API] 批量下载 ${avids.length} 个任务，超时设置: ${timeout}ms`)
    return api.post('/downloads/batch_submit', { avids }, { timeout })
  },
}
