import {
  readSessionCache,
  writeSessionCache,
  clearSessionCache,
  optionalSessionStorage,
} from '../../../shared/lib/sessionCache.js'
const STATE_KEY = 'nassav:recommendations:view-state'
const stateKey = (owner) => (owner ? `${STATE_KEY}:${encodeURIComponent(owner)}` : STATE_KEY)
const resultKey = (state) =>
  JSON.stringify(
    (Array.isArray(state?.items) ? state.items : []).map((item) => [
      item?.snapshot_id,
      item?.avid,
      item?.source,
    ])
  )
export function saveRecommendationViewState(state, storage = optionalSessionStorage(), owner = '') {
  const key = stateKey(owner),
    previous = readSessionCache(storage, key)
  return writeSessionCache(storage, key, state, {
    prefix: STATE_KEY,
    limit: 4,
    expiresAt: Math.min(
      Number.isFinite(state.cacheExpiresAt) ? state.cacheExpiresAt : Infinity,
      previous && resultKey(previous.value) === resultKey(state) ? previous.expiresAt : Infinity
    ),
  })
}
export function restoreRecommendationViewState(storage = optionalSessionStorage(), owner = '') {
  const state = readSessionCache(storage, stateKey(owner))?.value
  return state && typeof state === 'object' && !Array.isArray(state) ? state : null
}
export function clearRecommendationViewState(storage = optionalSessionStorage(), owner = '') {
  try {
    storage.removeItem(stateKey(owner))
  } catch {
    /* Optional storage. */
  }
}
export function clearAllRecommendationViewStates(storage = optionalSessionStorage()) {
  clearSessionCache(storage, STATE_KEY)
}
