/**
 * API接口测试工具
 * 用于测试所有API接口的连通性和响应
 */

import api from './index'
import inventoryApi from './inventory'
import financeApi from './finance'
import ordersApi from './orders'

/**
 * 测试API连通性
 * @returns {Promise<Object>} 测试结果
 */
export async function testApiConnectivity() {
  const results = {
    timestamp: new Date().toISOString(),
    totalTests: 0,
    passed: 0,
    failed: 0,
    details: []
  }

  const tests = [
    // 基础API测试
    { name: '健康检查', fn: () => api.healthCheck() },
    { name: '获取文件分组', fn: () => api.getFileGroups() },
    { name: '获取数据域列表', fn: () => api.getDataDomains() },
    
    // 库存API测试
    { name: '获取库存列表', fn: () => inventoryApi.getInventoryList({ page: 1, pageSize: 10 }) },
    { name: '获取库存汇总', fn: () => inventoryApi.getInventorySummary({}) },
    { name: '获取低库存预警', fn: () => inventoryApi.getLowStockAlert({}) },
    
    // 财务API测试
    { name: '获取应收账款列表', fn: () => financeApi.getAccountsReceivable({ page: 1, pageSize: 10 }) },
    { name: '获取财务总览', fn: () => financeApi.getFinancialOverview({ startDate: '2025-10-01', endDate: '2025-10-23' }) },
    { name: '获取利润报表', fn: () => financeApi.getProfitReport({ startDate: '2025-10-01', endDate: '2025-10-23' }) },
    
    // 数据看板API测试（已迁移到 Metabase Question API）
    // TODO: 添加新的 Metabase Question API 测试
    
    // 订单API测试
    { name: '获取订单列表', fn: () => ordersApi.getOrderList({ page: 1, pageSize: 10 }) },
    { name: '获取订单统计', fn: () => ordersApi.getOrderStatistics({ startDate: '2025-10-01', endDate: '2025-10-23' }) }
  ]

  results.totalTests = tests.length

  // 串行执行测试（避免并发过高）
  for (const test of tests) {
    const startTime = Date.now()
    try {
      const response = await test.fn()
      const duration = Date.now() - startTime
      
      results.passed++
      results.details.push({
        name: test.name,
        status: 'passed',
        duration: `${duration}ms`,
        response: response ? '✓ 有数据返回' : '✓ 请求成功'
      })
      
      console.log(`✓ ${test.name} - ${duration}ms`)
    } catch (error) {
      const duration = Date.now() - startTime
      
      results.failed++
      results.details.push({
        name: test.name,
        status: 'failed',
        duration: `${duration}ms`,
        error: error.message
      })
      
      console.error(`✗ ${test.name} - ${error.message}`)
    }
  }

  return results
}

/**
 * 测试单个API端点
 * @param {string} name - 测试名称
 * @param {Function} fn - API函数
 * @param {Object} params - 请求参数
 * @returns {Promise<Object>} 测试结果
 */
export async function testSingleEndpoint(name, fn, params = {}) {
  const startTime = Date.now()
  
  try {
    const response = await fn(params)
    const duration = Date.now() - startTime
    
    return {
      name,
      status: 'success',
      duration: `${duration}ms`,
      response,
      timestamp: new Date().toISOString()
    }
  } catch (error) {
    const duration = Date.now() - startTime
    
    return {
      name,
      status: 'error',
      duration: `${duration}ms`,
      error: error.message,
      timestamp: new Date().toISOString()
    }
  }
}

/**
 * 生成测试报告
 * @param {Object} results - 测试结果
 * @returns {string} HTML格式的报告
 */
export function generateTestReport(results) {
  const successRate = ((results.passed / results.totalTests) * 100).toFixed(2)
  
  let html = `
    <div class="api-test-report">
      <h2>API接口连通性测试报告</h2>
      <div class="summary">
        <p>测试时间: ${new Date(results.timestamp).toLocaleString('zh-CN')}</p>
        <p>总测试数: ${results.totalTests}</p>
        <p>通过: <span class="passed">${results.passed}</span></p>
        <p>失败: <span class="failed">${results.failed}</span></p>
        <p>成功率: <span class="rate">${successRate}%</span></p>
      </div>
      <table class="details">
        <thead>
          <tr>
            <th>测试名称</th>
            <th>状态</th>
            <th>耗时</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
  `

  results.details.forEach(detail => {
    const statusClass = detail.status === 'passed' ? 'success' : 'error'
    const statusIcon = detail.status === 'passed' ? '✓' : '✗'
    const message = detail.response || detail.error || ''
    
    html += `
      <tr class="${statusClass}">
        <td>${detail.name}</td>
        <td>${statusIcon} ${detail.status}</td>
        <td>${detail.duration}</td>
        <td>${message}</td>
      </tr>
    `
  })

  html += `
        </tbody>
      </table>
    </div>
    
    <style>
      .api-test-report {
        font-family: Arial, sans-serif;
        padding: 20px;
      }
      .summary {
        background: #f5f5f5;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 20px;
      }
      .passed { color: #52c41a; font-weight: bold; }
      .failed { color: #f5222d; font-weight: bold; }
      .rate { color: #1890ff; font-weight: bold; }
      table.details {
        width: 100%;
        border-collapse: collapse;
      }
      table.details th,
      table.details td {
        border: 1px solid #ddd;
        padding: 12px;
        text-align: left;
      }
      table.details th {
        background: #1890ff;
        color: white;
      }
      tr.success {
        background: #f6ffed;
      }
      tr.error {
        background: #fff1f0;
      }
    </style>
  `

  return html
}

/**
 * 性能测试
 * @param {Function} fn - API函数
 * @param {Object} params - 请求参数
 * @param {number} iterations - 迭代次数
 * @returns {Promise<Object>} 性能测试结果
 */
export async function performanceTest(fn, params = {}, iterations = 10) {
  const durations = []
  
  for (let i = 0; i < iterations; i++) {
    const startTime = Date.now()
    try {
      await fn(params)
      const duration = Date.now() - startTime
      durations.push(duration)
    } catch (error) {
      console.error(`性能测试失败 (第${i + 1}次):`, error.message)
    }
  }

  if (durations.length === 0) {
    return {
      success: false,
      message: '所有请求都失败了'
    }
  }

  const avg = durations.reduce((a, b) => a + b, 0) / durations.length
  const min = Math.min(...durations)
  const max = Math.max(...durations)

  return {
    success: true,
    iterations,
    avgDuration: `${avg.toFixed(2)}ms`,
    minDuration: `${min}ms`,
    maxDuration: `${max}ms`,
    durations
  }
}

