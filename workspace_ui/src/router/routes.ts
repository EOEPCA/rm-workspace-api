import type { RouteRecordRaw } from 'vue-router';
import ManagementPage from 'pages/ManagementPage.vue'
import HomePage from 'pages/HomePage.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', component: HomePage },
  { path: '/home', component: HomePage },
  { path: '/management', component: ManagementPage },
  // weitere Routen direkt auf Pages
  { path: '/:catchAll(.*)*', component: () => import('src/pages/ErrorNotFound.vue') }
];

export default routes;
