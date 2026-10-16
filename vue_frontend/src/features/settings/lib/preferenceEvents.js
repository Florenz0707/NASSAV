export const PREFERENCE_REVISION_KEY = 'nassav:preferences:revision'
export function preferencesChanged() {
  try {
    globalThis.window?.localStorage?.setItem(
      PREFERENCE_REVISION_KEY,
      `${Date.now()}:${Math.random()}`
    )
  } catch {
    /* Polling/visibility checks remain available when storage is disabled. */
  }
}
