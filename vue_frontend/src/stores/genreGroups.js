import {defineStore} from 'pinia'
import {ref} from 'vue'

export const useGenreGroupsStore = defineStore('genreGroups', () => {
    const groups = ref([])
    const pagination = ref({total: 0, page: 1, page_size: 15, pages: 1})
    const loading = ref(false)
    const error = ref(null)

    // direct call to /genres/ to get groups
    async function load({page = 1, page_size = 15, order_by = 'count', order = 'desc', search} = {}) {
        loading.value = true
        error.value = null
        try {
            // use plain fetch to avoid circular imports
            const params = {page: String(page), page_size: String(page_size), order_by}
            if (order) params.order = order
            if (typeof search !== 'undefined' && search !== null && String(search).trim() !== '') params.search = String(search).trim()
            const qs = new URLSearchParams(params)
            const r = await fetch(`/nassav/api/genres/?${qs.toString()}`)
            const body = await r.json()
            if (body && body.code === 200) {
                groups.value = body.data || []
                pagination.value = body.pagination || pagination.value
            } else {
                error.value = body && body.message ? body.message : 'Failed to load genre groups'
            }
        } catch (err) {
            error.value = err.message || String(err)
        } finally {
            loading.value = false
        }
    }

    return {groups, pagination, loading, error, load}
})
