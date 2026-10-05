// A response may update state only while it belongs to the current query.
export function createRequestGuard() {
  let version = 0
  return {
    begin: () => ++version,
    current: (request) => request === version,
    invalidate: () => {
      version++
    },
  }
}
