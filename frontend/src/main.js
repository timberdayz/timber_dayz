/**
 * Vue应用主入口 - 现代化ERP系统
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

// 样式文件
import './assets/styles/variables.css'
import './assets/styles/base.css'

// 应用组件和配置
import App from './App.vue'
import router from './router'

// 工具函数
import { useUserStore } from './stores/user'
import { useAuthStore } from './stores/auth'

const app = createApp(App)

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 创建Pinia实例
const pinia = createPinia()
app.use(pinia)

// ⭐ v4.19.5 修复：初始化认证状态（恢复 token 和用户信息）
const authStore = useAuthStore()
authStore.initAuth()

// 初始化用户信息（用于权限检查）
const userStore = useUserStore()
userStore.initUserInfo()

// 使用插件
app.use(router)
app.use(ElementPlus, {
  locale: zhCn,
  size: 'default'
})

// 全局属性
app.config.globalProperties.$ELEMENT = { size: 'default' }

// 错误处理
app.config.errorHandler = (err, vm, info) => {
  console.error('Vue应用错误:', err, info)
}

// 挂载应用
app.mount('#app')

// 开发环境下的调试信息
if (import.meta.env.DEV) {
  console.log('🚀 西虹ERP系统前端已启动')
  console.log('📊 Vue版本:', app.version)
  console.log('🎨 Element Plus已加载')
  console.log('🗂️ Pinia状态管理已初始化')
  console.log('🛣️ Vue Router已配置')
}