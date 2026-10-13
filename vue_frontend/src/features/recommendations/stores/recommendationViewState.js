const STATE_KEY = 'nassav:recommendations:view-state'
const stateKey = (owner) => (owner ? `${STATE_KEY}:${encodeURIComponent(owner)}` : STATE_KEY)

export function saveRecommendationViewState(state, storage = window.sessionStorage, owner = '') {
  storage.setItem(stateKey(owner), JSON.stringify(state))
}

export function restoreRecommendationViewState(storage = window.sessionStorage, owner = '') {
  const raw = storage.getItem(stateKey(owner))
  if (!raw) return null
  try {
    const state = JSON.parse(raw)
    if (!state || typeof state !== 'object' || Array.isArray(state))
      throw new Error('Invalid state')
    return state
  } catch {
    storage.removeItem(stateKey(owner))
    return null
  }
}

export function clearRecommendationViewState(storage = window.sessionStorage, owner = '') {
  storage.removeItem(stateKey(owner))
}

export function clearAllRecommendationViewStates(storage = window.sessionStorage) {
  for (let index = storage.length - 1; index >= 0; index--) {
    const key = storage.key(index)
    if (key === STATE_KEY || key?.startsWith(`${STATE_KEY}:`)) storage.removeItem(key)
  }
}
