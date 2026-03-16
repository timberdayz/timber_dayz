<template>
  <div class="performance-display erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">绩效公示</h1>
    <p style="color: #909399; margin-bottom: 20px;">绩效公示面向全员，数据来源于人员店铺归属和绩效配置计算。可按店铺或人员维度查看。</p>
    
    <div class="action-bar" style="margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
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
        type="warning"
        :loading="calculating"
        @click="handleRecalculate"
        v-if="hasPermission('performance:config')"
      >
        重新计算
      </el-button>
      <el-select v-model="filters.platform" placeholder="选择平台" clearable size="default" style="width: 140px; margin-left: auto;" @change="loadPerformanceList">
        <el-option label="全部平台" value="" />
        <el-option label="Shopee" value="Shopee" />
        <el-option label="Lazada" value="Lazada" />
      </el-select>
    </div>
    
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>绩效公示</span>
          <div style="font-size: 12px; color: #909399;">
            绩效构成：{{ formulaText }}
          </div>
        </div>
      </template>
      
      <el-table :data="performanceList.data" stripe v-loading="performanceList.loading" class="erp-table" border>
        <el-table-column :prop="filters.groupBy === 'person' ? 'employee_name' : 'shop_name'" :label="filters.groupBy === 'person' ? '人员' : '店铺'" width="180" fixed="left" show-overflow-tooltip>
          <template #default="{ row }">{{ filters.groupBy === 'person' ? (row.employee_name || row.employee_code || '—') : (row.shop_name || row.shop_id || '—') }}</template>
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
          <template #default="{ row }">{{ row.sales_score != null ? Number(row.sales_score).toFixed(1) : '—' }}</template>
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
          <template #default="{ row }">{{ row.profit_score != null ? Number(row.profit_score).toFixed(1) : '—' }}</template>
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
          <template #default="{ row }">{{ row.key_product_score != null ? Number(row.key_product_score).toFixed(1) : '—' }}</template>
        </el-table-column>
        <el-table-column prop="operation_score" label="运营得分" width="100" align="right" sortable>
          <template #default="{ row }">{{ row.operation_score != null ? Number(row.operation_score).toFixed(1) : '—' }}</template>
        </el-table-column>
        <el-table-column prop="total_score" label="总分" width="90" align="right" sortable>
          <template #default="{ row }">
            <el-tag v-if="row.total_score != null" :type="row.total_score >= 90 ? 'success' : row.total_score >= 80 ? 'warning' : 'danger'" size="small">{{ Number(row.total_score).toFixed(1) }}</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="rank" label="排名" width="80" align="center" sortable>
          <template #default="{ row }">{{ row.rank != null ? `第${row.rank}名` : '—' }}</template>
        </el-table-column>
        <el-table-column prop="performance_coefficient" label="绩效系数" width="100" align="right" sortable>
          <template #default="{ row }">{{ row.performance_coefficient != null ? Number(row.performance_coefficient).toFixed(2) : '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handleViewDetail(row)" v-if="row.platform_code && row.shop_id">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <div v-if="performanceList.data.length === 0 && !performanceList.loading" style="padding: 40px; text-align: center; color: #909399;">
        <template v-if="loadError">查询失败，请稍后重试或联系管理员。</template>
        <template v-else>
          <div style="margin-bottom: 12px;">暂无绩效数据，请选择月份并确保已执行绩效计算</div>
          <el-button type="warning" :loading="calculating" @click="handleRecalculate" v-if="hasPermission('performance:config')">
            重新计算当月绩效
          </el-button>
        </template>
      </div>
      <el-pagination
        v-model:current-page="performanceList.page"
        v-model:page-size="performanceList.pageSize"
        :total="performanceList.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px; justify-content: flex-end;"
        @size-change="loadPerformanceList"
        @current-change="loadPerformanceList"
      />
    </el-card>
    
    <el-dialog
      v-model="detailVisible"
      title="绩效详情"
      width="900px"
    >
      <div v-if="performanceDetail.data" v-loading="performanceDetail.loading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="店铺名称" :span="2">{{ performanceDetail.data.shop_name }}</el-descriptions-item>
          <el-descriptions-item label="考核周期">{{ performanceDetail.data.period }}</el-descriptions-item>
          <el-descriptions-item label="总分">
            <el-tag :type="performanceDetail.data.total_score >= 90 ? 'success' : performanceDetail.data.total_score >= 80 ? 'warning' : 'danger'" size="large">
              {{ performanceDetail.data.total_score.toFixed(1) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="排名">
            <el-tag :type="performanceDetail.data.rank === 1 ? 'success' : performanceDetail.data.rank === 2 ? 'warning' : performanceDetail.data.rank === 3 ? 'info' : ''" size="small">
              第{{ performanceDetail.data.rank }}名
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="绩效系数">
            <el-tag :type="performanceDetail.data.performance_coefficient >= 1.2 ? 'success' : performanceDetail.data.performance_coefficient >= 1.0 ? 'warning' : 'danger'" size="small">
              {{ performanceDetail.data.performance_coefficient.toFixed(2) }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
        
        <el-card style="margin-top: 20px;" v-if="performanceDetail.data.sales_score">
          <template #header><span>得分详情</span></template>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="销售额得分">{{ performanceDetail.data.sales_score?.score != null ? performanceDetail.data.sales_score.score.toFixed(1) : '—' }}分</el-descriptions-item>
            <el-descriptions-item label="毛利得分">{{ performanceDetail.data.profit_score?.score != null ? performanceDetail.data.profit_score.score.toFixed(1) : '—' }}分</el-descriptions-item>
            <el-descriptions-item label="重点产品得分">{{ performanceDetail.data.key_product_score?.score != null ? performanceDetail.data.key_product_score.score.toFixed(1) : '—' }}分</el-descriptions-item>
            <el-descriptions-item label="运营得分">{{ performanceDetail.data.operation_score?.score != null ? performanceDetail.data.operation_score.score.toFixed(1) : '—' }}分</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
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
const weightConfig = reactive({
  sales_weight: 30,
  profit_weight: 25,
  key_product_weight: 25,
  operation_weight: 20
})
const formulaText = computed(() => {
  return `销售额(${weightConfig.sales_weight}%) + 毛利(${weightConfig.profit_weight}%) + 重点产品(${weightConfig.key_product_weight}%) + 运营得分(${weightConfig.operation_weight}%)`
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

const detailVisible = ref(false)

function formatCell(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return String(v)
}

const hasPermission = (permission) => {
  return userStore.hasPermission(permission)
}

const loadPerformanceList = async () => {
  performanceList.loading = true
  loadError.value = false
  try {
    const period = typeof filters.period === 'string' ? filters.period : 
      (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : undefined)
    
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
  } catch (error) {
    // 配置读取失败不阻塞列表
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
    await api.calculatePerformanceScores(period)
    ElMessage.success('已触发绩效计算，请稍后刷新查看结果')
    await loadPerformanceList()
  } catch (error) {
    const code = error?.response?.data?.data?.error_code
    if (code === 'PERF_CALC_NOT_READY') {
      ElMessage.warning('绩效计算能力未就绪，请联系管理员完成 Metabase 计算方案部署')
    } else if (code === 'PERF_CONFIG_NOT_FOUND') {
      ElMessage.warning('当前考核周期无可用绩效配置，请联系管理员配置后重试')
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
    const period = typeof filters.period === 'string' ? filters.period : 
      (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : undefined)
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
