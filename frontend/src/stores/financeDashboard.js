/**
 * 月度利润看板 store（只读看板 + 唯一写入口：人工调整项）。
 *
 * 口径纪律：本 store **不生产任何金额**。
 * 净利润 / 员工侧分配额 / 人工调整额 / 公司留存 / 分配占比 / 超额标记
 * 全部由后端下发，前端只做渲染，不重算、不校验那些算术恒等式。
 */

import { defineStore } from 'pinia'
import financeApi from '@/api/finance'

/**
 * 金额格式化：千分位 + 币种符号。
 * ⚠️ 负数必须带前置负号可见：绝不截断为 0、绝不显示绝对值。
 * ⚠️ 缺失（null / undefined / 非数字）返回「—」占位，不补 0。
 */
export function formatDashboardAmount(value) {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  const absolute = Math.abs(numeric).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
  return `${numeric < 0 ? '-' : ''}¥${absolute}`
}

/**
 * 比率格式化：后端给 0–1 小数，展示统一成百分比（消除「标签写 %、值域 0–1」的不一致）。
 * ⚠️ 缺失返回「—」占位，绝不用 0 顶替。
 */
export function formatDashboardRatio(value) {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${(numeric * 100).toFixed(2)}%`
}

/**
 * 从后端错误里取出可读提示。
 * ⚠️ 必须把后端 detail 显示出来（FastAPI 的 HTTPException detail 在 response.data.detail）。
 */
export function extractDashboardError(error, fallback = '请求失败') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => item?.msg || item?.message)
      .filter((message) => typeof message === 'string' && message.trim())
    if (messages.length) return messages.join('；')
  }
  if (typeof error?.detail === 'string' && error.detail.trim()) return error.detail
  if (typeof error?.message === 'string' && error.message.trim()) return error.message
  return fallback
}

/** 统一响应信封 { success, data, timestamp } → data 载荷。 */
function unwrapPayload(response) {
  if (response && typeof response === 'object' && 'success' in response && 'data' in response) {
    return response.data ?? null
  }
  return response ?? null
}

export const useFinanceDashboardStore = defineStore('finance-dashboard', {
  state: () => ({
    periodMonth: '',
    dashboard: null,
    loading: false,
    error: '',
    submitting: false,
    actionError: ''
  }),

  getters: {
    /** 是否已拿到看板数据。 */
    hasDashboard: (state) => !!state.dashboard,
    /** 人工调整笔数（后端下发）。 */
    adjustmentCount: (state) => Number(state.dashboard?.manual_adjustment_count ?? 0)
  },

  actions: {
    /**
     * 拉取月度利润看板数据（只读）。
     * ⚠️ 失败必须落到 error 状态，由视图渲染进 el-alert —— 不允许失败对页面不可见。
     */
    async fetchDashboard(periodMonth) {
      const month = periodMonth || this.periodMonth
      this.loading = true
      this.error = ''
      try {
        const response = await financeApi.getFinanceDashboard({ period_month: month })
        this.dashboard = unwrapPayload(response)
        this.periodMonth = this.dashboard?.period_month || month
        return this.dashboard
      } catch (error) {
        this.error = extractDashboardError(error, '加载月度利润看板数据失败')
        this.dashboard = null
        throw error
      } finally {
        this.loading = false
      }
    },

    /**
     * 写操作成功后刷新看板。
     * ⚠️ 刷新失败不在这里覆盖 actionError：fetchDashboard 已把失败写进 error 状态，
     * 由页面顶部的 el-alert 呈现，避免把「刷新失败」说成「调整项失败」。
     */
    async refreshAfterWrite() {
      try {
        await this.fetchDashboard(this.periodMonth)
      } catch (_) {
        // 失败已落在 this.error 上
      }
    },

    /**
     * 新增一条人工调整项（看板唯一写入口）。
     * ⚠️ reason 必填：前端先拦一道，后端也会 400。
     */
    async addAdjustment(payload) {
      this.submitting = true
      this.actionError = ''
      try {
        const response = await financeApi.createFinanceAdjustment({
          period_month: payload.period_month,
          adjustment_type: payload.adjustment_type,
          amount: Number(payload.amount),
          reason: String(payload.reason ?? '').trim()
        })
        await this.refreshAfterWrite()
        return response
      } catch (error) {
        this.actionError = extractDashboardError(error, '新增人工调整项失败')
        throw error
      } finally {
        this.submitting = false
      }
    },

    /** 删除一条人工调整项。 */
    async removeAdjustment(adjustmentId) {
      this.submitting = true
      this.actionError = ''
      try {
        const response = await financeApi.deleteFinanceAdjustment(adjustmentId)
        await this.refreshAfterWrite()
        return response
      } catch (error) {
        this.actionError = extractDashboardError(error, '删除人工调整项失败')
        throw error
      } finally {
        this.submitting = false
      }
    }
  }
})
