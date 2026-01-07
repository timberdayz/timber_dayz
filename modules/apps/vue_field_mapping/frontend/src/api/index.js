import axios from 'axios'

// 创建axios实例
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    console.log(`🚀 API请求: ${config.method?.toUpperCase()} ${config.url}`)
    return config
  },
  error => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    console.log(`✅ API响应: ${response.config.url} - ${response.status}`)
    return response.data
  },
  error => {
    console.error('响应错误:', error)
    const message = error.response?.data?.message || error.message || '请求失败'
    return Promise.reject(new Error(message))
  }
)

// API方法
export const scanFiles = (directories) => {
  return api.post('/scan', { directories })
}

export const getFileGroups = () => {
  return api.get('/file-groups')
}

export const previewFile = (filePath, platform, dataDomain) => {
  return api.post('/file-preview', {
    file_path: filePath,
    platform,
    data_domain: dataDomain
  })
}

export const getFieldMapping = (columns, dataDomain) => {
  return api.post('/field-mapping', {
    columns,
    data_domain: dataDomain
  })
}

export const ingestFile = (filePath, platform, dataDomain, mappings) => {
  return api.post('/ingest', {
    file_path: filePath,
    platform,
    data_domain: dataDomain,
    mappings
  })
}

export const getCatalogStatus = () => {
  return api.get('/catalog/status')
}

export const cleanupInvalidFiles = () => {
  return api.post('/catalog/cleanup')
}

export const getHealth = () => {
  return api.get('/health')
}

export default api
