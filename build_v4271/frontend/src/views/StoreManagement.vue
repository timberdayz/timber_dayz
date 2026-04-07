<template>
  <div class="store-management">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Shop /></el-icon>
          店铺管理
        </h1>
        <p class="page-subtitle">统一管理多平台店铺，提升运营效率</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="refreshData">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
      </div>
    </div>

    <!-- 功能导航区域 -->
    <div class="function-nav">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="🏪 店铺概览" name="overview">
          <!-- 店铺概览内容 -->
          <div class="overview-content">
            <!-- 店铺统计指标 -->
            <el-row :gutter="20" style="margin-bottom: 20px;">
              <el-col :span="6">
                <el-card class="metric-card" shadow="hover">
                  <div class="metric-content">
                    <div class="metric-icon total">
                      <el-icon><Shop /></el-icon>
                    </div>
                    <div class="metric-info">
                      <div class="metric-label">总店铺数</div>
                      <div class="metric-value">12</div>
                      <div class="metric-change positive">+2</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="6">
                <el-card class="metric-card" shadow="hover">
                  <div class="metric-content">
                    <div class="metric-icon active">
                      <el-icon><CircleCheck /></el-icon>
                    </div>
                    <div class="metric-info">
                      <div class="metric-label">活跃店铺</div>
                      <div class="metric-value">10</div>
                      <div class="metric-change positive">+1</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="6">
                <el-card class="metric-card" shadow="hover">
                  <div class="metric-content">
                    <div class="metric-icon warning">
                      <el-icon><Warning /></el-icon>
                    </div>
                    <div class="metric-info">
                      <div class="metric-label">异常店铺</div>
                      <div class="metric-value">2</div>
                      <div class="metric-change negative">+1</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="6">
                <el-card class="metric-card" shadow="hover">
                  <div class="metric-content">
                    <div class="metric-icon revenue">
                      <el-icon><Money /></el-icon>
                    </div>
                    <div class="metric-info">
                      <div class="metric-label">总销售额</div>
                      <div class="metric-value">¥2.3M</div>
                      <div class="metric-change positive">+15.2%</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>

            <!-- 店铺列表 -->
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>店铺管理</span>
                      <div class="header-actions">
                        <el-button type="primary" @click="addStore">
                          <el-icon><Plus /></el-icon>
                          添加店铺
                        </el-button>
                        <el-button type="success" @click="syncAllStores">
                          <el-icon><Refresh /></el-icon>
                          同步所有店铺
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="store-management">
                    <!-- 搜索和筛选 -->
                    <div class="search-filters">
                      <el-row :gutter="20">
                        <el-col :span="6">
                          <el-input v-model="searchKeyword" placeholder="搜索店铺名称" clearable>
                            <template #prefix>
                              <el-icon><Search /></el-icon>
                            </template>
                          </el-input>
                        </el-col>
                        <el-col :span="4">
                          <el-select v-model="platformFilter" placeholder="选择平台" clearable>
                            <el-option label="全部平台" value=""></el-option>
                            <el-option label="Shopee" value="shopee"></el-option>
                            <el-option label="Amazon" value="amazon"></el-option>
                            <el-option label="Lazada" value="lazada"></el-option>
                            <el-option label="eBay" value="ebay"></el-option>
                          </el-select>
                        </el-col>
                        <el-col :span="4">
                          <el-select v-model="statusFilter" placeholder="选择状态" clearable>
                            <el-option label="全部状态" value=""></el-option>
                            <el-option label="正常" value="normal"></el-option>
                            <el-option label="异常" value="error"></el-option>
                            <el-option label="维护中" value="maintenance"></el-option>
                          </el-select>
                        </el-col>
                        <el-col :span="4">
                          <el-button type="primary" @click="searchStores">搜索</el-button>
                        </el-col>
                      </el-row>
                    </div>

                    <!-- 店铺表格 -->
                    <el-table :data="filteredStores" style="width: 100%; margin-top: 20px;">
                      <el-table-column prop="name" label="店铺名称" width="200"></el-table-column>
                      <el-table-column prop="platform" label="平台" width="120">
                        <template #default="scope">
                          <el-tag :type="getPlatformType(scope.row.platform)">
                            {{ scope.row.platform }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column prop="region" label="地区" width="100"></el-table-column>
                      <el-table-column prop="status" label="状态" width="100">
                        <template #default="scope">
                          <el-tag :type="getStatusType(scope.row.status)">
                            {{ scope.row.status }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column prop="healthScore" label="健康度" width="120">
                        <template #default="scope">
                          <el-progress :percentage="scope.row.healthScore" :color="getHealthColor(scope.row.healthScore)"></el-progress>
                        </template>
                      </el-table-column>
                      <el-table-column prop="lastSync" label="最后同步" width="150"></el-table-column>
                      <el-table-column prop="sales" label="销售额" width="120"></el-table-column>
                      <el-table-column label="操作" width="200">
                        <template #default="scope">
                          <el-button type="primary" size="small" @click="editStore(scope.row)">
                            编辑
                          </el-button>
                          <el-button type="info" size="small" @click="viewStoreDetail(scope.row)">
                            详情
                          </el-button>
                          <el-button type="success" size="small" @click="syncStore(scope.row)">
                            同步
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="📊 店铺分析" name="analysis">
          <!-- 店铺分析内容 -->
          <div class="analysis-content">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>平台销售对比</span>
                    </div>
                  </template>
                  <div class="chart-container">
                    <div ref="platformSalesChart" class="chart"></div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>店铺健康度分布</span>
                    </div>
                  </template>
                  <div class="chart-container">
                    <div ref="healthDistributionChart" class="chart"></div>
                  </div>
                </el-card>
              </el-col>
            </el-row>

            <el-row :gutter="20" style="margin-top: 20px;">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>店铺绩效排行</span>
                    </div>
                  </template>
                  <div class="store-ranking">
                    <el-table :data="storeRanking" style="width: 100%;">
                      <el-table-column prop="rank" label="排名" width="80"></el-table-column>
                      <el-table-column prop="name" label="店铺名称" width="200"></el-table-column>
                      <el-table-column prop="platform" label="平台" width="120"></el-table-column>
                      <el-table-column prop="sales" label="销售额" width="120"></el-table-column>
                      <el-table-column prop="orders" label="订单数" width="120"></el-table-column>
                      <el-table-column prop="conversion" label="转化率" width="120"></el-table-column>
                      <el-table-column prop="healthScore" label="健康度" width="120">
                        <template #default="scope">
                          <el-progress :percentage="scope.row.healthScore" :color="getHealthColor(scope.row.healthScore)"></el-progress>
                        </template>
                      </el-table-column>
                      <el-table-column label="操作" width="150">
                        <template #default="scope">
                          <el-button type="primary" size="small" @click="viewStoreDetail(scope.row)">
                            查看详情
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="🔄 数据同步" name="sync">
          <!-- 数据同步内容 -->
          <div class="sync-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>数据同步管理</span>
                      <div class="header-actions">
                        <el-button type="primary" @click="startSyncAll">
                          <el-icon><Refresh /></el-icon>
                          开始全量同步
                        </el-button>
                        <el-button type="success" @click="startIncrementalSync">
                          <el-icon><RefreshRight /></el-icon>
                          增量同步
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="sync-management">
                    <el-table :data="syncTasks" style="width: 100%;">
                      <el-table-column prop="storeName" label="店铺名称" width="200"></el-table-column>
                      <el-table-column prop="platform" label="平台" width="120"></el-table-column>
                      <el-table-column prop="syncType" label="同步类型" width="120"></el-table-column>
                      <el-table-column prop="status" label="状态" width="120">
                        <template #default="scope">
                          <el-tag :type="getSyncStatusType(scope.row.status)">
                            {{ scope.row.status }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column prop="progress" label="进度" width="150">
                        <template #default="scope">
                          <el-progress :percentage="scope.row.progress" :color="getProgressColor(scope.row.progress)"></el-progress>
                        </template>
                      </el-table-column>
                      <el-table-column prop="startTime" label="开始时间" width="150"></el-table-column>
                      <el-table-column prop="endTime" label="结束时间" width="150"></el-table-column>
                      <el-table-column label="操作" width="150">
                        <template #default="scope">
                          <el-button type="primary" size="small" @click="viewSyncDetail(scope.row)">
                            查看详情
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </el-card>
              </el-col>
            </el-row>

            <el-row :gutter="20" style="margin-top: 20px;">
              <el-col :span="8">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>同步统计</span>
                    </div>
                  </template>
                  <div class="sync-stats">
                    <div class="stat-item">
                      <div class="stat-label">今日同步次数</div>
                      <div class="stat-value">24次</div>
                      <div class="stat-change positive">+3次</div>
                    </div>
                    <div class="stat-item">
                      <div class="stat-label">成功同步</div>
                      <div class="stat-value">22次</div>
                      <div class="stat-change positive">+2次</div>
                    </div>
                    <div class="stat-item">
                      <div class="stat-label">失败同步</div>
                      <div class="stat-value">2次</div>
                      <div class="stat-change negative">+1次</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="8">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>同步设置</span>
                    </div>
                  </template>
                  <div class="sync-settings">
                    <div class="setting-item">
                      <div class="setting-label">自动同步间隔</div>
                      <div class="setting-value">30分钟</div>
                    </div>
                    <div class="setting-item">
                      <div class="setting-label">同步超时时间</div>
                      <div class="setting-value">10分钟</div>
                    </div>
                    <div class="setting-item">
                      <div class="setting-label">重试次数</div>
                      <div class="setting-value">3次</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="8">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>同步日志</span>
                    </div>
                  </template>
                  <div class="sync-logs">
                    <div class="log-item">
                      <div class="log-time">14:30:25</div>
                      <div class="log-content">Shopee店铺同步成功</div>
                    </div>
                    <div class="log-item">
                      <div class="log-time">14:25:18</div>
                      <div class="log-content">Amazon店铺同步失败</div>
                    </div>
                    <div class="log-item">
                      <div class="log-time">14:20:12</div>
                      <div class="log-content">Lazada店铺同步成功</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="⚙️ 店铺设置" name="settings">
          <!-- 店铺设置内容 -->
          <div class="settings-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>店铺配置管理</span>
                      <div class="header-actions">
                        <el-button type="primary" @click="saveSettings">
                          <el-icon><Check /></el-icon>
                          保存设置
                        </el-button>
                        <el-button type="success" @click="resetSettings">
                          <el-icon><RefreshLeft /></el-icon>
                          重置设置
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="settings-management">
                    <el-form :model="storeSettings" label-width="150px">
                      <el-form-item label="默认同步间隔">
                        <el-select v-model="storeSettings.syncInterval" placeholder="选择同步间隔">
                          <el-option label="15分钟" value="15m"></el-option>
                          <el-option label="30分钟" value="30m"></el-option>
                          <el-option label="1小时" value="1h"></el-option>
                          <el-option label="2小时" value="2h"></el-option>
                        </el-select>
                      </el-form-item>
                      <el-form-item label="同步超时时间">
                        <el-input-number v-model="storeSettings.syncTimeout" :min="5" :max="60" controls-position="right"></el-input-number>
                        <span style="margin-left: 10px;">分钟</span>
                      </el-form-item>
                      <el-form-item label="重试次数">
                        <el-input-number v-model="storeSettings.retryCount" :min="1" :max="10" controls-position="right"></el-input-number>
                      </el-form-item>
                      <el-form-item label="自动同步">
                        <el-switch v-model="storeSettings.autoSync"></el-switch>
                      </el-form-item>
                      <el-form-item label="异常告警">
                        <el-switch v-model="storeSettings.alertEnabled"></el-switch>
                      </el-form-item>
                      <el-form-item label="告警邮箱">
                        <el-input v-model="storeSettings.alertEmail" placeholder="请输入告警邮箱"></el-input>
                      </el-form-item>
                    </el-form>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { 
  Shop, Refresh, CircleCheck, Warning, Money, Plus, Search,
  Check, RefreshLeft, RefreshRight
} from '@element-plus/icons-vue'

// 响应式数据
const activeTab = ref('overview')
const searchKeyword = ref('')
const platformFilter = ref('')
const statusFilter = ref('')

// 店铺数据
const stores = ref([
  {
    id: 1,
    name: 'Shopee旗舰店',
    platform: 'Shopee',
    region: '新加坡',
    status: '正常',
    healthScore: 95,
    lastSync: '2024-01-15 14:30',
    sales: '¥456,789'
  },
  {
    id: 2,
    name: 'Amazon美国站',
    platform: 'Amazon',
    region: '美国',
    status: '正常',
    healthScore: 88,
    lastSync: '2024-01-15 14:25',
    sales: '¥789,123'
  },
  {
    id: 3,
    name: 'Lazada泰国站',
    platform: 'Lazada',
    region: '泰国',
    status: '异常',
    healthScore: 65,
    lastSync: '2024-01-15 13:45',
    sales: '¥234,567'
  },
  {
    id: 4,
    name: 'eBay德国站',
    platform: 'eBay',
    region: '德国',
    status: '维护中',
    healthScore: 72,
    lastSync: '2024-01-15 12:30',
    sales: '¥345,678'
  }
])

// 店铺排行数据
const storeRanking = ref([
  {
    rank: 1,
    name: 'Amazon美国站',
    platform: 'Amazon',
    sales: '¥789,123',
    orders: '1,234',
    conversion: '3.45%',
    healthScore: 88
  },
  {
    rank: 2,
    name: 'Shopee旗舰店',
    platform: 'Shopee',
    sales: '¥456,789',
    orders: '2,345',
    conversion: '2.89%',
    healthScore: 95
  },
  {
    rank: 3,
    name: 'eBay德国站',
    platform: 'eBay',
    sales: '¥345,678',
    orders: '987',
    conversion: '2.34%',
    healthScore: 72
  },
  {
    rank: 4,
    name: 'Lazada泰国站',
    platform: 'Lazada',
    sales: '¥234,567',
    orders: '654',
    conversion: '1.89%',
    healthScore: 65
  }
])

// 同步任务数据
const syncTasks = ref([
  {
    storeName: 'Shopee旗舰店',
    platform: 'Shopee',
    syncType: '全量同步',
    status: '进行中',
    progress: 75,
    startTime: '2024-01-15 14:30',
    endTime: '-'
  },
  {
    storeName: 'Amazon美国站',
    platform: 'Amazon',
    syncType: '增量同步',
    status: '已完成',
    progress: 100,
    startTime: '2024-01-15 14:25',
    endTime: '2024-01-15 14:28'
  },
  {
    storeName: 'Lazada泰国站',
    platform: 'Lazada',
    syncType: '全量同步',
    status: '失败',
    progress: 45,
    startTime: '2024-01-15 13:45',
    endTime: '2024-01-15 13:50'
  }
])

// 店铺设置数据
const storeSettings = ref({
  syncInterval: '30m',
  syncTimeout: 10,
  retryCount: 3,
  autoSync: true,
  alertEnabled: true,
  alertEmail: 'admin@xihong-erp.com'
})

// 计算属性
const filteredStores = computed(() => {
  let result = stores.value
  
  if (searchKeyword.value) {
    result = result.filter(store => 
      store.name.includes(searchKeyword.value)
    )
  }
  
  if (platformFilter.value) {
    result = result.filter(store => store.platform.toLowerCase() === platformFilter.value)
  }
  
  if (statusFilter.value) {
    result = result.filter(store => store.status === statusFilter.value)
  }
  
  return result
})

// 方法
const refreshData = () => {
  ElMessage.success('店铺数据已刷新')
}

const handleTabChange = (tabName) => {
  ElMessage.info(`切换到${tabName}标签页`)
}

const addStore = () => {
  ElMessage.info('添加店铺功能开发中...')
}

const syncAllStores = () => {
  ElMessage.info('同步所有店铺功能开发中...')
}

const searchStores = () => {
  ElMessage.info('搜索店铺功能开发中...')
}

const editStore = (row) => {
  ElMessage.info(`编辑店铺: ${row.name}`)
}

const viewStoreDetail = (row) => {
  ElMessage.info(`查看店铺详情: ${row.name}`)
}

const syncStore = (row) => {
  ElMessage.info(`同步店铺: ${row.name}`)
}

const startSyncAll = () => {
  ElMessage.info('开始全量同步功能开发中...')
}

const startIncrementalSync = () => {
  ElMessage.info('开始增量同步功能开发中...')
}

const viewSyncDetail = (row) => {
  ElMessage.info(`查看同步详情: ${row.storeName}`)
}

const saveSettings = () => {
  ElMessage.success('店铺设置已保存')
}

const resetSettings = () => {
  ElMessage.info('重置店铺设置功能开发中...')
}

const getPlatformType = (platform) => {
  const platformMap = {
    'Shopee': 'success',
    'Amazon': 'warning',
    'Lazada': 'primary',
    'eBay': 'info'
  }
  return platformMap[platform] || 'info'
}

const getStatusType = (status) => {
  const statusMap = {
    '正常': 'success',
    '异常': 'danger',
    '维护中': 'warning'
  }
  return statusMap[status] || 'info'
}

const getHealthColor = (score) => {
  if (score >= 90) return '#67C23A'
  if (score >= 80) return '#E6A23C'
  if (score >= 70) return '#F56C6C'
  return '#909399'
}

const getSyncStatusType = (status) => {
  const statusMap = {
    '进行中': 'warning',
    '已完成': 'success',
    '失败': 'danger'
  }
  return statusMap[status] || 'info'
}

const getProgressColor = (progress) => {
  if (progress >= 80) return '#67C23A'
  if (progress >= 50) return '#E6A23C'
  return '#F56C6C'
}
</script>

<style scoped>
.store-management {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 24px;
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  border-radius: 12px;
  color: white;
}

.header-content .page-title {
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 8px 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-content .page-subtitle {
  font-size: 16px;
  opacity: 0.9;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.development-notice {
  margin-top: 24px;
}
</style>
