import { defineStore } from 'pinia'
import { libraryApi } from '../../../api/library.js'
import { useMembershipsStore } from '../../library/stores/memberships.js'
import { createOperationTracking } from '../composables/operationTracking.js'

export const useUserOperationsStore = defineStore('userOperations', () =>
  createOperationTracking(libraryApi, {
    changed(item, previous) {
      if (
        item.state !== previous?.state &&
        ['succeeded', 'failed', 'cancelled'].includes(item.state)
      )
        useMembershipsStore().invalidate()
    },
  })
)
