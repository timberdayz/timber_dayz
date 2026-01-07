/**
 * API配置模块
 * 提供统一的axios配置、错误处理和重试机制
 */

import axios from 'axios'

// API基础URL
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

// 请求超时时间（30秒）
export const REQUEST_TIMEOUT = 30000

// 最大重试次数
export const MAX_RETRY_COUNT = 3

// 重试延迟（毫秒）
export const RETRY_DELAY = 1000

/**
 * 创建axios实例
 * @param {string} baseURL - 基础URL
 * @param {number} timeout - 超时时间
 * @returns {AxiosInstance}
 */
export function createApiInstance(baseURL = API_BASE_URL, timeout = REQUEST_TIMEOUT) {
  const instance = axios.create({
    baseURL,
    timeout,
    headers: {
      'Content-Type': 'application/json'
    }
  })

  // 请求拦截器
  instance.interceptors.request.use(
    config => {
      // 添加认证token
      const token = localStorage.getItem('auth_token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }

      // 添加请求时间戳（用于计算耗时）
      config.metadata = { startTime: new Date().getTime() }

      return config
    },
    error => {
      console.error('请求错误:', error)
      return Promise.reject(error)
    }
  )

  // 响应拦截器
  instance.interceptors.response.use(
    response => {
      // 计算请求耗时
      if (response.config.metadata) {
        const endTime = new Date().getTime()
        const duration = endTime - response.config.metadata.startTime
        console.log(`API请求耗时: ${response.config.url} - ${duration}ms`)
      }

      return response.data
    },
    error => {
      return handleResponseError(error)
    }
  )

  return instance
}

/**
 * 处理响应错误
 * @param {Error} error - 错误对象
 * @returns {Promise}
 */
function handleResponseError(error) {
  if (!error.response) {
    // 网络错误或请求被取消
    if (axios.isCancel(error)) {
      console.log('请求被取消:', error.message)
      return Promise.reject(new Error('请求被取消'))
    }

    console.error('网络错误:', error.message)
    return Promise.reject(new Error('网络连接失败，请检查网络设置'))
  }

  const { status, data } = error.response

  // 根据HTTP状态码处理
  switch (status) {
    case 400:
      return Promise.reject(new Error(data?.detail || '请求参数错误'))
    
    case 401:
      // 未授权，清除token并跳转登录
      localStorage.removeItem('auth_token')
      window.location.href = '/login'
      return Promise.reject(new Error('登录已过期，请重新登录'))
    
    case 403:
      return Promise.reject(new Error(data?.detail || '没有权限访问该资源'))
    
    case 404:
      return Promise.reject(new Error(data?.detail || '请求的资源不存在'))
    
    case 422:
      // 数据验证错误
      if (data?.detail && Array.isArray(data.detail)) {
        const errors = data.detail.map(err => err.msg).join('; ')
        return Promise.reject(new Error(`数据验证失败: ${errors}`))
      }
      return Promise.reject(new Error(data?.detail || '数据验证失败'))
    
    case 429:
      return Promise.reject(new Error('请求过于频繁，请稍后再试'))
    
    case 500:
      return Promise.reject(new Error(data?.detail || '服务器内部错误'))
    
    case 502:
    case 503:
    case 504:
      return Promise.reject(new Error('服务暂时不可用，请稍后再试'))
    
    default:
      return Promise.reject(new Error(data?.detail || error.message || '请求失败'))
  }
}

/**
 * 请求重试装饰器
 * @param {Function} fn - API函数
 * @param {number} maxRetries - 最大重试次数
 * @param {number} delay - 重试延迟
 * @returns {Function}
 */
export function withRetry(fn, maxRetries = MAX_RETRY_COUNT, delay = RETRY_DELAY) {
  return async function(...args) {
    let lastError
    
    for (let i = 0; i <= maxRetries; i++) {
      try {
        return await fn(...args)
      } catch (error) {
        lastError = error
        
        // 如果是客户端错误（4xx），不进行重试
        if (error.response && error.response.status >= 400 && error.response.status < 500) {
          throw error
        }
        
        // 如果还有重试机会，等待后重试
        if (i < maxRetries) {
          console.log(`请求失败，${delay}ms后进行第${i + 1}次重试...`)
          await new Promise(resolve => setTimeout(resolve, delay * (i + 1))) // 指数退避
        }
      }
    }
    
    // 所有重试都失败
    console.error(`请求失败，已重试${maxRetries}次`)
    throw lastError
  }
}

/**
 * 批量请求处理（并发控制）
 * @param {Array} requests - 请求列表
 * @param {number} concurrency - 并发数
 * @returns {Promise<Array>}
 */
export async function batchRequest(requests, concurrency = 5) {
  const results = []
  const executing = []
  
  for (const request of requests) {
    const promise = Promise.resolve().then(() => request())
    results.push(promise)
    
    if (concurrency <= requests.length) {
      const execute = promise.then(() => executing.splice(executing.indexOf(execute), 1))
      executing.push(execute)
      
      if (executing.length >= concurrency) {
        await Promise.race(executing)
      }
    }
  }
  
  return Promise.allSettled(results)
}

/**
 * 取消令牌管理器
 */
export class CancelTokenManager {
  constructor() {
    this.tokens = new Map()
  }

  /**
   * 创建取消令牌
   * @param {string} key - 令牌键
   * @returns {CancelToken}
   */
  create(key) {
    // 如果已存在，先取消
    this.cancel(key)
    
    const source = axios.CancelToken.source()
    this.tokens.set(key, source)
    return source.token
  }

  /**
   * 取消请求
   * @param {string} key - 令牌键
   * @param {string} message - 取消消息
   */
  cancel(key, message = '请求被取消') {
    const source = this.tokens.get(key)
    if (source) {
      source.cancel(message)
      this.tokens.delete(key)
    }
  }

  /**
   * 取消所有请求
   */
  cancelAll() {
    this.tokens.forEach((source, key) => {
      source.cancel('批量取消请求')
    })
    this.tokens.clear()
  }
}

// 全局取消令牌管理器
export const globalCancelManager = new CancelTokenManager()

// 默认导出
export default {
  API_BASE_URL,
  REQUEST_TIMEOUT,
  MAX_RETRY_COUNT,
  RETRY_DELAY,
  globalCancelManager
}

