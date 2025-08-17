import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ManagementView from '../views/ManagementView.vue'

const routes = [
  {
    path: '/home',
    name: 'Home',
    component: HomeView
  },
  {
    path: '/management',
    name: 'Management',
    component: ManagementView
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router