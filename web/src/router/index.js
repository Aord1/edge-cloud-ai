import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Monitor', component: () => import('../views/Monitor.vue') },
  { path: '/dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
  { path: '/logs', name: 'Logs', component: () => import('../views/Logs.vue') },
  { path: '/chat', name: 'Chat', component: () => import('../views/Chat.vue') },
  { path: '/system', name: 'SystemStatus', component: () => import('../views/SystemStatus.vue') },
]

const router = createRouter({ history: createWebHistory(), routes })

export default router
