<template>
  <div class="management">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>⚙️ 数据管理中心</h1>
      <p>数据治理 • 质量控制 • 智能分析</p>
    </div>

    <!-- 数据概览 -->
    <el-row :gutter="20" class="overview-cards">
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="card-content">
            <div class="card-icon">
              <el-icon><Database /></el-icon>
            </div>
            <div class="card-info">
              <div class="card-value">{{ managementStore.dataStats.totalRecords }}</div>
              <div class="card-label">总记录数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="card-content">
            <div class="card-icon">
              <el-icon><Check /></el-icon>
            </div>
            <div class="card-info">
              <div class="card-value">{{ managementStore.dataStats.validRecords }}</div>
              <div class="card-label">有效记录</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="card-content">
            <div class="card-icon">
              <el-icon><Warning /></el-icon>
            </div>
            <div class="card-info">
              <div class="card-value">{{ managementStore.dataStats.invalidRecords }}</div>
              <div class="card-label">异常记录</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="card-content">
            <div class="card-icon">
              <el-icon><TrendCharts /></el-icon>
            </div>
            <div class="card-info">
              <div class="card-value">{{ managementStore.dataStats.dataQuality }}%</div>
              <div class="card-label">数据质量</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据管理操作 -->
    <el-row :gutter="20" class="management-actions">
      <el-col :span="12">
        <el-card class="action-card">
          <template #header>
            <span>数据质量检查</span>
          </template>
          <div class="action-content">
            <el-button 
              type="primary" 
              size="large"
              :loading="managementStore.loading"
              @click="runQualityCheck"
            >
              <el-icon><Search /></el-icon>
              执行质量检查
            </el-button>
            <div class="action-description">
              检查数据完整性、一致性和准确性
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="action-card">
          <template #header>
            <span>数据清理</span>
          </template>
          <div class="action-content">
            <el-button 
              type="warning" 
              size="large"
              :loading="managementStore.loading"
              @click="runDataCleaning"
            >
              <el-icon><Delete /></el-icon>
              执行数据清理
            </el-button>
            <div class="action-description">
              清理重复数据、修复异常值
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据质量报告 -->
    <el-card class="quality-report">
      <template #header>
        <div class="card-header">
          <span>数据质量报告</span>
          <el-button type="primary" size="small" @click="generateQualityReport">
            <el-icon><Document /></el-icon>
            生成报告
          </el-button>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="8">
          <div class="quality-metric">
            <div class="metric-title">完整性</div>
            <el-progress 
              :percentage="managementStore.qualityMetrics.completeness" 
              :color="getQualityColor(managementStore.qualityMetrics.completeness)"
            />
          </div>
        </el-col>
        <el-col :span="8">
          <div class="quality-metric">
            <div class="metric-title">准确性</div>
            <el-progress 
              :percentage="managementStore.qualityMetrics.accuracy" 
              :color="getQualityColor(managementStore.qualityMetrics.accuracy)"
            />
          </div>
        </el-col>
        <el-col :span="8">
          <div class="quality-metric">
            <div class="metric-title">一致性</div>
            <el-progress 
              :percentage="managementStore.qualityMetrics.consistency" 
              :color="getQualityColor(managementStore.qualityMetrics.consistency)"
            />
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <div class="card-header">
          <span>数据记录</span>
          <div class="header-actions">
            <el-select v-model="selectedPlatform" placeholder="选择平台" @change="filterData">
              <el-option label="全部平台" value="" />
              <el-option label="SHOPEE" value="SHOPEE" />
              <el-option label="TIKTOK" value="TIKTOK" />
              <el-option label="AMAZON" value="AMAZON" />
              <el-option label="MIAOSHOU" value="MIAOSHOU" />
            </el-select>
            <el-button type="primary" size="small" @click="refreshData">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>
      <el-table 
        :data="managementStore.dataRecords" 
        style="width: 100%" 
        stripe
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="platform" label="平台" width="100">
          <template #default="{ row }">
            <el-tag :type="getPlatformTagType(row.platform)">
              {{ row.platform }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="dataType" label="数据类型" width="120" />
        <el-table-column prop="recordCount" label="记录数" width="100" />
        <el-table-column prop="quality" label="质量" width="100">
          <template #default="{ row }">
            <el-progress 
              :percentage="row.quality" 
              :color="getQualityColor(row.quality)"
              :show-text="false"
            />
            <span class="quality-text">{{ row.quality }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="lastUpdated" label="最后更新" width="180" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="viewDetails(row)">
              查看详情
            </el-button>
            <el-button type="warning" size="small" @click="editRecord(row)">
              编辑
            </el-button>
            <el-button type="danger" size="small" @click="deleteRecord(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 批量操作 -->
      <div v-if="selectedRecords.length > 0" class="batch-actions">
        <el-alert
          :title="`已选择 ${selectedRecords.length} 条记录`"
          type="info"
          show-icon
          :closable="false"
        >
          <template #default>
            <div class="batch-buttons">
              <el-button type="primary" size="small" @click="batchExport">
                <el-icon><Download /></el-icon>
                批量导出
              </el-button>
              <el-button type="warning" size="small" @click="batchClean">
                <el-icon><Delete /></el-icon>
                批量清理
              </el-button>
              <el-button type="danger" size="small" @click="batchDelete">
                <el-icon><Delete /></el-icon>
                批量删除
              </el-button>
            </div>
          </template>
        </el-alert>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useManagementStore } from '@/stores/management'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Database,
  Check,
  Warning,
  TrendCharts,
  Search,
  Delete,
  Document,
  Refresh,
  Download
} from '@element-plus/icons-vue'

