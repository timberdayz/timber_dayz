import axios from "axios";

// ⭐ v6.0.0新增：现代化认证系统改进
// 导入 authStore（延迟导入避免循环依赖）
let authStore = null;
const getAuthStore = () => {
  if (!authStore) {
    // 动态导入避免循环依赖
    const { useAuthStore } = require("@/stores/auth");
    authStore = useAuthStore();
  }
  return authStore;
};

// 注意：所有API直接使用真实后端API，Mock数据已全部替换

// API超时配置（v4.1.0优化 - 动态超时）
// ⭐ v4.19.5 更新：增加数据同步超时时间
const TIMEOUTS = {
  default: 30000, // 默认30秒
  scan: 120000, // 扫描文件120秒
  preview: 60000, // 预览文件60秒
  ingest: 180000, // 数据入库180秒
  dashboard: 45000, // Dashboard查询45秒
  collection: 300000, // 数据采集300秒（5分钟）
  mapping: 90000, // 字段映射90秒
  sync: 120000, // ⭐ v4.19.5 新增：数据同步120秒（2分钟）
};

// ⭐ v6.0.0新增：不需要认证的接口列表
const NO_AUTH_PATHS = [
  "/auth/login",
  "/auth/refresh",
  "/health",
];

// ⭐ v6.0.0新增：CSRF Token 名称（Phase 3: CSRF 保护）
const CSRF_COOKIE_NAME = "csrf_token";

/**
 * 从 Cookie 读取 CSRF Token
 * 
 * ⭐ v6.0.0新增：Phase 3: CSRF 保护
 * 
 * @returns {string|null} CSRF Token 或 null
 */
function getCsrfTokenFromCookie() {
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === CSRF_COOKIE_NAME) {
      return decodeURIComponent(value);
    }
  }
  return null;
}

// ⭐ v6.0.0新增：Token 刷新预检查配置（Phase 4: 优化 Token 过期时间）
const TOKEN_REFRESH_THRESHOLD_MINUTES = 5; // 过期前 5 分钟自动刷新

/**
 * 解析 JWT Token 获取过期时间
 * 
 * ⭐ v6.0.0新增：Phase 4: Token 刷新预检查
 * 
 * @param {string} token - JWT Token
 * @returns {number|null} 过期时间戳（秒）或 null
 */
function getTokenExpiration(token) {
  if (!token) return null;
  
  try {
    // JWT 格式：header.payload.signature
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    
    // 解析 payload（Base64Url 编码）
    const payload = parts[1];
    // Base64Url 转 Base64
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    // 解码
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    
    const data = JSON.parse(jsonPayload);
    return data.exp || null;
  } catch (error) {
    console.warn('[Auth] 解析 token 过期时间失败:', error);
    return null;
  }
}

/**
 * 检查 Token 是否即将过期
 * 
 * ⭐ v6.0.0新增：Phase 4: Token 刷新预检查
 * 
 * @param {string} token - JWT Token
 * @returns {boolean} 是否即将过期（过期前 5 分钟）
 */
function isTokenExpiringSoon(token) {
  const exp = getTokenExpiration(token);
  if (!exp) return false;
  
  const now = Math.floor(Date.now() / 1000);
  const thresholdSeconds = TOKEN_REFRESH_THRESHOLD_MINUTES * 60;
  
  // 如果距离过期时间小于阈值，返回 true
  return exp - now < thresholdSeconds;
}

// ⭐ v6.0.0新增：Token 刷新锁（防止多个请求同时触发刷新）
let isRefreshing = false;
let failedQueue = [];

// ⭐ v6.0.0修复：多标签页同步机制（防止多个标签页同时刷新 token）
let refreshChannel = null;
let refreshTimeout = null; // ⭐ v6.0.0修复：超时机制，防止消息丢失或延迟

try {
  // 使用 BroadcastChannel API 在标签页之间同步刷新状态
  refreshChannel = new BroadcastChannel('token_refresh_channel');
  
  // 监听其他标签页的刷新状态
  refreshChannel.onmessage = (event) => {
    // ⭐ v6.0.0修复：清除超时定时器（收到消息）
    if (refreshTimeout) {
      clearTimeout(refreshTimeout);
      refreshTimeout = null;
    }
    
    if (event.data.type === 'refresh_started') {
      // 其他标签页开始刷新，标记本地状态
      isRefreshing = true;
      
      // ⭐ v6.0.0修复：设置超时机制（30秒），如果超时则重置状态
      refreshTimeout = setTimeout(() => {
        console.warn('[Auth] BroadcastChannel 消息超时，重置刷新状态');
        isRefreshing = false;
        refreshTimeout = null;
      }, 30000); // 30秒超时
    } else if (event.data.type === 'refresh_completed') {
      // 其他标签页刷新完成，更新本地 token 并处理队列
      const newToken = event.data.token;
      const newRefreshToken = event.data.refresh_token; // ⭐ v6.0.0修复：同时更新 refresh_token
      
      if (newToken) {
        // ⭐ v6.0.0修复：更新本地 token 和 refreshToken（确保状态一致性）
        try {
          const store = getAuthStore();
          store.token = newToken;
          localStorage.setItem('access_token', newToken);
          
          // ⭐ v6.0.0修复：如果响应中包含 refresh_token，也同步更新
          if (newRefreshToken) {
            store.refreshToken = newRefreshToken;
            localStorage.setItem('refresh_token', newRefreshToken);
          }
        } catch (error) {
          // 如果 authStore 未初始化，只更新 localStorage
          console.warn('[Auth] authStore 未初始化，只更新 localStorage:', error);
          localStorage.setItem('access_token', newToken);
          if (newRefreshToken) {
            localStorage.setItem('refresh_token', newRefreshToken);
          }
        }
        
        // 处理队列中的请求
        failedQueue.forEach(({ resolve }) => {
          resolve(newToken);
        });
        failedQueue = [];
      }
      isRefreshing = false;
    } else if (event.data.type === 'refresh_failed') {
      // 其他标签页刷新失败，拒绝队列中的请求
      const refreshError = new Error("Token refresh failed");
      failedQueue.forEach(({ reject }) => {
        reject(refreshError);
      });
      failedQueue = [];
      isRefreshing = false;
    }
  };
} catch (error) {
  // BroadcastChannel 不支持时（如某些浏览器），降级为单标签页模式
  console.warn('[Auth] BroadcastChannel 不支持，多标签页同步功能不可用');
}

