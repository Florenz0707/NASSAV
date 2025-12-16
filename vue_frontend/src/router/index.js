import {createRouter, createWebHistory} from 'vue-router'

const routes = [
    {
        path: '/',
        name: 'Home',
        component: () => import('../views/HomeView.vue')
    },
    {
        path: '/resources',
        name: 'Resources',
        component: () => import('../views/ResourcesView.vue')
    },
    {
        path: '/resource/:avid',
        name: 'ResourceDetail',
        component: () => import('../views/ResourceDetailView.vue'),
        props: true
    },
    {
        path: '/add',
        name: 'AddResource',
        component: () => import('../views/AddResourceView.vue')
    },
    {
        path: '/downloads',
        name: 'Downloads',
        component: () => import('../views/DownloadsView.vue')
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

export default router
