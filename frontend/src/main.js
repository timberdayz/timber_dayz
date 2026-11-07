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
import { loadSemanticFieldRegistry } from './domains/data_platform/utils/semanticFieldRegistryApi.js'

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

  // [*] 批次 D: 标准字段定义从接口取(前端不再自己抄一份)。
  //     模块加载时已经用生成快照铺了底, 这里只是刷新成权威数据 ——
  //     权威数据里额外带**运行时别名索引**(用户在模板里沉淀过的),
  //     那份是活的, 快照里没有。
  //     失败不阻断启动: 快照兜底够用, 页面不至于空白。
  loadSemanticFieldRegistry().catch(() => {})

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
