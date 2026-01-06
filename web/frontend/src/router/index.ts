import { createRouter, createWebHistory } from 'vue-router'
import Chat from '@/pages/Chat.vue'
import Stats from '@/pages/Stats.vue'

const routes = [
    {
        path: '/',
        name: 'Chat',
        component: Chat
    },
    {
        path: '/stats',
        name: 'Stats',
        component: Stats
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

export default router
