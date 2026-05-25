/**
 * Vue 应用主入口
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElLoadingDirective } from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import './assets/styles/variables.css'
import './assets/styles/base.css'

import App from './App.vue'
import router from './router'
import { useUserStore } from './stores/user'
import { useAuthStore } from './stores/auth'

async function bootstrapApp() {
  const app = createApp(App)

  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }

  const pinia = createPinia()
  app.use(pinia)

  const authStore = useAuthStore()
  authStore.initAuth()

  const userStore = useUserStore()
  if (authStore.isLoggedIn) {
    userStore.hydrateFromStorage()
    await userStore.initUserInfo()
  }

  app.use(router)
  app.directive('loading', ElLoadingDirective)

  app.config.errorHandler = (err, vm, info) => {
    console.error('Vue应用错误:', err, info, vm)
  }

  app.mount('#app')

  if (import.meta.env.DEV) {
    console.log('[frontend] app bootstrapped')
    console.log('[frontend] vue version:', app.version)
  }
}

bootstrapApp()
