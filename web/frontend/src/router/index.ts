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
    },
    // Agent功能已合并到Chat页面，通过模式切换使用
    {
        path: '/agent',
        name: 'Agent',
        redirect: '/'  // 重定向到首页
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

export default router
