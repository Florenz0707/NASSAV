import { defineStore } from 'pinia'
import { libraryApi } from '../../../api/library.js'
import { createMembershipLookup } from '../lib/membershipLookup.js'

export const useMembershipsStore = defineStore('memberships', () =>
  createMembershipLookup(libraryApi.membershipStatuses)
)
