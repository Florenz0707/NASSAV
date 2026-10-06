import { actorApi } from '../../../api/index.js'
import { createDirectoryStore } from './directoryStore.js'
export const useActorGroupsStore = createDirectoryStore('actorGroups', actorApi)
