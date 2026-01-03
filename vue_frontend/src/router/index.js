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
        path: '/resources/actors',
        name: 'Actors',
        component: () => import('../views/ActorsView.vue')
    },
    {
        path: '/resources/genres',
        name: 'Genres',
        component: () => import('../views/GenresView.vue')
    },
    {
        path: '/actors/:actorId',
        name: 'ActorResources',
        component: () => import('../views/ActorDetailView.vue'),
        props: true
    },
    {
        path: '/genres/:genreId',
        name: 'GenreResources',
        component: () => import('../views/GenreDetailView.vue'),
        props: true
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
    },
    {
        path: '/settings',
        name: 'Settings',
        component: () => import('../views/SettingsView.vue')
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

export default router
