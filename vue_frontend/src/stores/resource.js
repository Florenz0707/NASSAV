import {defineStore} from 'pinia'
import {ref, computed} from 'vue'
import {resourceApi, sourceApi, downloadApi} from '../api'

export const useResourceStore = defineStore('resource', () => {
    const resources = ref([])
    const sources = ref([])
    const downloads = ref([])
    const loading = ref(false)
    const error = ref(null)

    // 获取资源列表
    // 支持分页和排序
    const pagination = ref({ total: 0, page: 1, page_size: 20, pages: 1 })
    async function fetchResources({ sort_by = 'metadata_create_time', order = 'desc', page = 1, page_size = 20 } = {}) {
        loading.value = true
        error.value = null
        try {
            console.debug('[resource] fetchResources params:', { sort_by, order, page, page_size })
            const response = await resourceApi.getList({ sort_by, order, page, page_size })
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
            await fetchResources()
            return response
        } catch (err) {
            error.value = err.message || '添加资源失败'
            throw err
        } finally {
            loading.value = false
        }
    }

    // 刷新资源
    async function refreshResource(avid) {
        try {
            const response = await resourceApi.refresh(avid)
            await fetchResources()
            return response
        } catch (err) {
            throw err
        }
    }

    // 提交下载
    async function submitDownload(avid) {
        try {
            const response = await downloadApi.submitDownload(avid)
            await fetchDownloads()
            return response
        } catch (err) {
            throw err
        }
    }

    // helper: normalize resources to an array
    function _resourcesArray() {
        const raw = resources.value
        if (Array.isArray(raw)) return raw
        if (raw && Array.isArray(raw.results)) return raw.results
        if (raw && Array.isArray(raw.data)) return raw.data
        return []
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
        submitDownload
    }
})
