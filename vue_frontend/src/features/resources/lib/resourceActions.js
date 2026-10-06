const refreshModes = [
  ['全部刷新', true, true, false],
  ['仅M3U8', true, false, false],
  ['仅元数据', false, true, false],
  ['仅翻译', false, false, true],
  ['元数据+翻译', false, true, true],
]
export function resourceRefreshOptions(detail = false) {
  return refreshModes.map(([text, refresh_m3u8, refresh_metadata, retranslate]) => ({
    text: detail ? text.replace(/^仅/, '') : text,
    params: { refresh_m3u8, refresh_metadata, retranslate },
  }))
}
export function resourceDeleteOptions(hasVideo, detail = false) {
  const options = hasVideo
    ? [
        {
          text: '删除视频',
          action: 'deleteFile',
          title: '删除视频文件',
          message: '确定要删除视频文件吗？元数据和封面将保留。',
        },
        {
          text: detail ? '删除全部' : '全部删除',
          action: 'delete',
          title: '删除全部数据',
          message: '确定要删除该资源的所有数据（包括视频、元数据、封面）吗？此操作不可恢复！',
        },
      ]
    : [
        {
          text: '删除数据',
          action: 'delete',
          title: '删除数据',
          message: '确定要删除该资源的元数据和封面吗？此操作不可恢复！',
        },
      ]
  return options.map((option) => ({ ...option, confirm: option.message }))
}
