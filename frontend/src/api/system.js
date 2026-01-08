/**
 * 系统管理API
 * v4.20.0: 系统管理模块API
 */

import api from './index'

/**
 * 系统日志API
 */

// 获取系统日志列表
export const getSystemLogs = async (params = {}) => {
  return api.get('/system/logs', { params })
}

// 获取系统日志详情
export const getSystemLogDetail = async (logId) => {
  return api.get(`/system/logs/${logId}`)
}

// 导出系统日志
export const exportSystemLogs = async (params = {}) => {
  return api.post('/system/logs/export', params, { responseType: 'blob' })
}

// 清空系统日志
export const clearSystemLogs = async () => {
  return api.delete('/system/logs')
}

/**
 * 系统配置API
 */

// 获取系统基础配置
export const getSystemConfig = async () => {
  return api.get('/system/config')
}

// 更新系统基础配置
export const updateSystemConfig = async (config) => {
  return api.put('/system/config', config)
}

// 获取数据库配置
export const getDatabaseConfig = async () => {
  return api.get('/system/database/config')
}

// 更新数据库配置
export const updateDatabaseConfig = async (config) => {
  return api.put('/system/database/config', config)
}

// 测试数据库连接
export const testDatabaseConnection = async (config) => {
  return api.post('/system/database/test-connection', config)
}

/**
 * 安全设置API
 */

// 获取密码策略
export const getPasswordPolicy = async () => {
  return api.get('/system/security/password-policy')
}

// 更新密码策略
export const updatePasswordPolicy = async (policy) => {
  return api.put('/system/security/password-policy', policy)
}

// 获取登录限制配置
export const getLoginRestrictions = async () => {
  return api.get('/system/security/login-restrictions')
}

// 更新登录限制配置
export const updateLoginRestrictions = async (restrictions) => {
  return api.put('/system/security/login-restrictions', restrictions)
}

// 获取IP白名单
export const getIPWhitelist = async () => {
  return api.get('/system/security/ip-whitelist')
}

// 添加IP到白名单
export const addIPToWhitelist = async (ip) => {
  return api.post('/system/security/ip-whitelist', { ip })
}

// 从白名单移除IP
export const removeIPFromWhitelist = async (ip) => {
  return api.delete(`/system/security/ip-whitelist/${ip}`)
}

// 获取会话配置
export const getSessionConfig = async () => {
  return api.get('/system/security/session-config')
}

// 更新会话配置
export const updateSessionConfig = async (config) => {
  return api.put('/system/security/session-config', config)
}

// 获取2FA配置
export const get2FAConfig = async () => {
  return api.get('/system/security/2fa-config')
}

// 更新2FA配置
export const update2FAConfig = async (config) => {
  return api.put('/system/security/2fa-config', config)
}

/**
 * 数据备份与恢复API
 */

// 创建备份
export const createBackup = async (params = {}) => {
  return api.post('/system/backup/backups', params)
}

// 获取备份列表
export const getBackupList = async (params = {}) => {
  return api.get('/system/backup/backups', { params })
}

// 获取备份详情
export const getBackupDetail = async (backupId) => {
  return api.get(`/system/backup/backups/${backupId}`)
}

// 下载备份
export const downloadBackup = async (backupId) => {
  return api.get(`/system/backup/backups/${backupId}/download`, { responseType: 'blob' })
}

// 恢复备份
export const restoreBackup = async (backupId, params = {}) => {
  return api.post(`/system/backup/backups/${backupId}/restore`, params)
}

// 获取自动备份配置
export const getAutoBackupConfig = async () => {
  return api.get('/system/backup/config')
}

// 更新自动备份配置
export const updateAutoBackupConfig = async (config) => {
  return api.put('/system/backup/config', config)
}

/**
 * 系统维护API
 */

// 获取缓存状态
export const getCacheStatus = async () => {
  return api.get('/system/maintenance/cache/status')
}

// 清理缓存
export const clearCache = async (params = {}) => {
  return api.post('/system/maintenance/cache/clear', params)
}

// 获取数据状态
export const getDataStatus = async () => {
  return api.get('/system/maintenance/data/status')
}

// 清理数据
export const cleanData = async (params = {}) => {
  return api.post('/system/maintenance/data/clean', params)
}

// 检查系统升级
export const checkUpgrade = async () => {
  return api.get('/system/maintenance/upgrade/check')
}

// 执行系统升级
export const performUpgrade = async (params = {}) => {
  return api.post('/system/maintenance/upgrade', params)
}

/**
 * 通知配置API
 */

// 获取SMTP配置
export const getSMTPConfig = async () => {
  return api.get('/system/notification/smtp-config')
}

// 更新SMTP配置
export const updateSMTPConfig = async (config) => {
  return api.put('/system/notification/smtp-config', config)
}

// 测试SMTP连接（已废弃，使用 sendTestEmail）
export const testSMTPConnection = async () => {
  return api.post('/system/notification/test-email', {})
}

// 发送测试邮件
export const sendTestEmail = async (params) => {
  return api.post('/system/notification/test-email', params)
}

// 获取通知模板列表
export const getNotificationTemplates = async () => {
  return api.get('/system/notification/templates')
}

// 创建通知模板
export const createNotificationTemplate = async (template) => {
  return api.post('/system/notification/templates', template)
}

// 获取通知模板详情
export const getNotificationTemplate = async (templateId) => {
  return api.get(`/system/notification/templates/${templateId}`)
}

// 更新通知模板
export const updateNotificationTemplate = async (templateId, template) => {
  return api.put(`/system/notification/templates/${templateId}`, template)
}

// 删除通知模板
export const deleteNotificationTemplate = async (templateId) => {
  return api.delete(`/system/notification/templates/${templateId}`)
}

// 获取告警规则列表
export const getAlertRules = async () => {
  return api.get('/system/notification/alert-rules')
}

// 创建告警规则
export const createAlertRule = async (rule) => {
  return api.post('/system/notification/alert-rules', rule)
}

// 获取告警规则详情
export const getAlertRule = async (ruleId) => {
  return api.get(`/system/notification/alert-rules/${ruleId}`)
}

// 更新告警规则
export const updateAlertRule = async (ruleId, rule) => {
  return api.put(`/system/notification/alert-rules/${ruleId}`, rule)
}

// 删除告警规则
export const deleteAlertRule = async (ruleId) => {
  return api.delete(`/system/notification/alert-rules/${ruleId}`)
}

/**
 * 权限管理API
 */

// 获取权限列表
export const getPermissions = async (category = null) => {
  const params = category ? { category } : {}
  return api.get('/system/permissions', { params })
}

// 获取权限树
export const getPermissionTree = async () => {
  return api.get('/system/permissions/tree')
}

// 获取权限树（另一个端点）
export const getPermissionTreeAlt = async () => {
  return api.get('/permissions/tree')
}
