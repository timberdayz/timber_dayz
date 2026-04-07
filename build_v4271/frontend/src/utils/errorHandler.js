/**
 * 错误处理工具函数（处理API错误和网络错误）
 * 
 * 重要区分：
 * - 空数据：API成功返回（success: true），但数据为空 → 显示"-"（由dataFormatter处理）
 * - API错误：API返回错误（success: false）或请求失败 → 显示错误信息（由本模块处理）
 */

/**
 * 判断是否为API错误
 * @param {Error} error - 错误对象
 * @returns {boolean} 是否为API错误
 */
export function isApiError(error) {
  return error && (error.isApiError === true || error.response)
}

/**
 * 判断是否为网络错误
 * @param {Error} error - 错误对象
 * @returns {boolean} 是否为网络错误
 */
export function isNetworkError(error) {
  return error && error.isNetworkError === true
}

/**
 * 格式化错误信息
 * @param {Error} error - 错误对象
 * @returns {string} 格式化后的错误信息
 */
export function formatError(error) {
  if (!error) {
    return '未知错误'
  }
  
  // 网络错误
  if (isNetworkError(error)) {
    return error.message || '网络连接失败，请检查网络'
  }
  
  // API错误
  if (isApiError(error)) {
    // 优先使用error.message（用户友好的错误信息）
    if (error.message) {
      return error.message
    }
    
    // 其次使用error.detail（详细错误信息）
    if (error.detail) {
      return error.detail
    }
    
    // 最后使用默认消息
    return '操作失败'
  }
  
  // 其他错误
  return error.message || '未知错误'
}

/**
 * 获取错误码
 * @param {Error} error - 错误对象
 * @returns {number|string} 错误码
 */
export function getErrorCode(error) {
  if (!error) {
    return 'UNKNOWN'
  }
  
  if (error.code) {
    return error.code
  }
  
  if (error.response && error.response.status) {
    return error.response.status
  }
  
  return 'UNKNOWN'
}

/**
 * 获取错误类型
 * @param {Error} error - 错误对象
 * @returns {string} 错误类型
 */
export function getErrorType(error) {
  if (!error) {
    return 'SystemError'
  }
  
  if (error.type) {
    return error.type
  }
  
  if (isNetworkError(error)) {
    return 'NetworkError'
  }
  
  if (isApiError(error)) {
    return 'ApiError'
  }
  
  return 'SystemError'
}

/**
 * 获取错误恢复建议
 * @param {Error} error - 错误对象
 * @returns {string|null} 错误恢复建议
 */
export function getRecoverySuggestion(error) {
  if (!error) {
    return null
  }
  
  if (error.recovery_suggestion) {
    return error.recovery_suggestion
  }
  
  // 根据错误类型提供默认恢复建议
  if (isNetworkError(error)) {
    return '请检查网络连接，稍后重试'
  }
  
  if (isApiError(error)) {
    const code = getErrorCode(error)
    
    // 根据错误码提供恢复建议
    if (code === 4001 || code === 4002 || code === 4003) {
      return '请重新登录'
    }
    
    if (code === 4101 || code === 4102 || code === 4103) {
      return '请联系管理员获取权限'
    }
    
    if (code === 4201 || code === 4202 || code === 4203 || code === 4204) {
      return '请检查输入参数是否正确'
    }
    
    if (code === 4301) {
      return '请求过于频繁，请稍后重试'
    }
  }
  
  return null
}

/**
 * 处理API错误（统一处理逻辑）
 * @param {Error} error - 错误对象
 * @param {object} options - 选项
 * @param {boolean} options.showMessage - 是否显示错误提示（默认true）
 * @param {boolean} options.logError - 是否记录错误日志（默认true）
 * @returns {object} 错误信息对象
 */
export function handleApiError(error, options = {}) {
  const {
    showMessage = true,
    logError = true
  } = options
  
  // 记录错误日志（开发环境）
  if (logError && import.meta.env.DEV) {
    console.error('[API错误]', {
      code: getErrorCode(error),
      type: getErrorType(error),
      message: formatError(error),
      detail: error.detail,
      recovery: getRecoverySuggestion(error),
      error
    })
  }
  
  // 显示错误提示
  if (showMessage) {
    showError(error)
  }
  
  return {
    code: getErrorCode(error),
    type: getErrorType(error),
    message: formatError(error),
    detail: error.detail,
    recovery: getRecoverySuggestion(error)
  }
}

/**
 * 显示错误提示（使用Element Plus的Message组件）
 * @param {Error} error - 错误对象
 */
export function showError(error) {
  if (!error) {
    return
  }
  
  // 动态导入Element Plus的Message组件（避免循环依赖）
  import('element-plus').then(({ ElMessage }) => {
    const message = formatError(error)
    const recovery = getRecoverySuggestion(error)
    
    // 组合错误信息和恢复建议
    const fullMessage = recovery ? `${message}\n${recovery}` : message
    
    // 根据错误类型选择不同的消息类型
    const type = getErrorType(error)
    let messageType = 'error'
    
    if (type === 'NetworkError') {
      messageType = 'warning'
    } else if (type === 'UserError') {
      messageType = 'warning'
    }
    
    ElMessage({
      message: fullMessage,
      type: messageType,
      duration: 5000,
      showClose: true
    })
  }).catch(() => {
    // 如果Element Plus未加载，使用console.error
    console.error('[错误]', formatError(error))
  })
}

/**
 * 处理网络错误
 * @param {Error} error - 网络错误对象
 */
export function handleNetworkError(error) {
  console.error('[网络错误]', error)
  showError(error)
}

