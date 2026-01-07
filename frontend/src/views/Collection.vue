<template>
  <div class="collection">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>🎮 数据采集中心</h1>
      <p>智能采集 • 实时监控 • 自动化处理</p>
    </div>

    <!-- 采集控制面板 -->
    <el-row :gutter="20" class="control-panel">
      <el-col :span="12">
        <el-card class="control-card">
          <template #header>
            <span>采集控制中心</span>
          </template>
          <div class="control-content">
            <div class="control-buttons">
              <el-button 
                type="primary" 
                size="large"
                :loading="collectionStore.loading"
                @click="startAllCollection"
              >
                <el-icon><Play /></el-icon>
                启动全平台采集
              </el-button>
              <el-button 
                type="warning" 
                size="large"
                @click="stopAllCollection"
              >
                <el-icon><VideoPause /></el-icon>
                停止所有采集
              </el-button>
            </div>
            <div class="collection-status">
              <el-tag :type="getStatusType(collectionStore.globalStatus)">
                {{ getStatusText(collectionStore.globalStatus) }}
              </el-tag>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="control-card">
          <template #header>
            <span>智能定时配置</span>
          </template>
          <div class="control-content">
            <el-form :model="scheduleForm" label-width="100px">
              <el-form-item label="采集频率">
                <el-select v-model="scheduleForm.frequency" placeholder="选择频率">
                  <el-option label="每小时" value="hourly" />
                  <el-option label="每天" value="daily" />
                  <el-option label="每周" value="weekly" />
                  <el-option label="手动" value="manual" />
                </el-select>
              </el-form-item>
              <el-form-item label="下次执行">
                <el-text type="info">{{ nextExecutionTime }}</el-text>
              </el-form-item>
            </el-form>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 平台采集状态 -->
    <el-card class="platform-status">
      <template #header>
        <span>平台采集状态</span>
      </template>
      <el-row :gutter="20">
        <el-col 
          v-for="platform in collectionStore.platforms" 
          :key="platform.name"
          :span="6"
        >
          <div class="platform-card" :class="getPlatformStatusClass(platform.status)">
            <div class="platform-icon">
              <el-icon><component :is="platform.icon" /></el-icon>
            </div>
            <div class="platform-info">
              <div class="platform-name">{{ platform.name }}</div>
              <div class="platform-status-text">{{ getStatusText(platform.status) }}</div>
              <div class="platform-progress">
                <el-progress 
                  :percentage="platform.progress" 
                  :status="getProgressStatus(platform.status)"
                  :show-text="false"
                />
              </div>
            </div>
            <div class="platform-actions">
              <el-button 
                size="small"
                :type="platform.status === 'running' ? 'warning' : 'primary'"
                @click="togglePlatformCollection(platform)"
              >
                {{ platform.status === 'running' ? '停止' : '启动' }}
              </el-button>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 实时监控 -->
    <el-row :gutter="20" class="monitoring-section">
      <el-col :span="12">
        <el-card class="monitoring-card">
          <template #header>
            <span>采集性能监控</span>
          </template>
          <div class="chart-container">
            <div ref="performanceChart" class="chart"></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="monitoring-card">
          <template #header>
            <span>成功率统计</span>
          </template>
          <div class="chart-container">
            <div ref="successChart" class="chart"></div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 采集历史记录 -->
    <el-card class="history-card">
      <template #header>
        <div class="card-header">
          <span>采集历史记录</span>
          <div class="header-actions">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              @change="filterHistory"
            />
            <el-button type="primary" size="small" @click="refreshHistory">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="collectionStore.historyRecords" style="width: 100%" stripe>
        <el-table-column prop="platform" label="平台" width="120">
          <template #default="{ row }">
            <el-tag :type="getPlatformTagType(row.platform)">
              {{ row.platform }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="taskType" label="任务类型" width="120" />
        <el-table-column prop="startTime" label="开始时间" width="180" />
        <el-table-column prop="endTime" label="结束时间" width="180" />
        <el-table-column prop="duration" label="耗时" width="100" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="filesCount" label="文件数量" width="100" />
        <el-table-column prop="errorMessage" label="错误信息" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import { useCollectionStore } from '@/stores/collection'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import {
  Play,
  VideoPause,
  Refresh,
  Shop,
  VideoCamera,
  ShoppingBag,
  Store
} from '@element-plus/icons-vue'

const collectionStore = useCollectionStore()

// 表单数据
const scheduleForm = ref({
  frequency: 'daily'
})

// 日期范围
const dateRange = ref([])

// 图表引用
const performanceChart = ref(null)
const successChart = ref(null)

// 计算属性
const nextExecutionTime = computed(() => {
  const now = new Date()
  const next = new Date(now.getTime() + 24 * 60 * 60 * 1000)
  return next.toLocaleString('zh-CN')
})

// 初始化数据
const initData = async () => {
  try {
    await collectionStore.initData()
    await nextTick()
    initCharts()
  } catch (error) {
    ElMessage.error('初始化数据失败')
  }
}

// 初始化图表
const initCharts = () => {
  initPerformanceChart()
  initSuccessChart()
}

// 性能监控图表
const initPerformanceChart = () => {
  if (!performanceChart.value) return
  
  const chart = echarts.init(performanceChart.value)
  const option = {
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: ['成功率', '处理速度']
    },
    xAxis: {
      type: 'category',
      data: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00']
    },
    yAxis: [
      {
        type: 'value',
        name: '成功率(%)',
        position: 'left'
      },
      {
        type: 'value',
        name: '处理速度(文件/分钟)',
        position: 'right'
      }
    ],
    series: [
      {
        name: '成功率',
        type: 'line',
        yAxisIndex: 0,
        data: [95, 97, 93, 98, 96, 94],
        smooth: true
      },
      {
        name: '处理速度',
        type: 'bar',
        yAxisIndex: 1,
        data: [120, 135, 110, 140, 125, 130]
      }
    ]
  }
  
  chart.setOption(option)
  
  window.addEventListener('resize', () => {
    chart.resize()
  })
}

