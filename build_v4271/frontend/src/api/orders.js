/**
 * 订单管理API模块
 * 提供订单查询、详情、取消、退款等功能
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
   * 获取订单列表
   * @param {Object} params - 查询参数
   * @param {string} params.platform - 平台代码
   * @param {string} params.shopId - 店铺ID
   * @param {string} params.orderStatus - 订单状态
   * @param {string} params.paymentStatus - 支付状态
   * @param {boolean} params.isInvoiced - 是否已开票
   * @param {boolean} params.isPaymentReceived - 是否已收款
   * @param {boolean} params.inventoryDeducted - 是否已扣库存
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.keyword - 搜索关键词（订单号/商品名）
   * @param {number} params.page - 页码
   * @param {number} params.pageSize - 每页条数
   * @returns {Promise} 订单列表
   */
  async getOrderList(params = {}) {
    return await api._get('/orders/list', { params })
  },

  /**
   * 获取订单详情（包含成本、利润）
   * @param {number} orderId - 订单ID
   * @returns {Promise} 订单详情
   */
  async getOrderDetail(orderId) {
    return await api._get(`/orders/detail/${orderId}`)
  },

  /**
   * 获取订单明细
   * @param {number} orderId - 订单ID
   * @returns {Promise} 订单明细列表
   */
  async getOrderItems(orderId) {
    return await api._get(`/orders/${orderId}/items`)
  },

  /**
   * 取消订单（自动恢复库存）
   * @param {Object} data - 取消数据
   * @param {number} data.orderId - 订单ID
   * @param {string} data.reason - 取消原因
   * @param {string} data.operatorId - 操作员ID
   * @returns {Promise} 取消结果
   */
  async cancelOrder(data) {
    return await api._post('/orders/cancel', data)
  },

  /**
   * 退款处理（调整应收账款）
   * @param {Object} data - 退款数据
   * @param {number} data.orderId - 订单ID
   * @param {number} data.refundAmount - 退款金额
   * @param {string} data.refundType - 退款类型（full/partial）
   * @param {string} data.reason - 退款原因
   * @param {boolean} data.restoreInventory - 是否恢复库存
   * @returns {Promise} 退款结果
   */
  async refundOrder(data) {
    return await api._post('/orders/refund', data)
  },

  /**
   * 批量导入订单
   * @param {Object} data - 导入数据
   * @param {string} data.platform - 平台代码
   * @param {string} data.shopId - 店铺ID
   * @param {Array} data.orders - 订单列表
   * @returns {Promise} 导入结果
   */
  async batchImportOrders(data) {
    return await api._post('/orders/batch-import', data)
  },

  /**
   * 同步订单状态
   * @param {Object} data - 同步数据
   * @param {number} data.orderId - 订单ID
   * @param {string} data.platform - 平台代码
   * @returns {Promise} 同步结果
   */
  async syncOrderStatus(data) {
    return await api._post('/orders/sync-status', data)
  },

  /**
   * 标记订单为已开票
   * @param {Object} data - 开票数据
   * @param {number} data.orderId - 订单ID
   * @param {number} data.invoiceId - 发票ID
   * @param {string} data.invoiceDate - 开票日期
   * @returns {Promise} 标记结果
   */
  async markAsInvoiced(data) {
    return await api._post('/orders/mark-invoiced', data)
  },

  /**
   * 标记订单为已收款
   * @param {Object} data - 收款数据
   * @param {number} data.orderId - 订单ID
   * @param {number} data.paymentVoucherId - 收款凭证ID
   * @param {string} data.receiptDate - 收款日期
   * @returns {Promise} 标记结果
   */
  async markAsPaymentReceived(data) {
    return await api._post('/orders/mark-payment-received', data)
  },

  /**
   * 获取订单统计
   * @param {Object} params - 查询参数
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.platform - 平台代码
   * @param {string} params.groupBy - 分组维度
   * @returns {Promise} 订单统计数据
   */
  async getOrderStatistics(params = {}) {
    return await api._get('/orders/statistics', { params })
  },

  /**
   * 导出订单数据
   * @param {Object} params - 导出参数
   * @returns {Promise} 导出文件blob
   */
  async exportOrders(params = {}) {
    return await api._get('/orders/export', {
      params,
      responseType: 'blob'
    })
  },

  /**
   * 获取订单时间线
   * @param {number} orderId - 订单ID
   * @returns {Promise} 订单时间线数据
   */
  async getOrderTimeline(orderId) {
    return await api._get(`/orders/${orderId}/timeline`)
  },

  /**
   * 批量更新订单状态
   * @param {Object} data - 更新数据
   * @param {Array} data.orderIds - 订单ID列表
   * @param {string} data.status - 新状态
   * @returns {Promise} 批量更新结果
   */
  async batchUpdateStatus(data) {
    return await api._post('/orders/batch-update-status', data)
  },

  /**
   * 获取订单利润明细
   * @param {number} orderId - 订单ID
   * @returns {Promise} 订单利润明细
   */
  async getOrderProfit(orderId) {
    return await api._get(`/orders/${orderId}/profit`)
  }
}

