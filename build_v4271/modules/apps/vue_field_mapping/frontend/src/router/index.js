import { createRouter, createWebHistory } from 'vue-router'
import FieldMapping from '../views/FieldMapping.vue'
import Dashboard from '../views/Dashboard.vue'

const routes = [
  {
    path: '/',
    name: 'FieldMapping',
    component: FieldMapping,
    meta: { title: 'Vue字段映射审核系统' }
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: Dashboard,
    meta: { title: '数据看板' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
