<template>
  <div class="performance-display erp-page-container">
    <h1 class="page-title">绩效公示</h1>
    <p class="page-subtitle">
      面向全员展示店铺或人员维度的绩效结果，并支持查看赛马池与预警状态。
    </p>

    <div class="action-bar">
      <el-date-picker
        v-model="filters.period"
        type="month"
        format="YYYY-MM"
        value-format="YYYY-MM"
        placeholder="选择月份"
        size="default"
        style="width: 180px;"
        @change="loadPerformanceList"
      />
      <el-radio-group v-model="filters.groupBy" size="default" @change="loadPerformanceList">
        <el-radio-button value="shop">按店铺</el-radio-button>
        <el-radio-button value="person">按人员</el-radio-button>
      </el-radio-group>
      <el-button :icon="Refresh" @click="loadPerformanceList">刷新</el-button>
      <el-button
        v-if="hasPermission('performance:config')"
        type="warning"
        :loading="calculating"
        @click="handleRecalculate"
      >
        重新计算
      </el-button>
      <el-select v-model="poolFilter" size="default" style="width: 120px;">
        <el-option label="全部池" value="all" />
        <el-option label="正式池" value="official" />
        <el-option label="观察池" value="observation" />
      </el-select>
      <el-select v-model="alertFilter" size="default" style="width: 140px;">
        <el-option label="全部预警" value="all" />
        <el-option label="无预警" value="none" />
        <el-option label="黄牌" value="yellow" />
        <el-option label="红牌" value="red" />
        <el-option label="淘汰评估" value="elimination" />
      </el-select>
      <el-select
        v-model="filters.platform"
        placeholder="选择平台"
        clearable
        size="default"
        style="width: 140px; margin-left: auto;"
        @change="loadPerformanceList"
      >
        <el-option label="全部平台" value="" />
        <el-option label="Shopee" value="Shopee" />
        <el-option label="Lazada" value="Lazada" />
      </el-select>
    </div>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>绩效公示</span>
          <div class="card-hint">绩效构成：{{ formulaText }}</div>
        </div>
      </template>

      <el-table :data="filteredPerformanceData" stripe v-loading="performanceList.loading" class="erp-table" border>
        <el-table-column
          :prop="filters.groupBy === 'person' ? 'employee_name' : 'shop_name'"
          :label="filters.groupBy === 'person' ? '人员' : '店铺'"
          width="180"
          fixed="left"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            {{ filters.groupBy === 'person' ? (row.employee_name || row.employee_code || '—') : (row.shop_name || row.shop_id || '—') }}
          </template>
        </el-table-column>
        <el-table-column label="销售额目标" width="110" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_target) }}</template>
        </el-table-column>
        <el-table-column label="销售额达成" width="110" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_achieved) }}</template>
        </el-table-column>
        <el-table-column label="销售额达成率" width="120" align="right">
          <template #default="{ row }">{{ formatPercent(row.sales_rate) }}</template>
        </el-table-column>
        <el-table-column label="销售额得分" width="100" align="right">
          <template #default="{ row }">{{ scoreText(row.sales_score) }}</template>
        </el-table-column>
        <el-table-column label="毛利目标" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.profit_target) }}</template>
        </el-table-column>
        <el-table-column label="毛利达成" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.profit_achieved) }}</template>
        </el-table-column>
        <el-table-column label="毛利达成率" width="110" align="right">
          <template #default="{ row }">{{ formatPercent(row.profit_rate) }}</template>
        </el-table-column>
        <el-table-column label="毛利得分" width="90" align="right">
          <template #default="{ row }">{{ scoreText(row.profit_score) }}</template>
        </el-table-column>
        <el-table-column label="重点产品目标" width="120" align="right">
          <template #default="{ row }">{{ formatCell(row.key_product_target) }}</template>
        </el-table-column>
        <el-table-column label="重点产品达成" width="120" align="right">
          <template #default="{ row }">{{ formatCell(row.key_product_achieved) }}</template>
        </el-table-column>
        <el-table-column label="重点产品达成率" width="130" align="right">
          <template #default="{ row }">{{ formatPercent(row.key_product_rate) }}</template>
        </el-table-column>
        <el-table-column label="重点产品得分" width="110" align="right">
          <template #default="{ row }">{{ scoreText(row.key_product_score) }}</template>
        </el-table-column>
        <el-table-column prop="operation_score" label="运营得分" width="100" align="right" sortable>
          <template #default="{ row }">{{ scoreText(row.operation_score) }}</template>
        </el-table-column>
        <el-table-column prop="total_score" label="总分" width="90" align="right" sortable>
          <template #default="{ row }">
            <el-tag v-if="row.total_score != null" :type="scoreTagType(row.total_score)" size="small">
              {{ Number(row.total_score).toFixed(1) }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="rank" label="排名" width="80" align="center" sortable>
          <template #default="{ row }">{{ row.rank != null ? `第${row.rank}名` : '—' }}</template>
        </el-table-column>
        <el-table-column prop="performance_coefficient" label="绩效系数" width="100" align="right" sortable>
          <template #default="{ row }">{{ coefficientText(row.performance_coefficient) }}</template>
        </el-table-column>
        <el-table-column label="赛马池" width="100" align="center">
          <template #default="{ row }">{{ rankingPoolText(row) }}</template>
        </el-table-column>
        <el-table-column label="预警" width="120" align="center">
          <template #default="{ row }">{{ performanceAlertText(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handleViewDetail(row)" v-if="row.platform_code && row.shop_id">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="filteredPerformanceData.length === 0 && !performanceList.loading" class="empty-state">
        <template v-if="loadError">查询失败，请稍后重试或联系管理员。</template>
        <template v-else>暂无符合筛选条件的绩效数据。</template>
      </div>
      <el-pagination
        v-model:current-page="performanceList.page"
        v-model:page-size="performanceList.pageSize"
        :total="performanceList.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        class="pager"
        @size-change="loadPerformanceList"
        @current-change="loadPerformanceList"
      />
    </el-card>

    <el-dialog v-model="detailVisible" title="绩效详情" width="900px">
      <div v-if="performanceDetail.data" v-loading="performanceDetail.loading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="店铺名称" :span="2">{{ performanceDetail.data.shop_name }}</el-descriptions-item>
          <el-descriptions-item label="考核周期">{{ performanceDetail.data.period }}</el-descriptions-item>
          <el-descriptions-item label="总分">
            <el-tag :type="performanceDetail.data.total_score != null ? scoreTagType(performanceDetail.data.total_score) : 'info'" size="large">
              {{ performanceDetail.data.total_score != null ? performanceDetail.data.total_score.toFixed(1) : '未完成' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="排名">
            <el-tag size="small">{{ performanceDetail.data.rank != null ? `第${performanceDetail.data.rank}名` : '未参与正式赛马' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="绩效系数">
            <el-tag size="small">{{ coefficientText(performanceDetail.data.performance_coefficient) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="赛马池">{{ rankingPoolText(performanceDetail.data) }}</el-descriptions-item>
          <el-descriptions-item label="预警">{{ performanceAlertText(performanceDetail.data) }}</el-descriptions-item>
        </el-descriptions>

        <el-card style="margin-top: 20px;">
          <template #header><span>得分详情</span></template>
          <el-card
            v-for="card in detailMetricCards"
            :key="card.key"
            shadow="never"
            style="margin-bottom: 15px;"
          >
            <div class="metric-header">
              <span class="metric-title">{{ card.label }}（权重 {{ card.weight }}%）</span>
              <el-tag :type="metricTagType(card.metric, card.successThreshold, card.warningThreshold)" size="small">
                {{ metricScoreText(card.metric) }}
              </el-tag>
            </div>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="状态">{{ isMetricCalculated(card.metric) ? '已计算' : '未就绪' }}</el-descriptions-item>
              <el-descriptions-item label="数据来源">{{ card.metric?.source || '—' }}</el-descriptions-item>
              <el-descriptions-item label="目标">{{ metricValueText(card.metric, 'target', card.targetType) }}</el-descriptions-item>
              <el-descriptions-item label="达成">{{ metricValueText(card.metric, 'achieved', card.achievedType) }}</el-descriptions-item>
              <el-descriptions-item label="达成率">{{ metricValueText(card.metric, 'rate', 'percent') }}</el-descriptions-item>
              <el-descriptions-item label="说明">{{ metricMessageText(card.metric) }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-card>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import api from '@/api'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatPercent } from '@/utils/dataFormatter'

const userStore = useUserStore()

const performanceList = reactive({
  data: [],
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false
})
const loadError = ref(false)
const calculating = ref(false)
const detailVisible = ref(false)
const poolFilter = ref('all')
const alertFilter = ref('all')

const weightConfig = reactive({
  sales_weight: 30,
  profit_weight: 25,
  key_product_weight: 25,
  operation_weight: 20
})

const filters = reactive({
  period: new Date().toISOString().slice(0, 7),
  platform: '',
  shopId: null,
  groupBy: 'shop'
})

const performanceDetail = reactive({
  data: null,
  loading: false
})

const formulaText = computed(() => {
  return `销售额(${weightConfig.sales_weight}%) + 毛利(${weightConfig.profit_weight}%) + 重点产品(${weightConfig.key_product_weight}%) + 运营得分(${weightConfig.operation_weight}%)`
})

const filteredPerformanceData = computed(() => {
  return (performanceList.data || []).filter((row) => {
    const pool = row?.score_details?.summary?.ranking_pool_status || 'unknown'
    const alertTypes = row?.score_details?.summary?.performance_alert_types || []
    const alert = alertTypes.includes('performance_elimination_review')
      ? 'elimination'
      : alertTypes.includes('performance_red_card')
        ? 'red'
        : alertTypes.includes('performance_yellow_card')
          ? 'yellow'
          : 'none'
    const poolOk = poolFilter.value === 'all' || pool === poolFilter.value
    const alertOk = alertFilter.value === 'all' || alert === alertFilter.value
    return poolOk && alertOk
  })
})

const detailMetricCards = computed(() => {
  const data = performanceDetail.data || {}
  return [
    {
      key: 'sales_score',
      label: '销售额得分',
      weight: weightConfig.sales_weight,
      metric: data.sales_score,
      successThreshold: 27,
      warningThreshold: 24,
      targetType: 'currency',
      achievedType: 'currency'
    },
    {
      key: 'profit_score',
      label: '毛利得分',
      weight: weightConfig.profit_weight,
      metric: data.profit_score,
      successThreshold: 22.5,
      warningThreshold: 20,
      targetType: 'currency',
      achievedType: 'currency'
    },
    {
      key: 'key_product_score',
      label: '重点产品得分',
      weight: weightConfig.key_product_weight,
      metric: data.key_product_score,
      successThreshold: 22.5,
      warningThreshold: 20,
      targetType: 'text',
      achievedType: 'text'
    },
    {
      key: 'operation_score',
      label: '运营得分',
      weight: weightConfig.operation_weight,
      metric: data.operation_score,
      successThreshold: 18,
      warningThreshold: 16,
      targetType: 'text',
      achievedType: 'text'
    }
  ]
})

const hasPermission = (permission) => userStore.hasPermission(permission)

function formatCell(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v)
}

function scoreText(value) {
  return value != null ? Number(value).toFixed(1) : '—'
}

function coefficientText(value) {
  return value != null ? Number(value).toFixed(2) : '—'
}

function scoreTagType(score) {
  if (score >= 90) return 'success'
  if (score >= 80) return 'warning'
  return 'danger'
}

function isMetricCalculated(metric) {
  return metric?.status === 'calculated'
}

function metricTagType(metric, successThreshold, warningThreshold) {
  if (!isMetricCalculated(metric)) return 'info'
  const score = Number(metric?.score || 0)
  if (score >= successThreshold) return 'success'
  if (score >= warningThreshold) return 'warning'
  return 'danger'
}

function metricScoreText(metric) {
  if (!isMetricCalculated(metric) || metric?.score == null) return '未就绪'
  return `${Number(metric.score).toFixed(1)}分`
}

function metricValueText(metric, field, valueType = 'text') {
  const value = metric?.[field]
  if (value == null || value === '') return '—'
  if (valueType === 'currency') return formatCurrency(value)
  if (valueType === 'percent') return formatPercent(value)
  if (typeof value === 'number') return Number(value).toFixed(1)
  return String(value)
}

function metricMessageText(metric) {
  return metric?.calculation || metric?.message || '—'
}

function rankingPoolText(row) {
  const status = row?.score_details?.summary?.ranking_pool_status
  if (status === 'official') return '正式池'
  if (status === 'observation') return '观察池'
  return '—'
}

function performanceAlertText(row) {
  const level = row?.score_details?.summary?.performance_alert_level
  const types = row?.score_details?.summary?.performance_alert_types || []
  if (types.includes('performance_elimination_review')) return '淘汰评估'
  if (level === 'critical') return '红牌'
  if (level === 'warning') return '黄牌'
  return '—'
}

const loadPerformanceList = async () => {
  performanceList.loading = true
  loadError.value = false
  try {
    const period = typeof filters.period === 'string'
      ? filters.period
      : (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : undefined)

    const response = await api.getPerformanceScores({
      period,
      platform: filters.platform || undefined,
      shop_id: filters.shopId || undefined,
      group_by: filters.groupBy,
      page: performanceList.page,
      page_size: performanceList.pageSize
    })

    if (response && Array.isArray(response)) {
      performanceList.data = response
      performanceList.total = response.length
    } else {
      performanceList.data = response?.data || response || []
      performanceList.total = response?.total || 0
    }
  } catch (error) {
    loadError.value = true
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    performanceList.loading = false
  }
}

const loadWeightConfig = async () => {
  try {
    const response = await api.getPerformanceConfigs({ is_active: true, page: 1, page_size: 1 })
    const row = Array.isArray(response)
      ? response[0]
      : (response?.data?.[0] || response?.data || response)
    if (!row) return
    weightConfig.sales_weight = row.sales_weight ?? weightConfig.sales_weight
    weightConfig.profit_weight = row.profit_weight ?? weightConfig.profit_weight
    weightConfig.key_product_weight = row.key_product_weight ?? weightConfig.key_product_weight
    weightConfig.operation_weight = row.operation_weight ?? weightConfig.operation_weight
  } catch (_error) {
    // ignore
  }
}

const handleRecalculate = async () => {
  const period = typeof filters.period === 'string'
    ? filters.period
    : (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : '')
  if (!period) {
    ElMessage.warning('请选择考核月份')
    return
  }
  calculating.value = true
  try {
    const result = await api.calculatePerformanceScores(period)
    ElMessage.success('已完成当月店铺绩效、个人绩效和提成重算，请刷新查看最新结果')
    const lockedConflicts = result?.payroll_locked_conflicts || 0
    const conflictDetails = result?.payroll_locked_conflict_details || []
    if (lockedConflicts > 0) {
      const summary = conflictDetails.length
        ? conflictDetails.map((item) => {
            const fields = Array.isArray(item.changed_fields) ? item.changed_fields.join(', ') : ''
            return `${item.employee_code} (${item.payroll_status}) -> ${fields}`
          }).join('\n')
        : `共有 ${lockedConflicts} 份已锁定工资单未被覆盖`
      await ElMessageBox.alert(summary, '工资单锁定冲突', {
        type: 'warning',
        confirmButtonText: '知道了'
      })
    }
    await loadPerformanceList()
  } catch (error) {
    const code = error?.response?.data?.data?.error_code
    if (code === 'PERF_CALC_NOT_READY') {
      ElMessage.warning('绩效计算能力未就绪，请联系管理员检查 PostgreSQL 数据链路与目标分解配置')
    } else if (code === 'PERF_CONFIG_NOT_FOUND') {
      ElMessage.warning('当前考核周期无可用绩效配置，请联系管理员完成配置后重试')
    } else {
      handleApiError(error, { showMessage: true, logError: true })
    }
  } finally {
    calculating.value = false
  }
}

const handleViewDetail = async (row) => {
  detailVisible.value = true
  performanceDetail.loading = true
  performanceDetail.data = null
  try {
    const period = typeof filters.period === 'string'
      ? filters.period
      : (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : undefined)
    const response = await api.getShopPerformanceDetail(row.platform_code, row.shop_id, period)
    performanceDetail.data = response?.data ?? response ?? {}
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    performanceDetail.loading = false
  }
}

onMounted(() => {
  loadWeightConfig()
  loadPerformanceList()
})
</script>

<style scoped>
.performance-display {
  padding: 20px;
}

.action-bar {
  display: flex;
  align-items: center;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-hint {
  font-size: 12px;
  color: #909399;
}

.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.metric-title {
  font-weight: bold;
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: #909399;
}

.pager {
  margin-top: 20px;
  justify-content: flex-end;
}

.erp-table :deep(.el-table__fixed-left) {
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table__fixed-right) {
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table .cell) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
