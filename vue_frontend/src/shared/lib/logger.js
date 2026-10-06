export const logger = {
  debug(...values) {
    if (import.meta.env?.DEV) console.debug(...values)
  },
}
