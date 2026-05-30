/**
 * HTTP request wrapper.
 */

import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const request = axios.create({
  baseURL: '/api',
  timeout: 10000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  }
})

request.interceptors.request.use(
  (config) => {
    config.metadata = { startTime: new Date() }
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

request.interceptors.response.use(
  (response) => {
    const duration = new Date() - response.config.metadata.startTime
    console.log(`请求 ${response.config.url} 耗时: ${duration}ms`)

    const { data } = response
    if (data && typeof data === 'object' && 'code' in data) {
      if (data.code === 200) {
        return data.data
      }
      ElMessage.error(data.message || '请求失败')
      return Promise.reject(new Error(data.message || '请求失败'))
    }

    return data
  },
  (error) => {
    console.error('响应错误:', error)

    if (error.response) {
      const { status, data } = error.response

      switch (status) {
      case 401: {
        ElMessage.error('登录已过期，请重新登录')
        const userStore = useUserStore()
        userStore.logout()
        break
      }
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
