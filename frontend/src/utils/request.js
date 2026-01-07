/**
 * HTTP请求工具 - 基于Axios的现代化请求封装
 */

import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

// 创建axios实例
const request = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    // 添加认证token
    const userStore = useUserStore()
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    
    // 添加请求时间戳
    config.metadata = { startTime: new Date() }
    
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  (response) => {
    // 计算请求耗时
    const duration = new Date() - response.config.metadata.startTime
    console.log(`请求 ${response.config.url} 耗时: ${duration}ms`)
    
    // 统一处理响应数据
    const { data } = response
    
    // 如果后端返回的数据格式是 { code, data, message }
    if (data && typeof data === 'object' && 'code' in data) {
      if (data.code === 200) {
        return data.data
      } else {
        // 业务错误
        ElMessage.error(data.message || '请求失败')
        return Promise.reject(new Error(data.message || '请求失败'))
      }
    }
    
    return data
  },
  (error) => {
    console.error('响应错误:', error)
    
    // 处理HTTP错误
    if (error.response) {
      const { status, data } = error.response
      
      switch (status) {
        case 401:
          ElMessage.error('登录已过期，请重新登录')
          // 清除用户信息并跳转到登录页
          const userStore = useUserStore()
          userStore.logout()
          break
        case 403:
          ElMessage.error('没有权限访问该资源')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 500:
          ElMessage.error('服务器内部错误')
          break
        default:
          ElMessage.error(data?.message || `请求失败 (${status})`)
      }
    } else if (error.request) {
      ElMessage.error('网络连接失败，请检查网络')
    } else {
      ElMessage.error('请求配置错误')
    }
    
    return Promise.reject(error)
  }
)

// 请求方法封装
export const api = {
  get(url, params = {}, config = {}) {
    return request.get(url, { params, ...config })
  },
  
  post(url, data = {}, config = {}) {
    return request.post(url, data, config)
  },
  
  put(url, data = {}, config = {}) {
    return request.put(url, data, config)
  },
  
  delete(url, config = {}) {
    return request.delete(url, config)
  },
  
  upload(url, file, config = {}) {
    const formData = new FormData()
    formData.append('file', file)
    
    return request.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      ...config
    })
  }
}

export default request
