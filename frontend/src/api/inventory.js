/**
 * 库存管理API模块
 * 提供库存查询、调整、预警等功能
 * 
 * 统一API调用规范：
 * - 使用统一的api实例（从index.js导入）
 * - 统一方法命名：getXxx、createXxx、updateXxx、deleteXxx
 * - 统一参数传递：GET使用params，POST/PUT/DELETE使用data
 * - 统一错误处理：由响应拦截器自动处理
 */

import api from './index.js'

export default {
  /**
   * 获取库存列表
   * @param {Object} params - 查询参数
   * @param {string} params.platform - 平台代码
   * @param {string} params.shopId - 店铺ID
   * @param {string} params.keyword - 搜索关键词（商品名/SKU）
   * @param {string} params.warehouseCode - 仓库代码
   * @param {boolean} params.lowStockOnly - 只显示低库存
   * @param {number} params.page - 页码
   * @param {number} params.pageSize - 每页条数
   * @returns {Promise} 库存列表
   */
  async getInventoryList(params = {}) {
    return await api._get('/inventory/list', { params })
  },

  /**
   * 获取库存详情
   * @param {number} productId - 商品ID
   * @returns {Promise} 库存详情
   */
  async getInventoryDetail(productId) {
    return await api._get(`/inventory/detail/${productId}`)
  },

  /**
   * 获取库存流水
   * @param {Object} params - 查询参数
   * @param {number} params.productId - 商品ID
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.transactionType - 交易类型
   * @param {number} params.page - 页码
   * @param {number} params.pageSize - 每页条数
   * @returns {Promise} 库存流水列表
   */
  async getInventoryTransactions(params = {}) {
    return await api._get('/inventory/transactions', { params })
  },

  /**
   * 获取低库存预警列表
   * @param {Object} params - 查询参数
   * @param {string} params.platform - 平台代码
   * @param {string} params.shopId - 店铺ID
   * @param {number} params.threshold - 预警阈值（百分比）
   * @returns {Promise} 低库存预警列表
   */
  async getLowStockAlert(params = {}) {
    return await api._get('/inventory/low-stock-alert', { params })
  },

  /**
   * 调整库存
   * @param {Object} data - 调整数据
   * @param {number} data.productId - 商品ID
   * @param {number} data.quantityChange - 变动数量
   * @param {string} data.transactionType - 交易类型
   * @param {string} data.reason - 调整原因
   * @param {string} data.operatorId - 操作员ID
   * @returns {Promise} 调整结果
   */
  async adjustInventory(data) {
    return await api._post('/inventory/adjust', data)
  },

  /**
   * 批量调整库存
   * @param {Array} adjustments - 调整列表
   * @returns {Promise} 批量调整结果
   */
  async batchAdjustInventory(adjustments) {
    return await api._post('/inventory/batch-adjust', { adjustments })
  },

  /**
   * 获取库存汇总统计
   * @param {Object} params - 查询参数
   * @param {string} params.platform - 平台代码
   * @param {string} params.shopId - 店铺ID
   * @param {string} params.warehouseCode - 仓库代码
   * @returns {Promise} 库存汇总统计
   */
  async getInventorySummary(params = {}) {
    return await api._get('/inventory/summary', { params })
  },

  /**
   * 获取库存周转率
   * @param {Object} params - 查询参数
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.platform - 平台代码
   * @returns {Promise} 库存周转率数据
   */
  async getInventoryTurnover(params = {}) {
    return await api._get('/inventory/turnover', { params })
  },

  /**
   * 导出库存数据
   * @param {Object} params - 导出参数
   * @returns {Promise} 导出文件blob
   */
  async exportInventory(params = {}) {
    return await api._get('/inventory/export', { 
      params,
      responseType: 'blob'
    })
  },

  /**
   * 设置安全库存
   * @param {Object} data - 设置数据
   * @param {number} data.productId - 商品ID
   * @param {number} data.safetyStock - 安全库存
   * @param {number} data.reorderPoint - 补货点
   * @returns {Promise} 设置结果
   */
  async setSafetyStock(data) {
    return await api._post('/inventory/safety-stock', data)
  },

  /**
   * 获取滞销清理排名
   * @param {Object} params - 查询参数
   * @param {string} params.granularity - 数据粒度（monthly/weekly）
   * @param {string} params.month - 月份（YYYY-MM格式，用于monthly粒度）
   * @param {string} params.week - 周（YYYY-WW格式，用于weekly粒度）
   * @param {string} params.platforms - 平台代码（逗号分隔）
   * @param {string} params.shops - 店铺ID（逗号分隔）
   * @returns {Promise} 滞销清理排名列表
   */
  async getClearanceRanking(params = {}) {
    return await api._get('/dashboard/clearance-ranking', { params })
  }
}

