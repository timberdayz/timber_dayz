/**
 * 数据看板API模块
 * 提供业务概览数据查询功能
 * 
 * 统一API调用规范：
 * - 使用统一的api实例（从index.js导入）
 * - 统一方法命名：queryXxx
 * - 统一参数传递：GET使用params
 * - 统一错误处理：由响应拦截器自动处理
 * 
 * 注意：所有方法都通过后端 Metabase Question 代理 API 获取数据
 */

import api from './index.js'

export default {
  /**
   * 查询业务概览KPI数据
   * @param {Object} params - 查询参数
   * @param {string} params.start_date - 开始日期
   * @param {string} params.end_date - 结束日期
   * @param {string} params.platforms - 平台代码（逗号分隔）
   * @param {string} params.shops - 店铺ID（逗号分隔）
   * @returns {Promise} KPI数据
   */
  async queryBusinessOverviewKpi(params = {}) {
    return await api._get('/dashboard/business-overview/kpi', { params })
  },

  /**
   * 查询业务概览对比数据
   * @param {Object} params - 查询参数
   * @param {string} params.granularity - 时间粒度（daily/weekly/monthly）
   * @param {string} params.date - 日期
   * @param {string} params.platforms - 平台代码（逗号分隔）
   * @param {string} params.shops - 店铺ID（逗号分隔）
   * @returns {Promise} 对比数据
   */
  async queryBusinessOverviewComparison(params = {}) {
    return await api._get('/dashboard/business-overview/comparison', { params })
  },

  /**
   * 查询店铺赛马数据
   * @param {Object} params - 查询参数
   * @param {string} params.granularity - 时间粒度
   * @param {string} params.date - 日期
   * @param {string} params.group_by - 分组维度（shop/account）
   * @param {string} params.platforms - 平台代码（逗号分隔）
   * @returns {Promise} 店铺赛马数据
   */
  async queryBusinessOverviewShopRacing(params = {}) {
    return await api._get('/dashboard/business-overview/shop-racing', { params })
  },

  /**
   * 查询流量排名数据
   * @param {Object} params - 查询参数
   * @param {string} params.granularity - 时间粒度
   * @param {string} params.dimension - 维度（shop/account）
   * @param {string} params.date_value - 日期值
   * @param {string} params.platforms - 平台代码（逗号分隔）
   * @param {string} params.shops - 店铺ID（逗号分隔）
   * @returns {Promise} 流量排名数据
   */
  async queryBusinessOverviewTrafficRanking(params = {}) {
    return await api._get('/dashboard/business-overview/traffic-ranking', { params })
  },

  /**
   * 查询库存积压数据
   * @param {Object} params - 查询参数
   * @param {number} params.days - 天数
   * @param {string} params.platforms - 平台代码（逗号分隔）
   * @param {string} params.shops - 店铺ID（逗号分隔）
   * @returns {Promise} 库存积压数据
   */
  async queryBusinessOverviewInventoryBacklog(params = {}) {
    return await api._get('/dashboard/business-overview/inventory-backlog', { params })
  },

  /**
   * 查询经营指标数据
   * @param {Object} params - 查询参数
   * @param {string} params.date - 日期
   * @param {string} params.platforms - 平台代码（逗号分隔）
   * @param {string} params.shops - 店铺ID（逗号分隔）
   * @returns {Promise} 经营指标数据
   */
  async queryBusinessOverviewOperationalMetrics(params = {}) {
    return await api._get('/dashboard/business-overview/operational-metrics', { params })
  },

  /**
   * 查询清仓排名数据
   * @param {Object} params - 查询参数
   * @param {string} params.start_date - 开始日期
   * @param {string} params.end_date - 结束日期
   * @param {string} params.platforms - 平台代码（逗号分隔）
   * @param {string} params.shops - 店铺ID（逗号分隔）
   * @param {number} params.limit - 返回数量
   * @returns {Promise} 清仓排名数据
   */
  async queryClearanceRanking(params = {}) {
    return await api._get('/dashboard/clearance-ranking', { params })
  }
}
