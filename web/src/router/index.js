import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Monitor', component: () => import('../views/Monitor.vue') },
]

const router = createRouter({ history: createWebHistory(), routes })

export default router