// 成功率统计图表
const initSuccessChart = () => {
  if (!successChart.value) return
  
  const chart = echarts.init(successChart.value)
  const option = {
    tooltip: {
      trigger: 'item'
    },
    series: [
      {
        name: '采集状态',
        type: 'pie',
        radius: ['40%', '70%'],
        data: [
          { value: 85, name: '成功' },
          { value: 10, name: '失败' },
          { value: 5, name: '进行中' }
        ],
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        }
      }
    ]
  }
  
  chart.setOption(option)
  
  window.addEventListener('resize', () => {
    chart.resize()
  })
}

// 启动全平台采集
const startAllCollection = async () => {
  try {
    await ElMessageBox.confirm('确定要启动全平台采集吗？', '确认操作', {
      type: 'warning'
    })
    
    await collectionStore.startAllCollection()
    ElMessage.success('全平台采集已启动')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('启动采集失败')
    }
  }
}

// 停止所有采集
const stopAllCollection = async () => {
  try {
    await ElMessageBox.confirm('确定要停止所有采集吗？', '确认操作', {
      type: 'warning'
    })
    
    await collectionStore.stopAllCollection()
    ElMessage.success('所有采集已停止')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('停止采集失败')
    }
  }
}

// 切换平台采集
const togglePlatformCollection = async (platform) => {
  try {
    if (platform.status === 'running') {
      await collectionStore.stopPlatformCollection(platform.name)
      ElMessage.success(`${platform.name}采集已停止`)
    } else {
      await collectionStore.startPlatformCollection(platform.name)
      ElMessage.success(`${platform.name}采集已启动`)
    }
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

// 筛选历史记录
const filterHistory = () => {
  // 实现历史记录筛选逻辑
}

// 刷新历史记录
const refreshHistory = async () => {
  try {
    await collectionStore.fetchHistoryRecords()
    ElMessage.success('历史记录已刷新')
  } catch (error) {
    ElMessage.error('刷新失败')
  }
}

// 工具函数
const getStatusType = (status) => {
  const typeMap = {
    'idle': 'info',
    'running': 'success',
    'stopped': 'warning',
    'error': 'danger'
  }
  return typeMap[status] || 'info'
}

const getStatusText = (status) => {
  const textMap = {
    'idle': '空闲',
    'running': '运行中',
    'stopped': '已停止',
    'error': '错误'
  }
  return textMap[status] || status
}

const getPlatformStatusClass = (status) => {
  return `platform-${status}`
}

const getProgressStatus = (status) => {
  return status === 'running' ? 'success' : 'exception'
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

onMounted(() => {
  initData()
})
</script>

<style scoped>
.collection {
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

.control-panel {
  margin-bottom: var(--spacing-2xl);
}

.control-card {
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.control-content {
  text-align: center;
}

.control-buttons {
  display: flex;
  gap: var(--spacing-base);
  justify-content: center;
  margin-bottom: var(--spacing-lg);
}

.collection-status {
  margin-top: var(--spacing-base);
}

.platform-status {
  margin-bottom: var(--spacing-2xl);
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.platform-card {
  background: var(--white);
  border-radius: var(--border-radius-base);
  padding: var(--spacing-lg);
  text-align: center;
  transition: all var(--transition-base);
  border: 2px solid transparent;
}

.platform-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-base);
}

.platform-card.platform-running {
  border-color: var(--success-color);
}

.platform-card.platform-error {
  border-color: var(--error-color);
}

.platform-icon {
  font-size: var(--font-size-3xl);
  color: var(--secondary-color);
  margin-bottom: var(--spacing-base);
}

.platform-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  margin-bottom: var(--spacing-xs);
}

.platform-status-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-base);
}

.platform-progress {
  margin-bottom: var(--spacing-base);
}

.monitoring-section {
  margin-bottom: var(--spacing-2xl);
}

.monitoring-card {
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.chart-container {
  height: 300px;
}

.chart {
  width: 100%;
  height: 100%;
}

.history-card {
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

/* 响应式设计 */
@media (max-width: 768px) {
  .collection {
    padding: var(--spacing-base);
  }
  
  .control-panel .el-col {
    margin-bottom: var(--spacing-base);
  }
  
  .platform-status .el-col {
    margin-bottom: var(--spacing-base);
  }
  
  .monitoring-section .el-col {
    margin-bottom: var(--spacing-base);
  }
  
  .chart-container {
    height: 250px;
  }
}
</style>
