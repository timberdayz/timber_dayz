<template>
  <div class="performance-management erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">绩效管理</h1>
    
    <!-- 操作栏 -->
    <div class="action-bar" style="margin-bottom: 20px;">
      <el-button :icon="Refresh" @click="loadPerformanceList">刷新</el-button>
      <el-button type="primary" :icon="Setting" @click="handleConfig" v-if="hasPermission('performance:config')">
        配置权重
      </el-button>
      <el-button :icon="Download" @click="handleExport" v-if="hasPermission('performance:export')">导出报表</el-button>
      <div style="flex: 1;"></div>
      <el-date-picker
        v-model="filters.period"
        type="month"
        format="YYYY-MM"
        placeholder="选择月份"
        size="small"
        style="width: 150px;"
        @change="loadPerformanceList"
      />
      <el-select v-model="filters.platform" placeholder="选择平台" clearable size="small" style="width: 150px; margin-left: 10px;" @change="loadPerformanceList">
        <el-option label="全部平台" value="" />
        <el-option label="Shopee" value="Shopee" />
        <el-option label="Lazada" value="Lazada" />
      </el-select>
    </div>
    
    <!-- 绩效公示表格 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>绩效公示</span>
          <div style="font-size: 12px; color: #909399;">
            绩效构成：销售额(30%) + 毛利(25%) + 重点产品(25%) + 运营得分(20%)
          </div>
        </div>
      </template>
      
      <el-table :data="performanceList.data" stripe v-loading="performanceList.loading" class="erp-table">
        <el-table-column prop="shop_name" label="店铺名称" width="200" fixed="left" show-overflow-tooltip />
        <el-table-column prop="sales_score" label="销售额得分(30%)" width="150" align="right" sortable>
          <template #default="{ row }">
            <el-tag :type="row.sales_score >= 27 ? 'success' : row.sales_score >= 24 ? 'warning' : 'danger'" size="small">
              {{ row.sales_score.toFixed(1) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="profit_score" label="毛利得分(25%)" width="150" align="right" sortable>
          <template #default="{ row }">
            <el-tag :type="row.profit_score >= 22.5 ? 'success' : row.profit_score >= 20 ? 'warning' : 'danger'" size="small">
              {{ row.profit_score.toFixed(1) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="key_product_score" label="重点产品得分(25%)" width="160" align="right" sortable>
          <template #default="{ row }">
            <el-tag :type="row.key_product_score >= 22.5 ? 'success' : row.key_product_score >= 20 ? 'warning' : 'danger'" size="small">
              {{ row.key_product_score.toFixed(1) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="operation_score" label="运营得分(20%)" width="150" align="right" sortable>
          <template #default="{ row }">
            <el-tag :type="row.operation_score >= 18 ? 'success' : row.operation_score >= 16 ? 'warning' : 'danger'" size="small">
              {{ row.operation_score.toFixed(1) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_score" label="总分" width="120" align="right" sortable>
          <template #default="{ row }">
            <el-tag :type="row.total_score >= 90 ? 'success' : row.total_score >= 80 ? 'warning' : 'danger'" size="large">
              {{ row.total_score.toFixed(1) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rank" label="排名" width="100" align="center" sortable>
          <template #default="{ row }">
            <el-tag :type="row.rank === 1 ? 'success' : row.rank === 2 ? 'warning' : row.rank === 3 ? 'info' : ''" size="small">
              第{{ row.rank }}名
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="performance_coefficient" label="绩效系数" width="120" align="right" sortable>
          <template #default="{ row }">
            <el-tag :type="row.performance_coefficient >= 1.2 ? 'success' : row.performance_coefficient >= 1.0 ? 'warning' : 'danger'" size="small">
              {{ row.performance_coefficient.toFixed(2) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handleViewDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      
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
    
    <!-- 绩效详情对话框 -->
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
        
        <!-- 得分详情 -->
        <el-card style="margin-top: 20px;">
          <template #header>
            <span>得分详情</span>
          </template>
          
          <!-- 销售额得分 -->
          <el-card shadow="never" style="margin-bottom: 15px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <span style="font-weight: bold;">销售额得分（权重30%）</span>
              <el-tag :type="performanceDetail.data.sales_score.score >= 27 ? 'success' : performanceDetail.data.sales_score.score >= 24 ? 'warning' : 'danger'" size="small">
                {{ performanceDetail.data.sales_score.score.toFixed(1) }}分
              </el-tag>
            </div>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="目标">{{ formatCurrency(performanceDetail.data.sales_score.target) }}</el-descriptions-item>
              <el-descriptions-item label="达成">{{ formatCurrency(performanceDetail.data.sales_score.achieved) }}</el-descriptions-item>
              <el-descriptions-item label="达成率">{{ performanceDetail.data.sales_score.rate.toFixed(1) }}%</el-descriptions-item>
              <el-descriptions-item label="计算方式">{{ performanceDetail.data.sales_score.calculation }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
          
          <!-- 毛利得分 -->
          <el-card shadow="never" style="margin-bottom: 15px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <span style="font-weight: bold;">毛利得分（权重25%）</span>
              <el-tag :type="performanceDetail.data.profit_score.score >= 22.5 ? 'success' : performanceDetail.data.profit_score.score >= 20 ? 'warning' : 'danger'" size="small">
                {{ performanceDetail.data.profit_score.score.toFixed(1) }}分
              </el-tag>
            </div>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="目标">{{ formatCurrency(performanceDetail.data.profit_score.target) }}</el-descriptions-item>
              <el-descriptions-item label="达成">{{ formatCurrency(performanceDetail.data.profit_score.achieved) }}</el-descriptions-item>
              <el-descriptions-item label="达成率">{{ performanceDetail.data.profit_score.rate.toFixed(1) }}%</el-descriptions-item>
              <el-descriptions-item label="计算方式">{{ performanceDetail.data.profit_score.calculation }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
          
          <!-- 重点产品得分 -->
          <el-card shadow="never" style="margin-bottom: 15px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <span style="font-weight: bold;">重点产品得分（权重25%）</span>
              <el-tag :type="performanceDetail.data.key_product_score.score >= 22.5 ? 'success' : performanceDetail.data.key_product_score.score >= 20 ? 'warning' : 'danger'" size="small">
                {{ performanceDetail.data.key_product_score.score.toFixed(1) }}分
              </el-tag>
            </div>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="目标">{{ performanceDetail.data.key_product_score.target }}</el-descriptions-item>
              <el-descriptions-item label="达成">{{ performanceDetail.data.key_product_score.achieved }}</el-descriptions-item>
              <el-descriptions-item label="达成率">{{ performanceDetail.data.key_product_score.rate.toFixed(1) }}%</el-descriptions-item>
              <el-descriptions-item label="计算方式">{{ performanceDetail.data.key_product_score.calculation }}</el-descriptions-item>
              <el-descriptions-item label="滞销清理">{{ performanceDetail.data.key_product_score.breakdown.backlog_clearance }}</el-descriptions-item>
              <el-descriptions-item label="服务得分">{{ performanceDetail.data.key_product_score.breakdown.service_score }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
          
          <!-- 运营得分 -->
          <el-card shadow="never">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <span style="font-weight: bold;">运营得分（权重20%）</span>
              <el-tag :type="performanceDetail.data.operation_score.score >= 18 ? 'success' : performanceDetail.data.operation_score.score >= 16 ? 'warning' : 'danger'" size="small">
                {{ performanceDetail.data.operation_score.score.toFixed(1) }}分
              </el-tag>
            </div>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="原始得分">{{ performanceDetail.data.operation_score.score_raw.toFixed(1) }}分</el-descriptions-item>
              <el-descriptions-item label="计算方式">{{ performanceDetail.data.operation_score.calculation }}</el-descriptions-item>
              <el-descriptions-item label="订单履约率">{{ performanceDetail.data.operation_score.breakdown.order_fulfillment_rate.toFixed(1) }}%</el-descriptions-item>
              <el-descriptions-item label="客户满意度">{{ performanceDetail.data.operation_score.breakdown.customer_satisfaction.toFixed(1) }}%</el-descriptions-item>
              <el-descriptions-item label="库存周转率">{{ performanceDetail.data.operation_score.breakdown.inventory_turnover.toFixed(1) }}%</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-card>
      </div>
    </el-dialog>
    
    <!-- 绩效配置对话框 -->
    <el-dialog
      v-model="configVisible"
      title="绩效权重配置"
      width="600px"
      @close="handleConfigClose"
    >
      <el-form
        ref="configFormRef"
        :model="configForm"
        :rules="configRules"
        label-width="150px"
      >
        <el-form-item label="销售额权重(%)" prop="sales_weight">
          <el-input-number v-model="configForm.sales_weight" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="毛利权重(%)" prop="profit_weight">
          <el-input-number v-model="configForm.profit_weight" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="重点产品权重(%)" prop="key_product_weight">
          <el-input-number v-model="configForm.key_product_weight" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="运营权重(%)" prop="operation_weight">
          <el-input-number v-model="configForm.operation_weight" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="总权重">
          <el-tag :type="totalWeight === 100 ? 'success' : 'danger'" size="large">
            {{ totalWeight }}%
          </el-tag>
          <span style="margin-left: 10px; color: #909399; font-size: 12px;">
            {{ totalWeight === 100 ? '权重配置正确' : '各项权重总和必须等于100%' }}
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button type="primary" @click="handleConfigSubmit" :loading="configSubmitting" :disabled="totalWeight !== 100">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Setting, Download } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import api from '@/api'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatNumber, formatPercent, formatInteger } from '@/utils/dataFormatter'

const userStore = useUserStore()

// 权限检查
const hasPermission = (permission) => {
  const user = userStore.userInfo
  if (!user) return false
  if (user.role === 'admin') return true
  if (user.role === 'manager') {
    return ['performance:read', 'performance:export'].includes(permission)
  }
  return permission === 'performance:read'
}

// 绩效列表数据
const performanceList = reactive({
  data: [],
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false
})

const filters = reactive({
  period: new Date(),
  platform: '',
  shopId: null
})

// 绩效详情
const performanceDetail = reactive({
  data: null,
  loading: false
})

const detailVisible = ref(false)
const configVisible = ref(false)
const configSubmitting = ref(false)
const configFormRef = ref(null)

// 配置表单
const configForm = reactive({
  sales_weight: 30,
  profit_weight: 25,
  key_product_weight: 25,
  operation_weight: 20
})

// 总权重计算
const totalWeight = computed(() => {
  return configForm.sales_weight + configForm.profit_weight + 
         configForm.key_product_weight + configForm.operation_weight
})

// 表单验证规则
const configRules = {
  sales_weight: [
    { required: true, message: '销售额权重不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '权重范围0-100', trigger: 'blur' }
  ],
  profit_weight: [
    { required: true, message: '毛利权重不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '权重范围0-100', trigger: 'blur' }
  ],
  key_product_weight: [
    { required: true, message: '重点产品权重不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '权重范围0-100', trigger: 'blur' }
  ],
  operation_weight: [
    { required: true, message: '运营权重不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '权重范围0-100', trigger: 'blur' }
  ]
}

// 加载绩效列表
const loadPerformanceList = async () => {
  performanceList.loading = true
  try {
    const period = filters.period ? 
      `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : 
      undefined
    
    const response = await api.getPerformanceScores({
      period: period,
      platform: filters.platform || undefined,
      shop_id: filters.shopId || undefined,
      page: performanceList.page,
      page_size: performanceList.pageSize
    })
    
    // 处理分页响应
    if (response && Array.isArray(response)) {
      performanceList.data = response
      performanceList.total = response.length
    } else {
      performanceList.data = response?.data || response || []
      performanceList.total = response?.total || 0
    }
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    performanceList.loading = false
  }
}

// 查看详情
const handleViewDetail = async (row) => {
  detailVisible.value = true
  performanceDetail.loading = true
  try {
    const response = await api.getShopPerformanceDetail(row.platform_code, row.shop_id, filters.period)
    performanceDetail.data = response || {}
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    performanceDetail.loading = false
  }
}

// 配置权重
const handleConfig = async () => {
  const response = await api.getPerformanceConfigs({})
  // 处理配置列表响应（取第一个配置或使用默认值）
  if (response && Array.isArray(response) && response.length > 0) {
    const config = response[0]
    configForm.sales_weight = config.sales_weight || 30
    configForm.profit_weight = config.profit_weight || 25
    configForm.key_product_weight = config.key_product_weight || 25
    configForm.operation_weight = config.operation_weight || 20
  } else if (response && response.pagination && response.data && response.data.length > 0) {
    const config = response.data[0]
    configForm.sales_weight = config.sales_weight || 30
    configForm.profit_weight = config.profit_weight || 25
    configForm.key_product_weight = config.key_product_weight || 25
    configForm.operation_weight = config.operation_weight || 20
  }
  configVisible.value = true
}

// 提交配置
const handleConfigSubmit = async () => {
  if (totalWeight.value !== 100) {
    ElMessage.warning('各项权重总和必须等于100%')
    return
  }
  
  configSubmitting.value = true
  try {
    // 注意：这里需要先获取配置ID，然后更新
    // 暂时使用创建新配置的方式（实际应该先查询现有配置）
    await api.createPerformanceConfig({
      sales_weight: configForm.sales_weight,
      profit_weight: configForm.profit_weight,
      key_product_weight: configForm.key_product_weight,
      operation_weight: configForm.operation_weight
    })
    
    ElMessage.success('配置更新成功')
    configVisible.value = false
    loadPerformanceList()
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    configSubmitting.value = false
  }
}

// 关闭配置对话框
const handleConfigClose = () => {
  configFormRef.value?.resetFields()
}

// 导出报表
const handleExport = () => {
  ElMessage.info('导出功能开发中（Mock阶段）')
  // TODO: 实现Excel导出功能
}

// formatCurrency 已从 @/utils/dataFormatter 导入，无需重复声明

onMounted(() => {
  loadPerformanceList()
})
</script>

<style scoped>
.performance-management {
  padding: 20px;
}

.action-bar {
  display: flex;
  align-items: center;
}

/* 企业级表格样式 */
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

