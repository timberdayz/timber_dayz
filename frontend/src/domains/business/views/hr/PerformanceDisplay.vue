<template>
  <div class="performance-display erp-page-container">
    <PageHeader
      :title="pageTitle"
      :subtitle="pageSubtitle"
      family="dashboard"
    />

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
      <el-radio-group v-if="showGroupToggle" v-model="filters.groupBy" size="default" @change="loadPerformanceList">
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
      <el-button
        v-if="taskContext.taskId"
        type="success"
        @click="submitPerformanceTaskResult('confirmed', 'performance confirmed from public display')"
      >
        确认无误
      </el-button>
      <el-button
        v-if="taskContext.taskId"
        type="danger"
        plain
        @click="submitPerformanceTaskResult('disputed', 'performance disputed from public display')"
      >
        提交异议
      </el-button>
      <el-select v-if="filters.groupBy === 'shop'" v-model="poolFilter" size="default" style="width: 120px;">
        <el-option label="全部池" value="all" />
        <el-option label="正式池" value="official" />
        <el-option label="观察池" value="observation" />
      </el-select>
      <el-select v-if="filters.groupBy === 'shop'" v-model="alertFilter" size="default" style="width: 140px;">
        <el-option label="全部预警" value="all" />
        <el-option label="无预警" value="none" />
        <el-option label="黄牌" value="yellow" />
        <el-option label="红牌" value="red" />
        <el-option label="淘汰评估" value="elimination" />
      </el-select>
      <el-select
        v-if="filters.groupBy === 'shop'"
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

    <el-card shadow="never" class="policy-card">
      <template #header>
        <div class="card-header">
          <span>口径说明</span>
        </div>
      </template>
      <div class="policy-grid">
        <div class="policy-item">
          <div class="policy-label">赛马池</div>
          <div class="policy-text">正式池参与公司总榜赛马并生成系数；观察池仅展示绩效，不参与正式奖惩。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">预警规则</div>
          <div class="policy-text">绩效分低于 70 为黄牌，低于 60 为红牌；连续红牌达到条件时升级为淘汰评估。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">{{ filters.groupBy === 'person' ? '人员维度' : '店铺维度' }}</div>
          <div class="policy-text">{{ currentGroupPolicyText }}</div>
        </div>
      </div>
    </el-card>

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
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额目标" width="110" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_target) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额达成" width="110" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额达成率" width="120" align="right">
          <template #default="{ row }">{{ formatPercent(row.sales_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额得分" width="100" align="right">
          <template #default="{ row }">{{ scoreText(row.sales_score) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利目标" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.profit_target) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利达成" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.profit_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利达成率" width="110" align="right">
          <template #default="{ row }">{{ formatPercent(row.profit_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利得分" width="90" align="right">
          <template #default="{ row }">{{ scoreText(row.profit_score) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="重点产品目标" width="120" align="right">
          <template #default="{ row }">{{ formatCell(row.key_product_target) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="重点产品达成" width="120" align="right">
          <template #default="{ row }">{{ formatCell(row.key_product_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="重点产品达成率" width="130" align="right">
          <template #default="{ row }">{{ formatPercent(row.key_product_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="重点产品得分" width="110" align="right">
          <template #default="{ row }">{{ scoreText(row.key_product_score) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" prop="operation_score" label="店铺运营得分" width="120" align="right" sortable>
          <template #default="{ row }">{{ scoreText(row.operation_score) }}</template>
        </el-table-column>

        <el-table-column v-if="filters.groupBy === 'person'" label="实际销售额" width="120" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'person'" label="店铺汇总达成率" width="140" align="right">
          <template #default="{ row }">{{ formatPercent(row.sales_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'person'" label="绩效来源" width="140" align="center">
          <template #default="{ row }">
            <el-tag :type="row.performance_source_type === 'personal_inputs' ? 'success' : 'warning'" size="small">
              {{ row.performance_source_type === 'personal_inputs' ? '个人输入项' : '店铺回退' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'person'" label="输入项构成" min-width="220">
          <template #default="{ row }">
            <div v-if="row.personal_input_items?.length" class="input-summary">
              <div class="input-summary-head">
                <span>{{ row.personal_input_items.length }}项</span>
                <span>合计 {{ formatScore(row.personal_input_score_total) }}</span>
              </div>
              <div class="input-summary-list">
                {{ summarizeInputItems(row.personal_input_items) }}
              </div>
            </div>
            <span v-else class="fallback-text">未配置个人输入项，回退至店铺绩效</span>
          </template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'person'" label="个人运营加减分(人工)" width="160" align="right">
          <template #default="{ row }">
            <el-tag v-if="row.personal_adjustment_total != null" :type="Number(row.personal_adjustment_total || 0) >= 0 ? 'success' : 'danger'" size="small">
              {{ Number(row.personal_adjustment_total || 0) > 0 ? '+' : '' }}{{ Number(row.personal_adjustment_total || 0).toFixed(1) }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'person'" label="个人输入项得分" width="130" align="right">
          <template #default="{ row }">
            <el-tag v-if="row.personal_input_score_total != null" type="warning" size="small">
              {{ formatScore(row.personal_input_score_total) }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>

        <el-table-column prop="total_score" :label="filters.groupBy === 'person' ? '个人绩效总分' : '总分'" width="120" align="right" sortable>
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
        <el-table-column v-if="filters.groupBy === 'shop'" prop="performance_coefficient" label="绩效系数" width="100" align="right" sortable>
          <template #default="{ row }">{{ coefficientText(row.performance_coefficient) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="赛马池" width="100" align="center">
          <template #default="{ row }">{{ rankingPoolText(row) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="预警" width="120" align="center">
          <template #default="{ row }">{{ performanceAlertText(row) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="操作" width="90" fixed="right">
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
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { useUserStore } from '@/stores/user'
import { useRoute } from 'vue-router'
import api from '@/api'
import employeeTasksApi from '@/api/employeeTasks.js'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatPercent } from '@/utils/dataFormatter'
import { hasScopedActionPermission } from '@/utils/actionPermissions'

const props = defineProps({
  forcedGroupBy: {
    type: String,
    default: ''
  }
})
const userStore = useUserStore()
const route = useRoute()
const showGroupToggle = computed(() => !props.forcedGroupBy)
const pageTitle = computed(() => {
  if (route.path.includes('/hr-performance-display/person')) return '个人绩效公示'
  if (route.path.includes('/hr-performance-display/shop')) return '店铺绩效公示'
  return '绩效公示'
})
const pageSubtitle = computed(() => {
  if (props.forcedGroupBy === 'person') {
    return '面向全员展示个人维度的绩效结果，并支持查看个人绩效来源。'
  }
  if (props.forcedGroupBy === 'shop') {
    return '面向全员展示店铺维度的绩效结果，并支持查看赛马池状态、预警和绩效口径。'
  }
  if (route.path.includes('/hr-performance-display/person')) {
    return '面向全员展示个人维度的绩效结果，并支持查看个人绩效来源。'
  }
  if (route.path.includes('/hr-performance-display/shop')) {
    return '面向全员展示店铺维度的绩效结果，并支持查看赛马池与预警状态。'
  }
  return '面向全员展示店铺或人员维度的绩效结果，并支持查看赛马池与预警状态。'
})

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

const resolveGroupBy = () => props.forcedGroupBy || (route.path.includes('/hr-performance-display/person') ? 'person' : 'shop')

const filters = reactive({
  period: new Date().toISOString().slice(0, 7),
  platform: '',
  shopId: null,
  groupBy: resolveGroupBy()
})

const taskContext = reactive({
  taskId: '',
  yearMonth: '',
  employeeCode: ''
})

const performanceDetail = reactive({
  data: null,
  loading: false
})

const formulaText = computed(() => {
  if (filters.groupBy === 'person') {
    return '优先取个人绩效输入项得分，再叠加个人调整项与考勤扣分；无输入项时才回退到店铺汇总绩效'
  }
  return `销售额(${weightConfig.sales_weight}%) + 毛利(${weightConfig.profit_weight}%) + 店铺运营得分(${weightConfig.operation_weight}%)`
})

const currentGroupPolicyText = computed(() => {
  if (filters.groupBy === 'person') {
    return '人员绩效优先由个人绩效输入项驱动；人工调整和考勤扣分继续叠加。只有未配置个人输入项时，系统才回退到挂店店铺绩效聚合。'
  }
  return '店铺总分由销售、毛利和运营三项组成；重点产品当前不纳入正式口径。正式池店铺按公司总榜排名并叠加分数底线生成赛马系数。'
})

const filteredPerformanceData = computed(() => {
  if (filters.groupBy !== 'shop') {
    return performanceList.data || []
  }
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
      key: 'operation_score',
      label: '店铺运营得分',
      weight: weightConfig.operation_weight,
      metric: data.operation_score,
      successThreshold: 18,
      warningThreshold: 16,
      targetType: 'text',
      achievedType: 'text'
    }
  ]
})

const hasPermission = (permission) =>
  hasScopedActionPermission({
    roles: userStore.roles || [],
    activeRole: localStorage.getItem('activeRole') || '',
    permission,
  })

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

function formatScore(value) {
  return value != null ? Number(value).toFixed(1) : '—'
}

function summarizeInputItems(items) {
  return (items || [])
    .slice(0, 3)
    .map((item) => `${item.metric_name || item.metric_code} ${formatScore(item.score)}`)
    .join(' / ')
}

function scoreTagType(score) {
  if (score >= 90) return 'success'
  if (score >= 80) return 'warning'
  return 'danger'
}

const initTaskContext = () => {
  taskContext.taskId = typeof route.query.task_id === 'string' ? route.query.task_id : ''
  taskContext.yearMonth = typeof route.query.year_month === 'string' ? route.query.year_month : ''
  taskContext.employeeCode = typeof route.query.employee_code === 'string' ? route.query.employee_code : ''
  if (taskContext.yearMonth) {
    filters.period = taskContext.yearMonth
  }
}

const submitPerformanceTaskResult = async (result, comment) => {
  if (!taskContext.taskId) return
  await employeeTasksApi.submitTask(taskContext.taskId, {
    completion_payload: {
      employee_code: taskContext.employeeCode,
      year_month: filters.period,
      confirmation_result: result
    },
    result_comment: comment,
    requires_confirmation: result !== 'confirmed'
  })
  ElMessage.success('绩效确认任务已提交')
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

watch(() => route.path, () => {
  filters.groupBy = resolveGroupBy()
  loadPerformanceList()
})

onMounted(() => {
  initTaskContext()
  loadWeightConfig()
  loadPerformanceList()
})
</script>

<style scoped>
.performance-display {
  padding: 20px;
  --perf-text-primary: #1d1d1f;
  --perf-text-secondary: #6e6e73;
  --perf-text-muted: #8a8a8f;
  --perf-surface: #ffffff;
  --perf-surface-muted: #f5f5f7;
  --perf-border: #d2d2d7;
}

.action-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 20px;
  padding: 14px 16px;
  border: 1px solid var(--perf-border);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(245, 245, 247, 0.96) 100%);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.policy-card {
  margin-bottom: 20px;
  border-color: var(--perf-border);
  border-radius: 18px;
  background: var(--perf-surface);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.policy-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.policy-item {
  padding: 14px 16px;
  border: 1px solid var(--perf-border);
  border-radius: 14px;
  background: var(--perf-surface-muted);
}

.policy-label {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--perf-text-primary);
}

.policy-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--perf-text-secondary);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-hint {
  font-size: 12px;
  color: var(--perf-text-muted);
}

.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.metric-title {
  font-weight: bold;
  color: var(--perf-text-primary);
}

.input-summary-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--perf-text-secondary);
}

.input-summary-list {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--perf-text-primary);
}

.fallback-text {
  font-size: 12px;
  color: var(--perf-text-muted);
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--perf-text-muted);
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
