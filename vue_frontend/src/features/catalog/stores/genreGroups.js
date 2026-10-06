import { genreApi } from '../../../api/index.js'
import { createDirectoryStore } from './directoryStore.js'
export const useGenreGroupsStore = createDirectoryStore('genreGroups', genreApi)
