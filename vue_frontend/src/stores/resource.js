import {defineStore} from 'pinia'
import {computed, ref} from 'vue'
import {downloadApi, resourceApi, sourceApi} from '../api'

export const useResourceStore = defineStore('resource', () => {
    const resources = ref([])
    const sources = ref([])
    const downloads = ref([])
    const loading = ref(false)
    const error = ref(null)

    // 获取资源列表
    // 支持分页和排序
    const pagination = ref({total: 0, page: 1, page_size: 20, pages: 1})

    async function fetchResources({
                                      sort_by = 'metadata_create_time',
                                      order = 'desc',
                                      page = 1,
                                      page_size = 20,
                                      search = '',
                                      status = 'all',
                                      actor = undefined,
                                      genre = undefined
                                  } = {}) {
        loading.value = true
        error.value = null
        try {
            console.debug('[resource] fetchResources params:', {sort_by, order, page, page_size, search, status})
            const params = {sort_by, order, page, page_size}
            if (search) params.search = search
            if (status && status !== 'all') params.status = status
            if (typeof actor !== 'undefined' && actor !== null && actor !== '') params.actor = actor
            if (typeof genre !== 'undefined' && genre !== null && genre !== '') params.genre = genre
            console.debug('[resource] fetchResources request params:', params)
            const response = await resourceApi.getList(params)
            console.debug('[resource] fetchResources response:', response)

            // 后端可能返回多种格式：
            // 1) envelope with data as an array -> { data: [ ... ], pagination?: {...} }
            // 2) envelope with data.results and data.pagination -> { data: { results: [...], pagination: {...} } }
            // 3) legacy or other -> response.data may already be the array
            let results = []
            let paginationObj = null

            if (response) {
                // case: response.data is array
                if (Array.isArray(response.data)) {
                    results = response.data
                    paginationObj = response.pagination || null
                }
                // case: response.data.metadata exists (new backend shape)
                else if (response.data && Array.isArray(response.data.metadata)) {
                    results = response.data.metadata
                    // map backend pagination fields to our pagination shape
                    paginationObj = {
                        total: response.data.total_num || (response.data.pagination && response.data.pagination.total) || response.pagination && response.pagination.total || 0,
                        pages: response.data.total_pages || (response.data.pagination && response.data.pagination.pages) || response.pagination && response.pagination.pages || 1,
                        page: page,
                        page_size: page_size
                    }
                }
                // case: response.data.results exists
                else if (response.data && Array.isArray(response.data.results)) {
                    results = response.data.results
                    paginationObj = response.data.pagination || response.pagination || null
                }
                // case: response itself is an array (unlikely)
                else if (Array.isArray(response)) {
                    results = response
                } else {
                    results = response.data || []
                    paginationObj = response.pagination || (response.data && response.data.pagination) || null
                }
            }

            resources.value = results || []
            if (paginationObj) {
                pagination.value = Object.assign({}, pagination.value, paginationObj)
            } else {
                // ensure pagination.page at least matches request
                pagination.value.page = page
                pagination.value.page_size = page_size
            }
        } catch (err) {
            error.value = err.message || '获取资源列表失败'
            throw err
        } finally {
            loading.value = false
        }
    }

    // 获取下载源列表
    async function fetchSources() {
        try {
            const response = await sourceApi.getList()
            sources.value = response.data || []
        } catch (err) {
            console.error('获取下载源失败:', err)
        }
    }

    // 获取已下载列表
    async function fetchDownloads() {
        try {
            const response = await downloadApi.getList()
            downloads.value = response.data || []
        } catch (err) {
            console.error('获取下载列表失败:', err)
        }
    }

    // 添加新资源
    async function addResource(avid, source = 'any') {
        loading.value = true
        error.value = null
        try {
            const response = await resourceApi.addNew(avid, source)
            // backend returns { data: { resource: {...} } }
            const resObj = response && response.data && response.data.resource ? response.data.resource : null
            if (resObj) {
                _mergeOrUpsertResource(resObj)
            }
            return response
        } catch (err) {
            error.value = err.message || '添加资源失败'
            throw err
        } finally {
            loading.value = false
        }
    }

    // 刷新资源
    async function refreshResource(avid, params = null) {
        const response = await resourceApi.refresh(avid, params)
        const resObj = response && response.data && response.data.resource ? response.data.resource : null
        if (resObj) _mergeOrUpsertResource(resObj)
        return response
    }

    // 批量刷新/删除等，使用后端批量接口
    async function batchRefresh(avids = []) {
        if (!Array.isArray(avids) || avids.length === 0) return
        const payload = {action: 'refresh', avids}
        const resp = await resourceApi.batch(payload)
        // 合并返回的资源对象（如果有的话），避免整页刷新
        const results = resp && resp.data && (resp.data.results || resp.data) ? (resp.data.results || resp.data) : (resp && resp.results ? resp.results : [])
        if (Array.isArray(results)) {
            for (const r of results) {
                if (r && r.resource) _mergeOrUpsertResource(r.resource)
            }
        } else if (resp && resp.data && resp.data.resource) {
            _mergeOrUpsertResource(resp.data.resource)
        }
        return resp
    }

    async function batchDelete(avids = []) {
        if (!Array.isArray(avids) || avids.length === 0) return
        const payload = {action: 'delete', avids}
        const resp = await resourceApi.batch(payload)
        // 根据返回结果局部删除/合并
        const results = resp && resp.data && (resp.data.results || resp.data) ? (resp.data.results || resp.data) : (resp && resp.results ? resp.results : [])
        if (Array.isArray(results)) {
            for (const r of results) {
                if (r && r.action === 'delete' && r.avid) {
                    _removeResourceByAvid(r.avid)
                } else if (r && r.resource) {
                    _mergeOrUpsertResource(r.resource)
                }
            }
        }
        return resp
    }

    // 提交下载
    async function submitDownload(avid) {
        const response = await downloadApi.submitDownload(avid)
        await fetchDownloads()
        return response
    }

    async function batchSubmitDownload(avids = []) {
        if (!Array.isArray(avids) || avids.length === 0) return
        const resp = await downloadApi.batchSubmit(avids)
        await fetchDownloads()
        return resp
    }

    // helper: normalize resources to an array
    function _resourcesArray() {
        const raw = resources.value
        if (Array.isArray(raw)) return raw
        if (raw && Array.isArray(raw.results)) return raw.results
        if (raw && Array.isArray(raw.data)) return raw.data
        return []
    }

    // helper: merge or upsert a single resource object into current list
    function _mergeOrUpsertResource(resObj) {
        if (!resObj || !resObj.avid) return
        const arr = _resourcesArray()
        const idx = arr.findIndex(r => r.avid === resObj.avid)
        if (idx !== -1) {
            // merge fields
            arr[idx] = Object.assign({}, arr[idx], resObj)
        } else {
            // if current view is page 1, insert at top, otherwise ignore
            if (pagination.value && pagination.value.page === 1) {
                arr.unshift(resObj)
                // respect page_size
                const max = pagination.value && pagination.value.page_size ? pagination.value.page_size : 20
                if (arr.length > max) arr.splice(max)
            }
        }
        // write back depending on original resources shape
        if (Array.isArray(resources.value)) resources.value = arr
        else if (resources.value && Array.isArray(resources.value.results)) resources.value.results = arr
        else if (resources.value && Array.isArray(resources.value.data)) resources.value.data = arr
        else resources.value = arr
    }

    function _removeResourceByAvid(avid) {
        if (!avid) return
        const arr = _resourcesArray()
        const idx = arr.findIndex(r => r.avid === avid)
        if (idx !== -1) {
            arr.splice(idx, 1)
        }
        if (Array.isArray(resources.value)) resources.value = arr
        else if (resources.value && Array.isArray(resources.value.results)) resources.value.results = arr
        else if (resources.value && Array.isArray(resources.value.data)) resources.value.data = arr
        else resources.value = arr
        // adjust pagination total if present
        if (pagination.value && typeof pagination.value.total === 'number') {
            pagination.value.total = Math.max(0, pagination.value.total - 1)
        }
    }

    // 统计信息
    const stats = computed(() => {
        const arr = _resourcesArray()
        const total = (pagination.value && pagination.value.total) || arr.length
        const downloadedCount = Array.isArray(downloads.value) ? downloads.value.length : arr.filter(r => r.has_video).length
        const pendingCount = Math.max(total - downloadedCount, arr.filter(r => !r.has_video).length)
        return {
            total,
            downloaded: downloadedCount,
            pending: pendingCount
        }
    })

    return {
        resources,
        sources,
        downloads,
        loading,
        error,
        pagination,
        stats,
        fetchResources,
        fetchSources,
        fetchDownloads,
        addResource,
        refreshResource,
        submitDownload,
        batchRefresh,
        batchDelete,
        batchSubmitDownload
    }
})
