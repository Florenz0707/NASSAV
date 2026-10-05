const titleFields = new Set(['original_title', 'source_title', 'translated_title'])

export function resolveResourceTitle(resource, preferred = 'source_title') {
  if (!resource) return ''
  if (titleFields.has(preferred) && resource[preferred]) return resource[preferred]
  return (
    resource.translated_title ||
    resource.source_title ||
    resource.original_title ||
    resource.title ||
    resource.avid ||
    ''
  )
}
