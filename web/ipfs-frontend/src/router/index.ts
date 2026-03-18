import { createRouter, createWebHistory,type RouteRecordRaw } from 'vue-router'

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    redirect: '/dashboard'
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { title: '历史案件大盘' }
  },
  {
    path: '/gather',
    name: 'IntelligenceGathering',
    component: () => import('../views/IntelligenceGathering.vue'),
    meta: { title: '全网情报采集' }
  },
  {
    path: '/evidence',
    name: 'Evidence',
    component: () => import('../views/EvidenceCollect.vue'),
    meta: { title: '证据固定提取' }
  },
  {
    path: '/analysis',
    name: 'Analysis',
    component: () => import('../views/IdAnalysis.vue'),
    meta: { title: '身份画像分析' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
