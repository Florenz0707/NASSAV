const STATE_KEY = 'nassav:recommendations:view-state'

export function saveRecommendationViewState(state, storage = window.sessionStorage) {
  storage.setItem(STATE_KEY, JSON.stringify(state))
}

export function restoreRecommendationViewState(storage = window.sessionStorage) {
  const raw = storage.getItem(STATE_KEY)
  if (!raw) return null
  try {
    const state = JSON.parse(raw)
    if (!state || typeof state !== 'object' || Array.isArray(state))
      throw new Error('Invalid state')
    return state
  } catch {
    storage.removeItem(STATE_KEY)
    return null
  }
}

export function clearRecommendationViewState(storage = window.sessionStorage) {
  storage.removeItem(STATE_KEY)
}
