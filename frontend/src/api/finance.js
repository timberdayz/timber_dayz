/**
 * 财务管理API模块
 * 提供应收账款、收款记录、费用管理、利润分析等功能
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
   * 获取应收账款列表
   * @param {Object} params - 查询参数
   * @param {string} params.platform - 平台代码
   * @param {string} params.shopId - 店铺ID
   * @param {string} params.status - 状态（pending/paid/overdue）
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {number} params.page - 页码
   * @param {number} params.pageSize - 每页条数
   * @returns {Promise} 应收账款列表
   */
  async getAccountsReceivable(params = {}) {
    return await api._get('/finance/accounts-receivable', { params })
  },

  /**
   * 获取应收账款详情
   * @param {number} arId - 应收账款ID
   * @returns {Promise} 应收账款详情
   */
  async getARDetail(arId) {
    return await api._get(`/finance/accounts-receivable/${arId}`)
  },

  /**
   * 获取收款记录列表
   * @param {Object} params - 查询参数
   * @param {number} params.arId - 应收账款ID
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.paymentMethod - 收款方式
   * @param {number} params.page - 页码
   * @param {number} params.pageSize - 每页条数
   * @returns {Promise} 收款记录列表
   */
  async getPaymentReceipts(params = {}) {
    return await api._get('/finance/payment-receipts', { params })
  },

  /**
   * 记录收款
   * @param {Object} data - 收款数据
   * @param {number} data.arId - 应收账款ID
   * @param {number} data.orderId - 订单ID
   * @param {string} data.receiptDate - 收款日期
   * @param {number} data.receiptAmount - 收款金额
   * @param {string} data.paymentMethod - 收款方式
   * @param {string} data.bankAccount - 银行账户
   * @param {string} data.remark - 备注
   * @returns {Promise} 收款记录
   */
  async recordPayment(data) {
    return await api._post('/finance/record-payment', data)
  },

  /**
   * 获取费用列表
   * @param {Object} params - 查询参数
   * @param {string} params.platform - 平台代码
   * @param {string} params.shopId - 店铺ID
   * @param {string} params.expenseType - 费用类型
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {number} params.page - 页码
   * @param {number} params.pageSize - 每页条数
   * @returns {Promise} 费用列表
   */
  async getExpenses(params = {}) {
    return await api._get('/finance/expenses', { params })
  },

  /**
   * 添加费用记录
   * @param {Object} data - 费用数据
   * @param {string} data.platform - 平台代码
   * @param {string} data.shopId - 店铺ID
   * @param {number} data.orderId - 订单ID（可选）
   * @param {string} data.expenseType - 费用类型
   * @param {string} data.expenseDate - 费用日期
   * @param {number} data.amount - 费用金额
   * @param {string} data.description - 描述
   * @returns {Promise} 费用记录
   */
  async addExpense(data) {
    return await api._post('/finance/expenses', data)
  },

  /**
   * 获取利润报表
   * @param {Object} params - 查询参数
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.platform - 平台代码
   * @param {string} params.shopId - 店铺ID
   * @param {string} params.groupBy - 分组维度（day/week/month）
   */
  async getProfitReport(params) {
    return await api.get('/profit-report', { params })
  },

  /**
   * 获取逾期预警列表
   * @param {Object} params - 查询参数
   * @param {string} params.platform - 平台代码
   * @param {string} params.shopId - 店铺ID
   * @param {number} params.overdueDays - 逾期天数阈值
   */
  async getOverdueAlert(params) {
    return await api.get('/overdue-alert', { params })
  },

  /**
   * 获取财务总览
   * @param {Object} params - 查询参数
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.platform - 平台代码
   * @param {string} params.shopId - 店铺ID
   */
  async getFinancialOverview(params) {
    return await api.get('/overview', { params })
  },

  /**
   * 获取现金流分析
   * @param {Object} params - 查询参数
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.platform - 平台代码
   */
  async getCashFlowAnalysis(params) {
    return await api.get('/cash-flow', { params })
  },

  /**
   * 获取利润率分析
   * @param {Object} params - 查询参数
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.dimension - 分析维度（platform/shop/product）
   */
  async getProfitMarginAnalysis(params) {
    return await api.get('/profit-margin', { params })
  },

  /**
   * 获取费用占比分析
   * @param {Object} params - 查询参数
   * @param {string} params.startDate - 开始日期
   * @param {string} params.endDate - 结束日期
   * @param {string} params.platform - 平台代码
   */
  async getExpenseRatio(params) {
    return await api.get('/expense-ratio', { params })
  },

  async getProfitBasis(params) {
    return await api._get('/finance/profit-basis', { params })
  },

  async rebuildProfitBasis(data) {
    return await api._post('/finance/profit-basis/rebuild', data)
  },

  /**
   * 获取月度利润看板数据（只读）
   * @param {Object} params - 查询参数
   * @param {string} params.period_month - 月份（YYYY-MM）
   * @returns {Promise} 看板聚合数据（结果区 + 店铺分布 + 调整项）
   */
  async getFinanceDashboard(params = {}) {
    return await api._get('/finance/monthly-profit-settlement', { params })
  },

  /**
   * 新增一条人工调整项（看板唯一写入口，原因必填）
   * @param {Object} data - 调整项数据
   * @param {string} data.period_month - 月份（YYYY-MM）
   * @param {string} data.adjustment_type - 调整类型
   * @param {number} data.amount - 调整金额（有符号）
   * @param {string} data.reason - 调整原因（必填）
   * @returns {Promise} 新建的调整项
   */
  async createFinanceAdjustment(data) {
    return await api._post('/finance/monthly-profit-settlement/adjustments', data)
  },

  /**
   * 删除一条人工调整项
   * @param {number} adjustmentId - 调整项ID
   * @returns {Promise} 删除结果
   */
  async deleteFinanceAdjustment(adjustmentId) {
    return await api._delete(`/finance/monthly-profit-settlement/adjustments/${adjustmentId}`)
  }
}

