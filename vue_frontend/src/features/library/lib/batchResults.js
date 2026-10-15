export function libraryBatchOutcome(response, avids) {
  const results = new Map((response?.data?.results || []).map((item) => [item.avid, item]))
  const accepted = [],
    failed = []
  for (const avid of new Set(avids)) {
    const result = results.get(avid)
    if (result?.code >= 200 && result.code < 300) accepted.push(avid)
    else failed.push(result || { avid, code: 500, message: '操作结果未确认，请重试' })
  }
  return { accepted, failed }
}
