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
    async function fetchResources() {
        loading.value = true
        error.value = null
        try {
            const response = await resourceApi.getList()
            resources.value = response.data || []
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

    // 统计信息
    const stats = computed(() => ({
        total: resources.value.length,
        downloaded: resources.value.filter(r => r.has_video).length,
        pending: resources.value.filter(r => !r.has_video).length
    }))

    return {
        resources,
        sources,
        downloads,
        loading,
        error,
        stats,
        fetchResources,
        fetchSources,
        fetchDownloads,
        addResource,
        refreshResource,
        submitDownload
    }
})