const managementStore = useManagementStore()

// 状态
const selectedPlatform = ref('')
const selectedRecords = ref([])

// 初始化数据
const initData = async () => {
  try {
    await managementStore.initData()
  } catch (error) {
    ElMessage.error('初始化数据失败')
  }
}

// 执行质量检查
const runQualityCheck = async () => {
  try {
    await ElMessageBox.confirm('确定要执行数据质量检查吗？', '确认操作', {
      type: 'warning'
    })
    
    await managementStore.runQualityCheck()
    ElMessage.success('数据质量检查完成')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('质量检查失败')
    }
  }
}

// 执行数据清理
const runDataCleaning = async () => {
  try {
    await ElMessageBox.confirm('确定要执行数据清理吗？', '确认操作', {
      type: 'warning'
    })
    
    await managementStore.runDataCleaning()
    ElMessage.success('数据清理完成')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('数据清理失败')
    }
  }
}

// 生成质量报告
const generateQualityReport = async () => {
  try {
    await managementStore.generateQualityReport()
    ElMessage.success('质量报告已生成')
  } catch (error) {
    ElMessage.error('生成报告失败')
  }
}

// 筛选数据
const filterData = () => {
  managementStore.filterData(selectedPlatform.value)
}

// 刷新数据
const refreshData = async () => {
  try {
    await managementStore.refreshData()
    ElMessage.success('数据已刷新')
  } catch (error) {
    ElMessage.error('刷新失败')
  }
}

// 查看详情
const viewDetails = (record) => {
  ElMessage.info(`查看记录 ${record.id} 的详情`)
}

// 编辑记录
const editRecord = (record) => {
  ElMessage.info(`编辑记录 ${record.id}`)
}

// 删除记录
const deleteRecord = async (record) => {
  try {
    await ElMessageBox.confirm(`确定要删除记录 ${record.id} 吗？`, '确认删除', {
      type: 'warning'
    })
    
    await managementStore.deleteRecord(record.id)
    ElMessage.success('记录已删除')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// 批量操作
const handleSelectionChange = (selection) => {
  selectedRecords.value = selection
}

const batchExport = async () => {
  try {
    await managementStore.batchExport(selectedRecords.value)
    ElMessage.success('批量导出完成')
  } catch (error) {
    ElMessage.error('批量导出失败')
  }
}

const batchClean = async () => {
  try {
    await ElMessageBox.confirm(`确定要清理选中的 ${selectedRecords.value.length} 条记录吗？`, '确认操作', {
      type: 'warning'
    })
    
    await managementStore.batchClean(selectedRecords.value)
    ElMessage.success('批量清理完成')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量清理失败')
    }
  }
}

const batchDelete = async () => {
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedRecords.value.length} 条记录吗？`, '确认删除', {
      type: 'warning'
    })
    
    await managementStore.batchDelete(selectedRecords.value)
    ElMessage.success('批量删除完成')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量删除失败')
    }
  }
}

// 工具函数
const getQualityColor = (quality) => {
  if (quality >= 90) return '#27ae60'
  if (quality >= 70) return '#f39c12'
  return '#e74c3c'
}

const getPlatformTagType = (platform) => {
  const typeMap = {
    'SHOPEE': 'success',
    'TIKTOK': 'primary',
    'AMAZON': 'warning',
    'MIAOSHOU': 'info'
  }
  return typeMap[platform] || 'info'
}

const getStatusType = (status) => {
  const typeMap = {
    'active': 'success',
    'inactive': 'info',
    'error': 'danger'
  }
  return typeMap[status] || 'info'
}

const getStatusText = (status) => {
  const textMap = {
    'active': '活跃',
    'inactive': '非活跃',
    'error': '错误'
  }
  return textMap[status] || status
}

onMounted(() => {
  initData()
})
</script>

<style scoped>
.management {
  padding: var(--content-padding);
}

.page-header {
  text-align: center;
  margin-bottom: var(--spacing-2xl);
  background: var(--gradient-primary);
  color: white;
  padding: var(--spacing-2xl);
  border-radius: var(--border-radius-lg);
}

.page-header h1 {
  margin: 0 0 var(--spacing-base) 0;
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-bold);
}

.page-header p {
  margin: 0;
  opacity: 0.9;
  font-size: var(--font-size-lg);
}

.overview-cards {
  margin-bottom: var(--spacing-2xl);
}

.overview-card {
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.card-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
}

.card-icon {
  font-size: var(--font-size-3xl);
  color: var(--secondary-color);
}

.card-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}

.card-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-xs);
}

.management-actions {
  margin-bottom: var(--spacing-2xl);
}

.action-card {
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.action-content {
  text-align: center;
}

.action-description {
  margin-top: var(--spacing-base);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.quality-report {
  margin-bottom: var(--spacing-2xl);
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.quality-metric {
  text-align: center;
}

.metric-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  margin-bottom: var(--spacing-base);
  color: var(--text-primary);
}

.data-table-card {
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: var(--spacing-base);
  align-items: center;
}

.quality-text {
  margin-left: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.batch-actions {
  margin-top: var(--spacing-lg);
}

.batch-buttons {
  display: flex;
  gap: var(--spacing-base);
  margin-top: var(--spacing-base);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .management {
    padding: var(--spacing-base);
  }
  
  .overview-cards .el-col {
    margin-bottom: var(--spacing-base);
  }
  
  .management-actions .el-col {
    margin-bottom: var(--spacing-base);
  }
}
</style>