// 创建axios实例
// ⭐ 修复：使用相对路径，通过Vite代理访问后端（支持Docker和本地模式）
const apiBaseURL = import.meta.env.VITE_API_BASE_URL || "/api";
const api = axios.create({
  baseURL: apiBaseURL, // 使用环境变量或相对路径（通过Vite代理）
  timeout: TIMEOUTS.default,
  headers: {
    "Content-Type": "application/json",
  },
});

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 记录请求开始时间（用于计算响应时间）
    config.metadata = {
      startTime: Date.now(),
    };
    
    // ⭐ v6.0.0新增：自动添加 Authorization Header
    // 排除不需要认证的接口
    const needsAuth = !NO_AUTH_PATHS.some(path => config.url.includes(path));
    if (needsAuth) {
      let token = null;
      try {
        const store = getAuthStore();
        token = store.token || localStorage.getItem('access_token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
      } catch (error) {
        // 如果 authStore 未初始化，从 localStorage 读取
        token = localStorage.getItem('access_token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
      }
      
      // ⭐ v6.0.0新增：Token 刷新预检查（Phase 4: 优化 Token 过期时间）
      // 如果 token 即将过期（过期前 5 分钟），在后台触发刷新
      if (token && isTokenExpiringSoon(token) && !isRefreshing) {
        // 在后台触发刷新，不阻塞当前请求
        (async () => {
          try {
            console.log('[Auth] Token 即将过期，后台触发刷新');
            isRefreshing = true;
            
            // 通知其他标签页开始刷新
            if (refreshChannel) {
              try {
                refreshChannel.postMessage({ type: 'refresh_started' });
              } catch (e) {
                console.warn('[Auth] 无法通知其他标签页:', e);
              }
            }
            
            const store = getAuthStore();
            const success = await store.refreshAccessToken();
            
            if (success) {
              console.log('[Auth] 后台 Token 刷新成功');
              // 通知其他标签页刷新完成
              if (refreshChannel) {
                try {
                  refreshChannel.postMessage({
                    type: 'refresh_completed',
                    token: store.token,
                    refresh_token: store.refreshToken
                  });
                } catch (e) {
                  console.warn('[Auth] 无法通知其他标签页:', e);
                }
              }
            } else {
              console.warn('[Auth] 后台 Token 刷新失败');
              // 通知其他标签页刷新失败
              if (refreshChannel) {
                try {
                  refreshChannel.postMessage({ type: 'refresh_failed' });
                } catch (e) {
                  console.warn('[Auth] 无法通知其他标签页:', e);
                }
              }
            }
          } catch (error) {
            console.error('[Auth] 后台 Token 刷新异常:', error);
          } finally {
            isRefreshing = false;
          }
        })();
      }
    }
    
    // ⭐ v6.0.0新增：自动添加 CSRF Token（Phase 3: CSRF 保护）
    // 对于 POST/PUT/DELETE 请求，从 Cookie 读取 CSRF Token 并添加到 Header
    const method = config.method?.toUpperCase();
    if (method && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
      // 从 Cookie 读取 CSRF Token
      const csrfToken = getCsrfTokenFromCookie();
      if (csrfToken) {
        config.headers['X-CSRF-Token'] = csrfToken;
      }
    }
    
    // 根据API路径动态设置超时时间
    if (!config.timeout || config.timeout === TIMEOUTS.default) {
      if (config.url.includes("/scan")) {
        config.timeout = TIMEOUTS.scan;
      } else if (config.url.includes("/preview")) {
        config.timeout = TIMEOUTS.preview;
      } else if (config.url.includes("/ingest")) {
        config.timeout = TIMEOUTS.ingest;
      } else if (config.url.includes("/dashboard")) {
        config.timeout = TIMEOUTS.dashboard;
      } else if (config.url.includes("/collection")) {
        config.timeout = TIMEOUTS.collection;
      } else if (config.url.includes("/mapping")) {
        config.timeout = TIMEOUTS.mapping;
      } else if (
        config.url.includes("/data-sync/batch") ||
        config.url.includes("/data-sync/batch-by-ids")
      ) {
        // ⭐ v4.17.0优化：批量同步API应该立即返回task_id，但给60秒缓冲时间
        // 批量同步是异步任务，不需要等待完成，但API调用本身可能需要一些时间
        config.timeout = 60000; // 60秒
      } else if (config.url.includes("/data-sync/single")) {
        // ⭐ v4.19.5 新增：单文件同步超时（120秒）
        // 单文件同步是异步任务，API会立即返回task_id，但给足够时间处理任务提交
        config.timeout = TIMEOUTS.sync; // 120秒
      }
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器（v4.6.0统一响应格式 - 首先判断success字段）
api.interceptors.response.use(
  (response) => {
    const data = response.data;
    
    // 首先判断success字段（统一响应格式）
    if (data && typeof data === "object" && "success" in data) {
      if (data.success === true) {
        // API成功：提取data字段返回给调用方（组件收到data内容）
        // 空数据处理：如果data为空（null、undefined），返回整个响应对象（包括success、message等）
        if (data.data === null || data.data === undefined) {
          return data; // 返回整个响应对象，前端可访问success、message等字段
        }
        return data.data; // 组件收到的是data字段内容，无需再检查success字段
      } else if (data.success === false) {
        // API业务错误：提取error字段，抛出错误（组件通过catch捕获）
        const apiError = new Error(data.message || "操作失败");
        apiError.code = data.error?.code;
        apiError.type = data.error?.type;
        apiError.detail = data.error?.detail;
        apiError.recovery_suggestion = data.error?.recovery_suggestion;
        apiError.isApiError = true; // 标记为API业务错误
        apiError.response = response; // 保留response对象
        // ⭐ v4.14.0新增：保留data字段（用于传递结构化错误数据如表头变化详情）
        apiError.data = data.data;
        apiError.error_code = data.data?.error_code; // 方便前端检查错误类型
        return Promise.reject(apiError);
      }
    }
    
    // 兼容旧格式（如果没有success字段，直接返回data）
    return data;
  },
  async (error) => {
    const config = error.config;
    
    // 初始化重试计数器
    if (!config.retryCount) {
      config.retryCount = 0;
    }
    
    // 自动重试机制（仅网络错误和超时）
    const shouldRetry =
      config.retryCount < 3 && 
      (error.code === "ECONNABORTED" ||
        error.code === "ETIMEDOUT" ||
        !error.response);
    
    if (shouldRetry) {
      config.retryCount += 1;
      console.warn(
        `请求失败，正在重试 (${config.retryCount}/3): ${config.url}`
      );
      
      // 等待递增时间后重试（1秒、2秒、3秒）
      await new Promise((resolve) =>
        setTimeout(resolve, config.retryCount * 1000)
      );
      
      return api(config);
    }
    
    // ⭐ v6.0.0新增：自动 Token 刷新机制
    // 检测 401 Unauthorized 错误
    if (error.response && error.response.status === 401) {
      const originalRequest = error.config;
      
      // 排除登录、刷新 token 等接口（避免无限循环）
      if (NO_AUTH_PATHS.some(path => originalRequest.url.includes(path))) {
        // 登录/刷新接口返回 401，直接返回错误
        const responseData = error.response.data;
        if (
          responseData &&
          typeof responseData === "object" &&
          "success" in responseData &&
          responseData.success === false
        ) {
          const apiError = new Error(responseData.message || "认证失败");
          apiError.code = responseData.error?.code || 401;
          apiError.type = responseData.error?.type || "AuthError";
          apiError.detail = responseData.error?.detail;
          apiError.recovery_suggestion = responseData.error?.recovery_suggestion;
          apiError.isApiError = true;
          apiError.response = error.response;
          return Promise.reject(apiError);
        }
        const httpError = new Error(
          error.response.data?.message || "认证失败"
        );
        httpError.code = 401;
        httpError.type = "AuthError";
        httpError.isApiError = true;
        httpError.response = error.response;
        return Promise.reject(httpError);
      }
      
      // 如果请求已经重试过（避免无限循环）
      if (originalRequest._retry) {
        // 刷新失败，清除 token 并跳转登录页
        try {
          const store = getAuthStore();
          await store.logout();
        } catch (err) {
          console.error("登出失败:", err);
          // 清除 localStorage
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('user_info');
        }
        // 跳转登录页（如果使用 Vue Router）
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
      
      // 如果正在刷新 token，将请求加入队列
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then(token => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return api(originalRequest);
          })
          .catch(err => {
            return Promise.reject(err);
          });
      }
      
      // 标记为正在刷新
      originalRequest._retry = true;
      isRefreshing = true;
      
      // ⭐ v6.0.0修复：通知其他标签页开始刷新
      if (refreshChannel) {
        try {
          refreshChannel.postMessage({ type: 'refresh_started' });
        } catch (error) {
          console.warn('[Auth] 无法通知其他标签页刷新状态:', error);
        }
      }
      
      try {
        const store = getAuthStore();
        const refreshed = await store.refreshAccessToken();
        
        if (refreshed) {
          // 刷新成功，更新 token
          const newToken = store.token || localStorage.getItem('access_token');
          
          // ⭐ v6.0.0修复：处理队列中的请求（成功时 resolve，失败时 reject）
          failedQueue.forEach(({ resolve }) => {
            resolve(newToken);
          });
          failedQueue = [];
          
          // ⭐ v6.0.0修复：通知其他标签页刷新完成（包含 refresh_token）
          if (refreshChannel) {
            try {
              const newRefreshToken = store.refreshToken || localStorage.getItem('refresh_token'); // ⭐ v6.0.0修复：获取 refresh_token
              refreshChannel.postMessage({ 
                type: 'refresh_completed', 
                token: newToken,
                refresh_token: newRefreshToken // ⭐ v6.0.0修复：同时发送 refresh_token
              });
            } catch (error) {
              console.warn('[Auth] 无法通知其他标签页刷新完成:', error);
            }
          }
          
          // ⭐ v6.0.0修复：清除超时定时器（刷新成功）
          if (refreshTimeout) {
            clearTimeout(refreshTimeout);
            refreshTimeout = null;
          }
          
          // 更新原始请求的 token 并重试
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return api(originalRequest);
        } else {
          // ⭐ v6.0.0修复：刷新失败，拒绝队列中的所有请求
          const refreshError = new Error("Token refresh failed");
          failedQueue.forEach(({ reject }) => {
            reject(refreshError);
          });
          failedQueue = [];
          
          // ⭐ v6.0.0修复：通知其他标签页刷新失败
          if (refreshChannel) {
            try {
              refreshChannel.postMessage({ type: 'refresh_failed' });
            } catch (error) {
              console.warn('[Auth] 无法通知其他标签页刷新失败:', error);
            }
          }
          
          // 清除 token 并跳转登录页
          try {
            const store = getAuthStore();
            await store.logout();
          } catch (err) {
            console.error("登出失败:", err);
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('user_info');
          }
          if (window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
          return Promise.reject(refreshError);
        }
      } catch (refreshError) {
        // ⭐ v6.0.0修复：刷新失败，拒绝队列中的所有请求
        console.error("Token 刷新失败:", refreshError);
        failedQueue.forEach(({ reject }) => {
          reject(refreshError);
        });
        failedQueue = [];
        
        // ⭐ v6.0.0修复：通知其他标签页刷新失败
        if (refreshChannel) {
          try {
            refreshChannel.postMessage({ type: 'refresh_failed' });
          } catch (error) {
            console.warn('[Auth] 无法通知其他标签页刷新失败:', error);
          }
        }
        
        // 清除 token 并跳转登录页
        try {
          const store = getAuthStore();
          await store.logout();
        } catch (err) {
          console.error("登出失败:", err);
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('user_info');
        }
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
        // ⭐ v6.0.0修复：清除超时定时器（刷新完成或失败）
        if (refreshTimeout) {
          clearTimeout(refreshTimeout);
          refreshTimeout = null;
        }
      }
    }
    
    // 网络错误或HTTP错误（404、500等）
    if (error.response) {
      // HTTP错误（404、500等）：检查响应格式
      const responseData = error.response.data;
      if (
        responseData &&
        typeof responseData === "object" &&
        "success" in responseData &&
        responseData.success === false
      ) {
        // 统一错误格式：提取error字段
        const apiError = new Error(responseData.message || "请求失败");
        apiError.code = responseData.error?.code || error.response.status;
        apiError.type = responseData.error?.type || "SystemError";
        apiError.detail = responseData.error?.detail;
        apiError.recovery_suggestion = responseData.error?.recovery_suggestion;
        apiError.isApiError = true;
        apiError.response = error.response;
        return Promise.reject(apiError);
      }
      // 非统一格式的HTTP错误：包装为统一格式
      const httpError = new Error(
        error.response.data?.message || `HTTP ${error.response.status} 错误`
      );
      httpError.code = error.response.status;
      httpError.type = "SystemError";
      httpError.isApiError = true;
      httpError.response = error.response;
      return Promise.reject(httpError);
    }
    
    // 真正的网络错误（无响应）
    const message = error.message || "网络连接失败，请检查网络";
    const networkError = new Error(message);
    networkError.isNetworkError = true; // 标记为网络错误
    networkError.code = "NETWORK_ERROR";
    networkError.type = "NetworkError";
    
    // 记录网络错误日志（性能监控）
    if (
      error.config &&
      error.config.metadata &&
      error.config.metadata.startTime
    ) {
      const duration = Date.now() - error.config.metadata.startTime;
      const url = error.config.url || error.config.baseURL + error.config.url;
      console.error(
        `[网络错误] ${error.config.method?.toUpperCase()} ${url} - 错误: ${message}, 响应时间: ${duration}ms`
      );
    }
    
    return Promise.reject(networkError);
  }
);

// API方法
export default {
  // 内部通用方法
  async _get(path, config = {}) {
    return await api.get(path, config);
  },
  async _post(path, data, config = {}) {
    return await api.post(path, data, config);
  },
  async _put(path, data) {
    return await api.put(path, data);
  },
  async _patch(path, data) {
    return await api.patch(path, data);
  },
  async _delete(path, config = {}) {
    return await api.delete(path, config);
  },
  async get(path) {
    return await api.get(path);
  },
  async post(path, data) {
    return await api.post(path, data);
  },
  async put(path, data) {
    return await api.put(path, data);
  },
  async delete(path) {
    return await api.delete(path);
  },
  // 健康检查
  async healthCheck() {
    return await this._get("/health");
  },

  // 扫描文件
  async scanFiles() {
    return await this._post("/field-mapping/scan", {
      directories: ["temp/outputs"],
    });
  },

  // 获取文件分组
  async getFileGroups() {
    // 使用模块化后端的文件分组API
    return await this._get("/field-mapping/file-groups");
  },

  // 预览文件（仅支持 file_id）
  async previewFile({ fileId, headerRow = 0 }) {
    return await this._post("/field-mapping/preview", {
      file_id: fileId,
      header_row: headerRow,
    });
  },

  // 获取字段映射建议
  async getFieldMappings({ columns, dataDomain }) {
    return await this._post("/field-mapping/generate-mapping", {
      columns,
      data_domain: dataDomain,
    });
  },

  /**
   * 应用模板（旧版API - 已不推荐）
   * @deprecated 自v4.4.1起废弃，使用 applyTemplateById 或 getTemplatesList 代替
   * 
   * 当前状态：
   * - FieldMapping.vue（已归档到backups/）使用
   * - FieldMappingEnhanced.vue（已归档到backups/20250131_field_mapping_audit/）已废弃
   * 
   * @param {Object} params - 参数
   * @returns {Promise} 响应
   */
  async applyTemplate({ columns, platform, domain, granularity, sheetName }) {
    // ⚠️ 旧版API，仅为兼容性保留
    return await this._post("/field-mapping/apply-template", {
      columns,
      platform,
      domain,
      granularity,
      sheet_name: sheetName,
    });
  },

  // 获取默认核心字段推荐
  async getDefaultDeduplicationFields({ dataDomain, subDomain }) {
    if (!dataDomain) {
      throw new Error("数据域为必填项");
    }
    return await this._get(
      "/field-mapping/templates/default-deduplication-fields",
      {
      params: {
        data_domain: dataDomain,
          sub_domain: subDomain || null,
        },
      }
    );
  },

  // 保存模板
  // ⭐ v4.6.0 DSS架构：使用新API路径和header_columns参数
  // ⭐ v4.14.0新增：添加deduplication_fields参数（必填）
  async saveTemplate({
    mappings,
    platform,
    domain,
    dataDomain,
    granularity,
    sheetName,
    headerRow,
    headerColumns,
    subDomain,
    deduplicationFields,
  }) {
    // 兼容domain和dataDomain两种参数名
    const finalDomain = dataDomain || domain;
    if (!platform || !finalDomain) {
      throw new Error("平台和数据域为必填项");
    }
    
    // ⭐ v4.14.0新增：验证deduplication_fields必填
    if (
      !deduplicationFields ||
      !Array.isArray(deduplicationFields) ||
      deduplicationFields.length === 0
    ) {
      throw new Error(
        "核心字段（deduplicationFields）为必填项，请至少选择1个字段"
      );
    }
    
    return await this._post("/field-mapping/templates/save", {
      platform,
      data_domain: finalDomain,
      granularity: granularity || null,
      header_columns: headerColumns || [], // ⭐ v4.6.0 DSS架构：使用header_columns
      template_name: `${platform}_${finalDomain}_${subDomain || ""}_${
        granularity || "all"
      }_v1`, // 默认模板名称
      created_by: "web_ui",
      header_row: headerRow || 0,
      sub_domain: subDomain || null,
      sheet_name: sheetName || null,
      deduplication_fields: deduplicationFields, // ⭐ v4.14.0新增：核心字段列表（必填）
      // ⭐ 向后兼容：如果提供了mappings，也传递（后端会忽略）
      mappings: mappings || {},
    });
  },

  // 数据验证
  async validateRows({ domain, rows }) {
    return await this._post("/field-mapping/validate", {
      data_domain: domain,
      rows,
    });
  },

  // 数据入库（仅支持 file_id）
  // ⭐ v4.6.0 DSS架构：添加header_columns参数
  async ingestFile({
    fileId,
    platform,
    domain,
    mappings = {},
    rows = [],
    header_row = 0,
    header_columns = [],
  }) {
    return await this._post("/field-mapping/ingest", {
      file_id: fileId,
      platform,
      data_domain: domain,
      mappings, // 向后兼容：保留mappings参数
      rows,
      header_row, // ⭐ v4.6.1新增：传递header_row参数
      header_columns, // ⭐ v4.6.0 DSS架构：传递原始表头字段列表
    });
  },

  // 获取Catalog状态
  async getCatalogStatus() {
    return await this._get("/field-mapping/catalog-status");
  },

  // ========== 数据库浏览器API（v4.7.0企业级增强） ==========
  
  // ⚠️ v4.12.0移除：数据浏览器API已移除，使用Metabase替代（http://localhost:8080）
  // // 获取所有数据表列表
  // async getTables() {
  //   return await this._get('/data-browser/tables')
  // },
  // 
  // // 查询数据表数据（企业级增强版）
  // async queryData(params) {
  //   // 如果filters是对象，转换为JSON字符串
  //   const queryParams = { ...params }
  //   if (queryParams.filters && typeof queryParams.filters === 'object') {
  //     queryParams.filters = JSON.stringify(queryParams.filters)
  //   }
  //   return await this._get('/data-browser/query', { params: queryParams })
  // },
  // 
  // // 获取表的统计信息（企业级增强版）
  // async getTableStats(table) {
  //   return await this._get('/data-browser/stats', { params: { table } })
  // },

  // ========== 主视图API（v4.12.0新增） ==========
  
  // 获取订单汇总（orders域主视图）
  async getOrderSummary(params = {}) {
    return await this._get("/main-views/orders/summary", { params });
  },

  // 获取流量汇总（traffic域主视图）
  async getTrafficSummary(params = {}) {
    return await this._get("/main-views/traffic/summary", { params });
  },

  // 获取库存明细（inventory域主视图）
  async getInventoryBySku(params = {}) {
    return await this._get("/main-views/inventory/by-sku", { params });
  },

  // 获取主视图信息
  async getMainViewsInfo() {
    return await this._get("/main-views/main-views/info");
  },

  // 获取销售明细（产品ID级别）
  async getSalesDetailByProduct(params = {}) {
    return await this._get("/management/sales-detail-by-product", { params });
  },

  // ⚠️ v4.12.0移除：数据浏览器字段映射和导出API已完全移除，使用Metabase替代

  // 清理无效文件
  async cleanupInvalidFiles() {
    return await this._post("/field-mapping/cleanup");
  },

  // 获取任务进度
  async getTaskProgress(taskId) {
    return await this._get(`/field-mapping/progress/${taskId}`);
  },

  // 列出所有任务
  async listTasks(status) {
    const params = status ? `?status=${status}` : "";
    return await this._get(`/field-mapping/progress${params}`);
  },

  // ========== 数据采集API ==========
  
  // 启动采集
  async startCollection({
    platform,
    account,
    dataDomains,
    dateRange,
    granularity = "daily",
  }) {
    return await this._post("/collection/start", {
      platform,
      account,
      data_domains: dataDomains,
      date_range: dateRange,
      granularity,
    });
  },

  // 获取采集任务状态
  async getCollectionStatus(taskId) {
    return await this._get(`/collection/status/${taskId}`);
  },

  // 获取全局采集状态
  async getGlobalCollectionStatus() {
    return await this._get("/collection/status");
  },

  // 获取采集历史
  async getCollectionHistory(limit = 50, platform = null) {
    const params = new URLSearchParams();
    if (limit) params.append("limit", limit);
    if (platform) params.append("platform", platform);
    const query = params.toString() ? `?${params.toString()}` : "";
    return await this._get(`/collection/history${query}`);
  },

  // 平台登录
  async platformLogin(platform, account) {
    return await this._post(`/collection/platforms/${platform}/login`, {
      platform,
      account,
    });
  },

  // 获取平台店铺列表
  async getPlatformShops(platform, account) {
    return await this._get(
      `/collection/platforms/${platform}/shops?account=${account}`
    );
  },

  // 获取支持的平台列表
  async getCollectionPlatforms() {
    return await this._get("/collection/platforms");
  },

  // 取消采集任务
  async cancelCollectionTask(taskId) {
    return await axios.delete(
      `http://localhost:8000/api/collection/tasks/${taskId}`
    );
  },

  // 获取文件完整路径
  async getFilePath(fileName, platform, domain) {
    return await this._get(
      `/field-mapping/files?file_name=${encodeURIComponent(
        fileName
      )}&platform=${encodeURIComponent(platform)}&domain=${encodeURIComponent(
        domain
      )}`
    );
  },

  // 获取文件完整信息（仅支持 file_id）
  async getFileInfo(fileId) {
    return await this._get(
      `/field-mapping/file-info?file_id=${encodeURIComponent(fileId)}`
    );
  },

  // ========== 字段映射增强API ==========
  
  // 获取支持的数据域列表
  async getDataDomains() {
    return await this._get("/field-mapping/data-domains");
  },

  // 获取指定数据域的字段映射
  async getDomainFieldMappings(domain) {
    return await this._get(`/field-mapping/field-mappings/${domain}`);
  },

  // 批量验证数据
  async bulkValidate(payload) {
    return await this._post("/field-mapping/bulk-validate", payload);
  },

  // 获取模板缓存统计
  async getTemplateCacheStats() {
    return await this._get("/field-mapping/template-cache/stats");
  },

  // 清理过期模板
  async cleanupTemplateCache(days = 30) {
    return await this._post("/field-mapping/template-cache/cleanup", { days });
  },

  // 查找相似模板
  async findSimilarTemplates(platform, domain, columns) {
    return await this._get(
      `/field-mapping/template-cache/similar?platform=${platform}&domain=${domain}&columns=${columns.join(
        ","
      )}`
    );
  },

  // 获取商品成本信息
  async getProductCost(platform, shopId, sku) {
    return await this._get(
      `/field-mapping/cost-auto-fill/product?platform=${platform}&shop_id=${shopId}&sku=${sku}`
    );
  },

  // 批量更新成本价
  async batchUpdateCosts(costUpdates) {
    return await this._post(
      "/field-mapping/cost-auto-fill/batch-update",
      costUpdates
    );
  },

  // 自动填充成本价
  async autoFillCosts(data) {
    return await this._post("/field-mapping/cost-auto-fill/auto-fill", data);
  },

  // ========== 后端健康检查（v4.4.1新增）==========

  /**
   * 检查后端服务健康状态
   * @returns {Promise<{healthy: boolean, database: boolean, message: string}>}
   */
  async checkBackendHealth() {
    try {
      const response = await this._get("/health");
      return {
        healthy: response.status === "healthy",
        database: response.database?.status === "connected",
        message: response.status === "healthy" ? "后端正常" : "后端异常",
      };
    } catch (error) {
      return {
        healthy: false,
        database: false,
        message: "后端未启动",
      };
    }
  },

  // ========== 模板管理（v4.4.1新版API）==========

  /**
   * 获取模板列表（新版API - 推荐）
   * @param {Object} params - 参数
   * @param {string} params.platform - 平台代码
   * @param {string} params.dataDomain - 数据域
   * @returns {Promise} 模板列表
   */
  async getTemplatesList({ platform, dataDomain }) {
    const params = {};
    if (platform) {
      params.platform = platform;
    }
    if (dataDomain) {
      params.data_domain = dataDomain;
    }
    const queryString = new URLSearchParams(params).toString();
    return await this._get(
      `/field-mapping/templates/list${queryString ? "?" + queryString : ""}`
    );
  },

  /**
   * 删除模板
   * @param {number} templateId - 模板ID
   */
  async deleteTemplate(templateId) {
    return await this._delete(`/field-mapping/templates/${templateId}`);
  },

  /**
   * 应用指定模板（新版API - 推荐）
   * @param {Object} params - 参数
   * @param {number} params.templateId - 模板ID
   * @param {string[]} params.columns - 列名列表
   * @returns {Promise} 应用结果
   */
  async applyTemplateById({ templateId, columns }) {
    return await this._post("/field-mapping/templates/apply", {
      template_id: templateId,
      columns,
    });
  },

  /**
   * 检测表头变化（v4.6.0新增）
   * @param {Object} params - 参数
   * @param {number} params.templateId - 模板ID
   * @param {string[]} params.currentColumns - 当前表头字段列表
   * @returns {Promise} 表头变化检测结果
   */
  async detectHeaderChanges({ templateId, currentColumns }) {
    return await this._post("/field-mapping/templates/detect-header-changes", {
      template_id: templateId,
      current_columns: currentColumns,
    });
  },

  // ========== 治理统计（v4.5.0新增）==========

  /**
   * 获取治理概览统计
   * @param {string} platform - 平台代码（可选）
   * @returns {Promise} {pending_files, template_coverage, today_auto_ingested, missing_templates_count}
   */
  async getGovernanceOverview(platform = null) {
    const params = platform ? `?platform=${platform}` : "";
    return await this._get(`/field-mapping/governance/overview${params}`);
  },

  /**
   * 获取缺少模板的域×粒度清单
   * @param {string} platform - 平台代码（可选）
   * @returns {Promise} [{domain, granularity, file_count}]
   */
  async getMissingTemplates(platform = null) {
    const params = platform ? `?platform=${platform}` : "";
    return await this._get(
      `/field-mapping/governance/missing-templates${params}`
    );
  },

  /**
   * 获取待入库文件列表
   * @param {Object} params - 筛选参数
   * @returns {Promise} [{file_id, file_name, platform, domain, granularity, ...}]
   */
  async getPendingFiles(params = {}) {
    const query = new URLSearchParams(params).toString();
    return await this._get(`/field-mapping/governance/pending-files?${query}`);
  },

  // ========== 自动入库（v4.5.0新增）==========

  /**
   * 单文件数据同步（v4.12.0更新：使用新的data-sync API）
   * @param {number} fileId - 文件ID
   * @param {boolean} onlyWithTemplate - 只处理有模板的文件
   * @param {boolean} allowQuarantine - 允许隔离错误数据
   * @param {CancelToken} cancelToken - 取消令牌（可选）
   * @returns {Promise} {success, file_id, file_name, status, message, task_id}
   */
  /**
   * 数据同步 - 文件预览（v4.6.0新增：支持表头行参数）
   * 
   * @param {number} fileId - 文件ID
   * @param {number} headerRow - 表头行（0-based，0=Excel第1行）
   */
  async previewFileWithHeaderRow(fileId, headerRow = 0) {
    return await this._post("/data-sync/preview", {
      file_id: fileId,
      header_row: headerRow,
    });
  },

  /**
   * 数据同步 - 文件列表（v4.6.0新增）
   * 
   * @param {object} filters - 筛选条件
   * @param {string} filters.platform - 平台代码
   * @param {string} filters.domain - 数据域
   * @param {string} filters.granularity - 粒度
   * @param {string} filters.sub_domain - 子类型
   * @param {string} filters.status - 状态（pending/ingested/failed）
   * @param {number} filters.limit - 数量限制
   */
  async getDataSyncFiles(filters = {}) {
    return await this._get("/data-sync/files", { params: filters });
  },

  /**
   * v4.18.0新增：获取同步历史记录
   * @param {Object} params - 查询参数
   * @param {string} params.status - 状态筛选
   * @param {number} params.limit - 数量限制
   */
  async getSyncHistory(params = {}) {
    return await this._get("/data-sync/tasks", { params });
  },

  async startSingleAutoIngest(
    fileId,
    onlyWithTemplate = true,
    allowQuarantine = true,
    useTemplateHeaderRow = true,
    cancelToken = null
  ) {
    const config = {};
    if (cancelToken) {
      config.cancelToken = cancelToken;
    }
    // ⭐ v4.12.0更新：统一使用data-sync API（移除双维护）
    const response = await this._post(
      "/data-sync/single",
      {
      file_id: fileId,
      only_with_template: onlyWithTemplate,
      allow_quarantine: allowQuarantine,
        use_template_header_row: useTemplateHeaderRow, // ⭐ v4.6.0新增
      },
      config
    );
    // 新API返回格式：{success, file_id, file_name, status, message, task_id}
    return response;
  },

  /**
   * 批量数据同步（v4.12.0更新：使用新的data-sync API）
   * @param {Object} config - 批量配置
   * @param {string} config.platform - 平台代码（必填，'*'表示全部平台）
   * @param {string[]} config.domains - 数据域列表（可选）
   * @param {string[]} config.granularities - 粒度列表（可选）
   * @param {number} config.since_hours - 最近N小时
   * @param {number} config.limit - 最多处理N个文件
   * @param {boolean} config.only_with_template - 只处理有模板的文件
   * @param {boolean} config.allow_quarantine - 允许隔离错误数据
   * @returns {Promise} {success, task_id, summary}
   */
  async startBatchAutoIngest(config) {
    // ⭐ v4.12.0更新：统一使用data-sync API（移除双维护）
    const response = await this._post("/data-sync/batch", config);
    // 新API返回格式：{success, task_id, summary}
    return response;
  },

  /**
   * 查询数据同步进度（v4.12.0更新：统一使用data-sync API）
   * @param {string} taskId - 任务ID
   * @returns {Promise} {task_id, total, processed, succeeded, quarantined, failed, ...}
   */
  async getAutoIngestProgress(taskId) {
    // ⭐ v4.12.0更新：统一使用data-sync API（移除双维护）
    // ⭐ 修复：响应拦截器已提取data字段，response就是data内容
    const data = await this._get(`/data-sync/progress/${taskId}`);
    if (data) {
      // ⭐ 修复：直接返回数据对象，而不是包装在{success, data}中（前端直接使用）
      return {
          task_id: data.task_id,
        type: data.task_type || "auto_ingest",
          total: data.total_files || 0,
        total_files: data.total_files || 0, // ⭐ 兼容两种字段名
          processed: data.processed_files || 0,
        processed_files: data.processed_files || 0, // ⭐ 兼容两种字段名
          succeeded: data.valid_rows || 0,
        valid_rows: data.valid_rows || 0, // ⭐ 兼容两种字段名
          quarantined: data.quarantined_rows || 0,
        quarantined_rows: data.quarantined_rows || 0, // ⭐ 兼容两种字段名
          failed: data.error_rows || 0,
        error_rows: data.error_rows || 0, // ⭐ 兼容两种字段名
        skipped: data.skipped_files || 0, // ⭐ 修复：从API返回的skipped_files读取
        skipped_files: data.skipped_files || 0, // ⭐ 新增：跳过文件数
        skipped_no_template: 0,
        success_files: data.success_files || 0, // ⭐ 新增：成功文件数
        failed_files: data.failed_files || 0, // ⭐ 新增：失败文件数
        status:
          data.status === "completed"
            ? "completed"
            : data.status === "failed"
            ? "failed"
            : data.status === "processing"
            ? "processing"
            : "running",
        percentage:
          data.file_progress ||
          (data.total_files > 0
            ? Math.round((data.processed_files / data.total_files) * 100)
            : 0),
          files: [],
        current_file: data.current_file || "",
        current_stage: data.status === "processing" ? "正在处理..." : "",
          estimated_time_remaining: null,
          errors: data.errors || [],
          warnings: data.warnings || [],
          start_time: data.start_time,
        elapsed_seconds: data.start_time
          ? Math.round((new Date() - new Date(data.start_time)) / 1000)
          : null,
        quality_check: data.task_details?.quality_check || null,
      };
      }
    // ⭐ 修复：返回null而不是{success: false, data: null}，前端会检查null
    return null;
  },

  /**
   * 数据丢失分析（v4.13.0新增）
   * @param {Object} params - 查询参数
   * @param {number} params.file_id - 文件ID（可选）
   * @param {string} params.task_id - 任务ID（可选）
   * @param {string} params.data_domain - 数据域（可选）
   * @returns {Promise} 数据丢失分析结果
   */
  async analyzeDataLoss(params = {}) {
    try {
      const data = await this._get("/data-sync/loss-analysis", { params });
      return data;
    } catch (error) {
      console.error("[API] 数据丢失分析失败:", error);
      throw error;
    }
  },

  /**
   * 数据丢失预警检查（v4.13.0新增）
   * @param {Object} params - 查询参数
   * @param {number} params.file_id - 文件ID（可选）
   * @param {string} params.task_id - 任务ID（可选）
   * @param {string} params.data_domain - 数据域（可选）
   * @param {number} params.threshold - 丢失率阈值（默认5.0）
   * @returns {Promise} 预警检查结果
   */
  async checkDataLossAlert(params = {}) {
    try {
      const data = await this._get("/data-sync/loss-alert", { params });
      return data;
    } catch (error) {
      console.error("[API] 数据丢失预警检查失败:", error);
      throw error;
    }
  },

  /**
   * 获取字段映射质量评分（v4.13.0新增）
   * @param {number} fileId - 文件ID
   * @returns {Promise} 字段映射质量评分结果
   */
  async getMappingQuality(fileId) {
    try {
      const data = await this._get("/data-sync/mapping-quality", {
        params: { file_id: fileId },
      });
      return data;
    } catch (error) {
      console.error("[API] 获取字段映射质量评分失败:", error);
      throw error;
    }
  },

  /**
   * 获取任务日志详情（v4.11.4新增）
   * @param {string} taskId - 任务ID
   * @param {number} limit - 返回数量限制
   * @returns {Promise} {success, task_id, logs, total}
   */
  async getTaskLogs(taskId, limit = 50) {
    return await this._get(`/field-mapping/auto-ingest/task/${taskId}/logs`, {
      limit,
    });
  },

  /**
   * 通过文件ID获取任务日志（v4.11.5新增）
   * @param {number} fileId - 文件ID
   * @param {number} limit - 返回数量限制
   * @returns {Promise} {success, file_id, logs, total}
   */
  async getTaskLogsByFileId(fileId, limit = 50) {
    return await this._get(`/field-mapping/auto-ingest/file/${fileId}/logs`, {
      limit,
    });
  },

  // 原始数据层查看API（v4.11.5新增）
  /**
   * 查看原始Excel数据
   * @param {number} fileId - 文件ID
   * @param {number} headerRow - 表头行（0-based）
   * @param {number} limit - 预览行数限制
   * @returns {Promise} 原始Excel数据
   */
  async viewRawExcel(fileId, headerRow = 0, limit = 100) {
    return await this._get(`/raw-layer/view/${fileId}`, {
      params: { header_row: headerRow, limit },
    });
  },

  /**
   * 查看staging数据
   * @param {number} fileId - 文件ID
   * @param {number} limit - 返回行数限制
   * @param {number} offset - 偏移量
   * @returns {Promise} staging数据
   */
  async viewStagingData(fileId, limit = 100, offset = 0) {
    return await this._get(`/raw-layer/staging/${fileId}`, {
      params: { limit, offset },
    });
  },

  /**
   * 对比原始数据与staging数据
   * @param {number} fileId - 文件ID
   * @param {number} headerRow - 表头行（0-based）
   * @returns {Promise} 对比报告
   */
  async compareRawAndStaging(fileId, headerRow = 0) {
    return await this._get(`/raw-layer/compare/${fileId}`, {
      params: { header_row: headerRow },
    });
  },

  // 数据流转追踪API（v4.11.5新增）
  /**
   * 追踪任务数据流转
   * @param {string} taskId - 任务ID
   * @returns {Promise} 任务数据流转信息
   */
  async traceTaskDataFlow(taskId) {
    return await this._get(`/data-flow/trace/task/${taskId}`);
  },

  /**
   * 按文件追踪数据流转
   * @param {number} fileId - 文件ID
   * @param {number} headerRow - 表头行（0-based）
   * @returns {Promise} 文件数据流转信息
   */
  async traceFileDataFlow(fileId, headerRow = 0) {
    return await this._get(`/data-flow/trace/file/${fileId}`, {
      params: { header_row: headerRow },
    });
  },

  /**
   * 导出丢失数据到Excel（v4.13.0新增）
   * @param {number} fileId - 文件ID
   * @param {number} headerRow - 表头行（0-based）
   * @returns {Promise} Excel文件下载
   */
  async exportLostData(fileId, headerRow = 0) {
    try {
      const response = await axios.get(
        `${this.baseURL}/raw-layer/export-lost-data/${fileId}`,
        {
          params: { header_row: headerRow },
          responseType: "blob",
          timeout: 60000,
        }
      );
      
      // 创建下载链接
      const blob = new Blob([response.data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      
      // 从Content-Disposition头获取文件名
      const contentDisposition = response.headers["content-disposition"];
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(
          /filename\*=UTF-8''(.+)/
        );
        if (filenameMatch) {
          link.download = decodeURIComponent(filenameMatch[1]);
        } else {
          const filenameMatch2 = contentDisposition.match(/filename="(.+)"/);
          if (filenameMatch2) {
            link.download = filenameMatch2[1];
          } else {
            link.download = `lost_data_${fileId}_${new Date().getTime()}.xlsx`;
          }
        }
      } else {
        link.download = `lost_data_${fileId}_${new Date().getTime()}.xlsx`;
      }
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
      return { success: true };
    } catch (error) {
      console.error("[API] 导出丢失数据失败:", error);
      throw error;
    }
  },

  // 连带率指标API（v4.11.5新增）
  /**
   * 获取连带率趋势分析
   * @param {string} platformCode - 平台代码（可选）
   * @param {string} shopId - 店铺ID（可选）
   * @param {string} startDate - 开始日期（YYYY-MM-DD）
   * @param {string} endDate - 结束日期（YYYY-MM-DD）
   * @param {string} granularity - 粒度（daily/weekly/monthly）
   * @returns {Promise} 连带率趋势数据
   */
  async getAttachRateTrend(
    platformCode,
    shopId,
    startDate,
    endDate,
    granularity = "daily"
  ) {
    const params = { start_date: startDate, end_date: endDate, granularity };
    if (platformCode) params.platform_code = platformCode;
    if (shopId) params.shop_id = shopId;
    return await this._get("/metrics/attach-rate/trend", { params });
  },

  /**
   * 获取连带率对比分析
   * @param {string} platforms - 平台代码列表（逗号分隔，可选）
   * @param {string} shops - 店铺ID列表（逗号分隔，可选）
   * @param {string} dateRange - 日期范围（7d/30d/90d/custom）
   * @param {string} startDate - 自定义开始日期（可选）
   * @param {string} endDate - 自定义结束日期（可选）
   * @returns {Promise} 连带率对比数据
   */
  async getAttachRateComparison(
    platforms,
    shops,
    dateRange = "7d",
    startDate,
    endDate
  ) {
    const params = { date_range: dateRange };
    if (platforms) params.platforms = platforms;
    if (shops) params.shops = shops;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    return await this._get("/metrics/attach-rate/comparison", { params });
  },

  // 平台对比分析API（v4.11.5增强）
  /**
   * 获取平台对比分析（增强版）
   * @param {string} platforms - 平台代码列表（逗号分隔，可选）
   * @param {string} startDate - 开始日期（YYYY-MM-DD）
   * @param {string} endDate - 结束日期（YYYY-MM-DD）
   * @param {string} metrics - 对比指标（逗号分隔，可选）
   * @returns {Promise} 平台对比数据
   */
  async getPlatformComparison(
    platforms,
    startDate,
    endDate,
    metrics = "gmv,orders,attach_rate,conversion_rate,aov"
  ) {
    const params = { start_date: startDate, end_date: endDate, metrics };
    if (platforms) params.platforms = platforms;
    return await this._get("/metrics/platform/comparison", { params });
  },

  // 数据一致性验证API（v4.11.5新增）
  /**
   * 跨平台数据一致性检查
   * @param {string} shopId - 店铺ID（可选）
   * @param {string} platforms - 平台代码列表（逗号分隔，可选）
   * @param {string} startDate - 开始日期（YYYY-MM-DD）
   * @param {string} endDate - 结束日期（YYYY-MM-DD）
   * @returns {Promise} 跨平台一致性检查结果
   */
  async checkCrossPlatformConsistency(shopId, platforms, startDate, endDate) {
    const params = { start_date: startDate, end_date: endDate };
    if (shopId) params.shop_id = shopId;
    if (platforms) params.platforms = platforms;
    return await this._get("/data-consistency/cross-platform", { params });
  },

  /**
   * 计算数据与源数据一致性验证（C类 vs B类）
   * @param {string} platformCode - 平台代码（可选）
   * @param {string} shopId - 店铺ID（可选）
   * @param {string} metricDate - 指标日期（YYYY-MM-DD）
   * @returns {Promise} 计算数据一致性验证结果
   */
  async checkCalculatedVsSourceConsistency(platformCode, shopId, metricDate) {
    const params = { metric_date: metricDate };
    if (platformCode) params.platform_code = platformCode;
    if (shopId) params.shop_id = shopId;
    return await this._get("/data-consistency/calculated-vs-source", {
      params,
    });
  },

  /**
   * 异常数据检测
   * @param {string} platformCode - 平台代码（可选）
   * @param {string} shopId - 店铺ID（可选）
   * @param {string} startDate - 开始日期（YYYY-MM-DD）
   * @param {string} endDate - 结束日期（YYYY-MM-DD）
   * @param {string} metric - 检测指标（gmv/orders/attach_rate/conversion_rate）
   * @param {number} threshold - 异常检测阈值（标准差倍数，默认3.0）
   * @returns {Promise} 异常数据检测结果
   */
  async detectDataAnomalies(
    platformCode,
    shopId,
    startDate,
    endDate,
    metric = "gmv",
    threshold = 3.0
  ) {
    const params = {
      start_date: startDate,
      end_date: endDate,
      metric,
      threshold,
    };
    if (platformCode) params.platform_code = platformCode;
    if (shopId) params.shop_id = shopId;
    return await this._get("/data-consistency/anomaly-detection", { params });
  },

  /**
   * 获取物化视图刷新日志（v4.11.4新增）
   * @param {string} viewName - 视图名称（可选）
   * @param {number} limit - 返回数量限制
   * @returns {Promise} {success, logs, total}
   */
  async getRefreshLog(viewName = null, limit = 50) {
    const params = { limit };
    if (viewName) params.view_name = viewName;
    return await this._get("/mv/refresh-log", params);
  },

  /**
   * 一键清理数据库中所有业务数据（开发阶段使用）
   * @param {boolean} confirm - 必须显式确认
   * @returns {Promise} {success, message, details}
   */
  async clearAllData(confirm = true) {
    return await this._post("/field-mapping/database/clear-all-data", {
      confirm,
    });
  },

  /**
   * 单文件自动入库
   * @param {number} fileId - 文件ID
   * @returns {Promise} {success, file_id, status, message}
   */
  async autoIngestSingleFile(fileId) {
    return await this._post("/field-mapping/auto-ingest/single", {
      file_id: fileId,
      only_with_template: true,
      allow_quarantine: true,
    });
  },

  // ========== 物化视图管理API（v4.9.0完整版）==========
  
  // 刷新所有物化视图
  async refreshAllMV() {
    return await this._post("/mv/refresh-all");
  },
  
  // 获取所有视图状态
  async getAllMVStatus() {
    return await this._get("/mv/status");
  },
  
  // 查询销售趋势
  async querySalesTrend(params) {
    return await this._get("/mv/query/sales-trend", { params });
  },
  
  // 查询TopN产品
  async queryTopProducts(params) {
    return await this._get("/mv/query/top-products", { params });
  },
  
  // 查询店铺汇总
  async queryShopSummary(params) {
    return await this._get("/mv/query/shop-summary", { params });
  },
  
  /**
   * 获取产品列表（库存管理）
   * @param {Object} params - 查询参数
   * @param {string} params.platform - 平台筛选
   * @param {string} params.shop_id - 店铺筛选
   * @param {string} params.keyword - 关键词搜索（SKU/名称）
   * @param {string} params.category - 分类筛选
   * @param {string} params.status - 状态筛选：active/inactive
   * @param {boolean} params.has_image - 是否有图片
   * @param {boolean} params.low_stock - 低库存预警
   * @param {number} params.page - 页码
   * @param {number} params.page_size - 每页数量
   * @returns {Promise} 产品列表（包含分页信息）
   */
  async getProducts(params = {}) {
    return await this._get("/products/products", { params });
  },
  
  // ========== 字段映射辞典物化视图显示标识API（v4.10.2新增）==========
  
  // 更新字段的物化视图显示标识
  async updateFieldMvDisplay(fieldCode, isMvDisplay) {
    return await this._put(
      `/field-mapping/dictionary/field/${fieldCode}/mv-display`,
      {
        is_mv_display: isMvDisplay,
      }
    );
  },
  
  // 批量更新字段的物化视图显示标识
  async batchUpdateFieldMvDisplay(updates) {
    return await this._put(
      "/field-mapping/dictionary/fields/mv-display/batch",
      {
        updates: updates,
      }
    );
  },
  
  // ========== 销售相关API（新增 - 支持Mock数据开关） ==========
  
  // 获取店铺销售表现（v4.11.0：从dashboard API获取）
  async getShopPerformance(params = {}) {
    // TODO: 需要创建专门的API端点，暂时使用dashboard数据
    return await this._get("/dashboard/shop-performance", { params });
  },
  
  // 获取销售PK排名（v4.11.0：从dashboard API获取）
  async getPKRanking(params = {}) {
    // TODO: 需要创建专门的API端点，暂时使用dashboard数据
    return await this._get("/dashboard/pk-ranking", { params });
  },
  
  // 获取销售战役列表
  async getCampaigns(params = {}) {
    return await this._get("/sales-campaigns", { params });
  },
  
  // 获取销售战役详情
  async getCampaignDetail(id) {
    return await this._get(`/sales-campaigns/${id}`);
  },
  
  // 创建销售战役
  async createCampaign(data) {
    return await this._post("/sales-campaigns", data);
  },
  
  // 更新销售战役
  async updateCampaign(id, data) {
    return await this._put(`/sales-campaigns/${id}`, data);
  },
  
  // 删除销售战役
  async deleteCampaign(id) {
    return await this._delete(`/sales-campaigns/${id}`);
  },
  
  // 计算销售战役达成情况
  async calculateCampaignAchievement(id) {
    return await this._post(`/sales-campaigns/${id}/calculate`);
  },
  
  // ========== 人力资源API ==========
  
  // 获取绩效评分列表
  async getPerformanceScores(params = {}) {
    return await this._get("/performance/scores", { params });
  },
  
  // 获取店铺绩效详情
  async getShopPerformanceDetail(platformCode, shopId, period) {
    return await this._get(`/performance/scores/${shopId}`, { 
      params: { platform_code: platformCode, period },
    });
  },
  
  // 获取绩效配置列表
  async getPerformanceConfigs(params = {}) {
    return await this._get("/performance/config", { params });
  },
  
  // 创建绩效配置
  async createPerformanceConfig(config) {
    return await this._post("/performance/config", config);
  },
  
  // 更新绩效配置
  async updatePerformanceConfig(configId, config) {
    return await this._put(`/performance/config/${configId}`, config);
  },
  
  // 计算绩效评分
  async calculatePerformanceScores(period, configId) {
    return await this._post("/performance/scores/calculate", null, {
      params: { period, config_id: configId },
    });
  },
  
  // ========== 目标管理API ==========
  
  // 获取目标列表
  async getTargets(params = {}) {
    return await this._get("/targets", { params });
  },
  
  // 获取目标详情
  async getTargetDetail(id) {
    return await this._get(`/targets/${id}`);
  },
  
  // 创建目标
  async createTarget(data) {
    return await this._post("/targets", data);
  },
  
  // 更新目标
  async updateTarget(id, data) {
    return await this._put(`/targets/${id}`, data);
  },
  
  // 删除目标
  async deleteTarget(id) {
    return await this._delete(`/targets/${id}`);
  },
  
  // 创建目标分解
  async createTargetBreakdown(targetId, breakdown) {
    return await this._post(`/targets/${targetId}/breakdown`, breakdown);
  },
  
  // ========== 库存API ==========
  
  // 获取滞销清理排名（v4.11.0：从dashboard API获取）
  async getClearanceRanking(params = {}) {
    // TODO: 需要创建专门的API端点，暂时使用dashboard数据
    return await this._get("/dashboard/clearance-ranking", { params });
  },
  
  // ========== 店铺分析API ==========
  
  // 获取店铺GMV趋势
  async getStoreGMVTrend(params = {}) {
    return await this._get("/store-analytics/gmv-trend", { params });
  },
  
  // 获取店铺转化率分析
  async getStoreConversionAnalysis(params = {}) {
    return await this._get("/store-analytics/conversion-analysis", { params });
  },
  
  // 获取店铺健康度评分
  async getStoreHealthScores(params = {}) {
    return await this._get("/store-analytics/health-scores", { params });
  },
  
  // 计算店铺健康度评分
  async calculateStoreHealthScores(params = {}) {
    return await this._post("/store-analytics/health-scores/calculate", null, {
      params,
    });
  },
  
  // 获取店铺流量分析
  async getStoreTrafficAnalysis(params = {}) {
    return await this._get("/store-analytics/traffic-analysis", { params });
  },
  
  // 获取店铺对比分析
  async getStoreComparison(params = {}) {
    return await this._get("/store-analytics/comparison", { params });
  },
  
  // 获取店铺预警提醒
  async getStoreAlerts(params = {}) {
    return await this._get("/store-analytics/alerts", { params });
  },
  
  // 生成店铺预警
  async generateStoreAlerts(params = {}) {
    return await this._post("/store-analytics/alerts/generate", null, {
      params,
    });
  },
  
  // ========== 业务概览API（v4.11.0新增） ==========
  
  // 获取业务概览5个核心KPI指标
  async getBusinessOverviewKPI(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.platforms) queryParams.append("platforms", params.platforms);
    if (params.shops) queryParams.append("shops", params.shops);
    if (params.start_date) queryParams.append("start_date", params.start_date);
    if (params.end_date) queryParams.append("end_date", params.end_date);
    const queryString = queryParams.toString();
    return await this._get(
      `/dashboard/business-overview/kpi${queryString ? "?" + queryString : ""}`
    );
  },
  
  // 获取业务概览数据对比（日/周/月度）
  async getBusinessOverviewComparison(params) {
    const queryParams = new URLSearchParams();
    queryParams.append("granularity", params.granularity);
    queryParams.append("date", params.date);
    if (params.platforms) queryParams.append("platforms", params.platforms);
    if (params.shops) queryParams.append("shops", params.shops);
    return await this._get(
      `/dashboard/business-overview/comparison?${queryParams.toString()}`
    );
  },
  
  // 获取店铺赛马数据
  async getBusinessOverviewShopRacing(params) {
    const queryParams = new URLSearchParams();
    queryParams.append("granularity", params.granularity);
    queryParams.append("date", params.date);
    queryParams.append("group_by", params.group_by || "shop");
    if (params.platforms) queryParams.append("platforms", params.platforms);
    return await this._get(
      `/dashboard/business-overview/shop-racing?${queryParams.toString()}`
    );
  },
  
  // 获取流量排名数据
  async getBusinessOverviewTrafficRanking(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.granularity)
      queryParams.append("granularity", params.granularity);
    if (params.dimension) queryParams.append("dimension", params.dimension);
    if (params.date) queryParams.append("date_value", params.date); // 后端API使用date_value参数
    if (params.platforms) queryParams.append("platforms", params.platforms);
    if (params.shops) queryParams.append("shops", params.shops);
    const queryString = queryParams.toString();
    return await this._get(
      `/dashboard/business-overview/traffic-ranking${
        queryString ? "?" + queryString : ""
      }`
    );
  },

  async getBusinessOverviewInventoryBacklog(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.days) queryParams.append("days", params.days);
    if (params.platforms) queryParams.append("platforms", params.platforms);
    if (params.shops) queryParams.append("shops", params.shops);
    const queryString = queryParams.toString();
    return await this._get(
      `/dashboard/business-overview/inventory-backlog${
        queryString ? "?" + queryString : ""
      }`
    );
  },
  
  // 获取经营指标数据（门店经营表格）
  async getBusinessOverviewOperationalMetrics(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.date) queryParams.append("date", params.date);
    if (params.platforms) queryParams.append("platforms", params.platforms);
    if (params.shops) queryParams.append("shops", params.shops);
    const queryString = queryParams.toString();
    return await this._get(
      `/dashboard/business-overview/operational-metrics${
        queryString ? "?" + queryString : ""
      }`
    );
  },

  // ========== 数据同步 - 数据治理（v4.6.0新增）==========

  /**
   * 获取可用的平台列表
   * @returns {Promise} {platforms: string[]}
   */
  async getAvailablePlatforms() {
    return await this._get("/data-sync/platforms");
  },

  /**
   * 获取数据治理统计（待同步/已同步数量）
   * @returns {Promise} {pending_count, ingested_count, failed_count, total_count}
   */
  async getDataSyncGovernanceStats() {
    return await this._get("/data-sync/governance/stats");
  },

  /**
   * 获取模板覆盖统计
   * @param {string} platform - 平台代码（可选）
   * @returns {Promise} {template_coverage, missing_templates_count, ...}
   */
  async getTemplateCoverage(platform = null) {
    const params = platform ? { platform } : {};
    return await this._get("/field-mapping/governance/overview", { params });
  },

  /**
   * 获取缺少模板的清单
   * @param {string} platform - 平台代码（可选）
   * @returns {Promise} [{domain, granularity, file_count}]
   */
  async getMissingTemplates(platform = null) {
    const params = platform ? { platform } : {};
    return await this._get("/field-mapping/governance/missing-templates", {
      params,
    });
  },

  /**
   * 获取详细的模板覆盖统计
   * @returns {Promise} {summary, covered, missing, needs_update}
   */
  async getDetailedTemplateCoverage() {
    return await this._get("/data-sync/governance/detailed-coverage");
  },

  /**
   * 手动全部数据同步（同步所有有模板的待同步文件）
   * @returns {Promise} {task_id, file_count, message}
   */
  async syncAllWithTemplate() {
    return await this._post("/data-sync/batch-all");
  },

  /**
   * 批量数据同步（基于文件ID列表）⭐ 新增（2025-11-27）
   * @param {number[]} fileIds - 文件ID列表
   * @param {boolean} onlyWithTemplate - 是否只处理有模板的文件
   * @param {boolean} allowQuarantine - 是否允许隔离错误数据
   * @param {boolean} useTemplateHeaderRow - 是否使用模板表头行
   * @returns {Promise} {task_id, total_files, processed_files, message}
   */
  async syncBatchByFileIds({
    fileIds,
    onlyWithTemplate = true,
    allowQuarantine = true,
    useTemplateHeaderRow = true,
  }) {
    return await this._post("/data-sync/batch-by-ids", {
      file_ids: fileIds,
      only_with_template: onlyWithTemplate,
      allow_quarantine: allowQuarantine,
      use_template_header_row: useTemplateHeaderRow,
    });
  },

  /**
   * 获取同步任务进度
   * @param {string} taskId - 任务ID
   * @returns {Promise} {task_id, status, total_files, processed_files, success_files, failed_files, progress, details}
   */
  async getSyncTaskProgress(taskId) {
    return await this._get(`/data-sync/progress/${taskId}`);
  },

  /**
   * 清理数据库（清理所有已入库的数据）
   * @returns {Promise} {deleted_counts, total_deleted_rows, reset_files_count}
   */
  async cleanupDatabase() {
    return await this._post("/data-sync/cleanup-database");
  },

  /**
   * 刷新待同步文件（重新扫描文件）
   * @returns {Promise} {scanned_count, message}
   */
  async refreshPendingFiles() {
    // 调用扫描文件API（修复：使用正确的API路径）
    return await this._post("/field-mapping/scan");
  },

  // ==================== 组件版本管理API (Phase 9.4) ====================

  /**
   * 获取组件版本列表
   * @param {Object} params - 查询参数 {platform, component_type, status, page, page_size}
   * @returns {Promise} {data, total, page, page_size}
   */
  async getComponentVersions(params) {
    return await this._get("/component-versions", { params });
  },

  /**
   * 获取组件版本详情
   * @param {number} versionId - 版本ID
   * @returns {Promise} 版本详情
   */
  async getComponentVersion(versionId) {
    return await this._get(`/component-versions/${versionId}`);
  },

  /**
   * 注册新版本
   * @param {Object} data - {component_name, version, file_path, description, is_stable, created_by}
   * @returns {Promise} 注册的版本信息
   */
  async registerComponentVersion(data) {
    return await this._post("/component-versions", data);
  },

  /**
   * 启动A/B测试
   * @param {number} versionId - 版本ID
   * @param {Object} data - {test_ratio, duration_days}
   * @returns {Promise} {success, message, test_start_at, test_end_at}
   */
  async startABTest(versionId, data) {
    return await this._post(`/component-versions/${versionId}/ab-test`, data);
  },

  /**
   * 停止A/B测试
   * @param {number} versionId - 版本ID
   * @returns {Promise} {success, message}
   */
  async stopABTest(versionId) {
    return await this._post(`/component-versions/${versionId}/stop-ab-test`);
  },

  /**
   * 提升为稳定版本
   * @param {number} versionId - 版本ID
   * @returns {Promise} {success, message}
   */
  async promoteToStable(versionId) {
    return await this._post(`/component-versions/${versionId}/promote`);
  },

  /**
   * 更新版本
   * @param {number} versionId - 版本ID
   * @param {Object} data - {is_active, description}
   * @returns {Promise} {success, message}
   */
  async updateComponentVersion(versionId, data) {
    return await this._patch(`/component-versions/${versionId}`, data);
  },

  /**
   * 测试组件版本（有头模式）
   * @param {number} versionId - 版本ID
   * @param {Object} data - {account_id}
   * @returns {Promise} {success, message, test_result, version_info}
   */
  async testComponentVersion(versionId, data) {
    return await this._post(`/component-versions/${versionId}/test`, data);
  },

  /**
   * 获取测试状态（v4.7.4 新增）
   * @param {number} versionId - 版本ID
   * @param {string} testId - 测试ID
   * @returns {Promise} {status, progress, current_step, test_result}
   */
  async getTestStatus(versionId, testId) {
    return await this._get(
      `/component-versions/${versionId}/test/${testId}/status`
    );
  },

  /**
   * 获取组件统计信息
   * @param {string} componentName - 组件名称
   * @returns {Promise} {success, component_name, versions}
   */
  async getComponentStatistics(componentName) {
    return await this._get(`/component-versions/${componentName}/statistics`);
  },

  /**
   * 删除组件版本（v4.8.0 新增）
   * @param {number} versionId - 版本ID
   * @returns {Promise} {success, message, deleted_version}
   */
  async deleteComponentVersion(versionId) {
    return await this._delete(`/component-versions/${versionId}`);
  },

  /**
   * 批量注册 Python 组件（v4.8.0 新增）
   * @param {Object} params - {platform: optional}
   * @returns {Promise} {success, registered_count, skipped_count, error_count, details}
   */
  async batchRegisterPythonComponents(params = {}) {
    return await this._post(
      "/component-versions/batch-register-python",
      params
    );
  },
};
