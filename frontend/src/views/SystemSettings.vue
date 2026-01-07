<template>
  <div class="system-settings">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Setting /></el-icon>
          系统设置
        </h1>
        <p class="page-subtitle">系统配置管理，确保系统稳定运行</p>
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
        <el-tab-pane label="⚙️ 系统配置" name="config">
          <!-- 系统配置内容 -->
          <div class="config-content">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>基础配置</span>
                    </div>
                  </template>
                  <div class="config-management">
                    <el-form :model="systemConfig" label-width="120px">
                      <el-form-item label="系统名称">
                        <el-input v-model="systemConfig.systemName" placeholder="请输入系统名称"></el-input>
                      </el-form-item>
                      <el-form-item label="系统版本">
                        <el-input v-model="systemConfig.version" disabled></el-input>
                      </el-form-item>
                      <el-form-item label="时区设置">
                        <el-select v-model="systemConfig.timezone" placeholder="选择时区">
                          <el-option label="北京时间 (UTC+8)" value="Asia/Shanghai"></el-option>
                          <el-option label="纽约时间 (UTC-5)" value="America/New_York"></el-option>
                          <el-option label="伦敦时间 (UTC+0)" value="Europe/London"></el-option>
                          <el-option label="东京时间 (UTC+9)" value="Asia/Tokyo"></el-option>
                        </el-select>
                      </el-form-item>
                      <el-form-item label="语言设置">
                        <el-select v-model="systemConfig.language" placeholder="选择语言">
                          <el-option label="简体中文" value="zh-CN"></el-option>
                          <el-option label="English" value="en-US"></el-option>
                          <el-option label="繁體中文" value="zh-TW"></el-option>
                        </el-select>
                      </el-form-item>
                      <el-form-item label="货币设置">
                        <el-select v-model="systemConfig.currency" placeholder="选择货币">
                          <el-option label="人民币 (CNY)" value="CNY"></el-option>
                          <el-option label="美元 (USD)" value="USD"></el-option>
                          <el-option label="欧元 (EUR)" value="EUR"></el-option>
                          <el-option label="日元 (JPY)" value="JPY"></el-option>
                        </el-select>
                      </el-form-item>
                    </el-form>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>数据库配置</span>
                    </div>
                  </template>
                  <div class="config-management">
                    <el-form :model="databaseConfig" label-width="120px">
                      <el-form-item label="数据库类型">
                        <el-select v-model="databaseConfig.type" placeholder="选择数据库类型">
                          <el-option label="SQLite" value="sqlite"></el-option>
                          <el-option label="PostgreSQL" value="postgresql"></el-option>
                          <el-option label="MySQL" value="mysql"></el-option>
                        </el-select>
                      </el-form-item>
                      <el-form-item label="主机地址">
                        <el-input v-model="databaseConfig.host" placeholder="请输入主机地址"></el-input>
                      </el-form-item>
                      <el-form-item label="端口号">
                        <el-input-number v-model="databaseConfig.port" :min="1" :max="65535" controls-position="right"></el-input-number>
                      </el-form-item>
                      <el-form-item label="数据库名">
                        <el-input v-model="databaseConfig.database" placeholder="请输入数据库名"></el-input>
                      </el-form-item>
                      <el-form-item label="用户名">
                        <el-input v-model="databaseConfig.username" placeholder="请输入用户名"></el-input>
                      </el-form-item>
                      <el-form-item label="密码">
                        <el-input v-model="databaseConfig.password" type="password" placeholder="请输入密码"></el-input>
                      </el-form-item>
                    </el-form>
                  </div>
                </el-card>
              </el-col>
            </el-row>

            <el-row :gutter="20" style="margin-top: 20px;">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>系统配置管理</span>
                      <div class="header-actions">
                        <el-button type="primary" @click="saveConfig">
                          <el-icon><Check /></el-icon>
                          保存配置
                        </el-button>
                        <el-button type="success" @click="testConnection">
                          <el-icon><Connection /></el-icon>
                          测试连接
                        </el-button>
                        <el-button type="warning" @click="resetConfig">
                          <el-icon><RefreshLeft /></el-icon>
                          重置配置
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="config-actions">
                    <el-alert
                      title="配置说明"
                      description="修改系统配置后需要重启系统才能生效。请谨慎操作，建议在维护时间进行配置修改。"
                      type="info"
                      show-icon
                      :closable="false"
                    />
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="🔐 权限管理" name="permission">
          <!-- 权限管理内容 -->
          <div class="permission-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>角色权限管理</span>
                      <div class="header-actions">
                        <el-button type="primary" @click="addRole">
                          <el-icon><Plus /></el-icon>
                          添加角色
                        </el-button>
                        <el-button type="success" @click="savePermissions">
                          <el-icon><Check /></el-icon>
                          保存权限
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="permission-management">
                    <el-table :data="roles" style="width: 100%;">
                      <el-table-column prop="name" label="角色名称" width="150"></el-table-column>
                      <el-table-column prop="description" label="角色描述" width="200"></el-table-column>
                      <el-table-column prop="userCount" label="用户数量" width="100"></el-table-column>
                      <el-table-column prop="permissions" label="权限数量" width="100"></el-table-column>
                      <el-table-column prop="status" label="状态" width="100">
                        <template #default="scope">
                          <el-tag :type="scope.row.status === '启用' ? 'success' : 'danger'">
                            {{ scope.row.status }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column prop="createTime" label="创建时间" width="150"></el-table-column>
                      <el-table-column label="操作" width="200">
                        <template #default="scope">
                          <el-button type="primary" size="small" @click="editRole(scope.row)">
                            编辑
                          </el-button>
                          <el-button type="info" size="small" @click="viewPermissions(scope.row)">
                            权限
                          </el-button>
                          <el-button type="danger" size="small" @click="deleteRole(scope.row)">
                            删除
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </el-card>
              </el-col>
            </el-row>

            <el-row :gutter="20" style="margin-top: 20px;">
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>权限模块</span>
                    </div>
                  </template>
                  <div class="permission-modules">
                    <el-tree
                      :data="permissionModules"
                      show-checkbox
                      node-key="id"
                      :default-expand-all="true"
                      :default-checked-keys="checkedPermissions"
                      @check="handlePermissionCheck"
                    >
                      <template #default="{ node, data }">
                        <span class="permission-node">
                          <el-icon v-if="data.type === 'module'"><Folder /></el-icon>
                          <el-icon v-else><Document /></el-icon>
                          {{ data.label }}
                        </span>
                      </template>
                    </el-tree>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>权限统计</span>
                    </div>
                  </template>
                  <div class="permission-stats">
                    <div class="stat-item">
                      <div class="stat-label">总角色数</div>
                      <div class="stat-value">5</div>
                      <div class="stat-change positive">+1</div>
                    </div>
                    <div class="stat-item">
                      <div class="stat-label">总权限数</div>
                      <div class="stat-value">32</div>
                      <div class="stat-change positive">+3</div>
                    </div>
                    <div class="stat-item">
                      <div class="stat-label">活跃角色</div>
                      <div class="stat-value">4</div>
                      <div class="stat-change positive">+1</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="📊 系统监控" name="monitor">
          <!-- 系统监控内容 -->
          <div class="monitor-content">
            <el-row :gutter="20">
              <el-col :span="6">
                <el-card class="metric-card" shadow="hover">
                  <div class="metric-content">
                    <div class="metric-icon cpu">
                      <el-icon><Monitor /></el-icon>
                    </div>
                    <div class="metric-info">
                      <div class="metric-label">CPU使用率</div>
                      <div class="metric-value">45%</div>
                      <div class="metric-change positive">-5%</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="6">
                <el-card class="metric-card" shadow="hover">
                  <div class="metric-content">
                    <div class="metric-icon memory">
                      <el-icon><MemoryCard /></el-icon>
                    </div>
                    <div class="metric-info">
                      <div class="metric-label">内存使用率</div>
                      <div class="metric-value">68%</div>
                      <div class="metric-change negative">+3%</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="6">
                <el-card class="metric-card" shadow="hover">
                  <div class="metric-content">
                    <div class="metric-icon disk">
                      <el-icon><HardDisk /></el-icon>
                    </div>
                    <div class="metric-info">
                      <div class="metric-label">磁盘使用率</div>
                      <div class="metric-value">32%</div>
                      <div class="metric-change positive">+1%</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="6">
                <el-card class="metric-card" shadow="hover">
                  <div class="metric-content">
                    <div class="metric-icon network">
                      <el-icon><Connection /></el-icon>
                    </div>
                    <div class="metric-info">
                      <div class="metric-label">网络状态</div>
                      <div class="metric-value">正常</div>
                      <div class="metric-change positive">稳定</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>

            <el-row :gutter="20" style="margin-top: 20px;">
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>系统性能监控</span>
                    </div>
                  </template>
                  <div class="chart-container">
                    <div ref="performanceChart" class="chart"></div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>服务状态监控</span>
                    </div>
                  </template>
                  <div class="service-status">
                    <div class="service-item">
                      <div class="service-name">Web服务</div>
                      <div class="service-status-value">
                        <el-tag type="success">运行中</el-tag>
                      </div>
                      <div class="service-uptime">运行时间: 15天</div>
                    </div>
                    <div class="service-item">
                      <div class="service-name">数据库服务</div>
                      <div class="service-status-value">
                        <el-tag type="success">运行中</el-tag>
                      </div>
                      <div class="service-uptime">运行时间: 15天</div>
                    </div>
                    <div class="service-item">
                      <div class="service-name">Redis缓存</div>
                      <div class="service-status-value">
                        <el-tag type="success">运行中</el-tag>
                      </div>
                      <div class="service-uptime">运行时间: 15天</div>
                    </div>
                    <div class="service-item">
                      <div class="service-name">数据采集服务</div>
                      <div class="service-status-value">
                        <el-tag type="warning">维护中</el-tag>
                      </div>
                      <div class="service-uptime">维护时间: 2小时</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="📝 系统日志" name="logs">
          <!-- 系统日志内容 -->
          <div class="logs-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>系统日志管理</span>
                      <div class="header-actions">
                        <el-button type="primary" @click="refreshLogs">
                          <el-icon><Refresh /></el-icon>
                          刷新日志
                        </el-button>
                        <el-button type="success" @click="exportLogs">
                          <el-icon><Download /></el-icon>
                          导出日志
                        </el-button>
                        <el-button type="warning" @click="clearLogs">
                          <el-icon><Delete /></el-icon>
                          清空日志
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="logs-management">
                    <!-- 日志筛选 -->
                    <div class="log-filters">
                      <el-row :gutter="20">
                        <el-col :span="4">
                          <el-select v-model="logLevel" placeholder="选择日志级别">
                            <el-option label="全部级别" value=""></el-option>
                            <el-option label="ERROR" value="error"></el-option>
                            <el-option label="WARN" value="warn"></el-option>
                            <el-option label="INFO" value="info"></el-option>
                            <el-option label="DEBUG" value="debug"></el-option>
                          </el-select>
                        </el-col>
                        <el-col :span="4">
                          <el-select v-model="logModule" placeholder="选择模块">
                            <el-option label="全部模块" value=""></el-option>
                            <el-option label="系统核心" value="core"></el-option>
                            <el-option label="数据采集" value="collection"></el-option>
                            <el-option label="数据管理" value="management"></el-option>
                            <el-option label="用户管理" value="user"></el-option>
                          </el-select>
                        </el-col>
                        <el-col :span="4">
                          <el-date-picker v-model="logDateRange" type="datetimerange" placeholder="选择时间范围"></el-date-picker>
                        </el-col>
                        <el-col :span="4">
                          <el-button type="primary" @click="filterLogs">筛选</el-button>
                        </el-col>
                      </el-row>
                    </div>

                    <!-- 日志表格 -->
                    <el-table :data="systemLogs" style="width: 100%; margin-top: 20px;">
                      <el-table-column prop="timestamp" label="时间" width="150"></el-table-column>
                      <el-table-column prop="level" label="级别" width="80">
                        <template #default="scope">
                          <el-tag :type="getLogLevelType(scope.row.level)">
                            {{ scope.row.level }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column prop="module" label="模块" width="120"></el-table-column>
                      <el-table-column prop="message" label="消息" width="300"></el-table-column>
                      <el-table-column prop="user" label="用户" width="120"></el-table-column>
                      <el-table-column prop="ip" label="IP地址" width="120"></el-table-column>
                      <el-table-column label="操作" width="100">
                        <template #default="scope">
                          <el-button type="primary" size="small" @click="viewLogDetail(scope.row)">
                            详情
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
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

// 响应式数据
const activeTab = ref('config')

// 系统配置数据
const systemConfig = ref({
  systemName: '西红ERP系统',
  version: 'v4.6.1',
  timezone: 'Asia/Shanghai',
  language: 'zh-CN',
  currency: 'CNY'
})

// 数据库配置数据
const databaseConfig = ref({
  type: 'sqlite',
  host: 'localhost',
  port: 5432,
  database: 'xihong_erp',
  username: 'admin',
  password: ''
})

// 角色数据
const roles = ref([
  {
    id: 1,
    name: '超级管理员',
    description: '拥有系统所有权限',
    userCount: 1,
    permissions: 32,
    status: '启用',
    createTime: '2024-01-01'
  },
  {
    id: 2,
    name: '系统管理员',
    description: '系统配置和用户管理',
    userCount: 2,
    permissions: 24,
    status: '启用',
    createTime: '2024-01-02'
  },
  {
    id: 3,
    name: '业务主管',
    description: '业务数据查看和分析',
    userCount: 5,
    permissions: 16,
    status: '启用',
    createTime: '2024-01-03'
  },
  {
    id: 4,
    name: '操作员',
    description: '基础数据录入和查看',
    userCount: 15,
    permissions: 8,
    status: '启用',
    createTime: '2024-01-04'
  },
  {
    id: 5,
    name: '财务专员',
    description: '财务数据管理',
    userCount: 3,
    permissions: 12,
    status: '启用',
    createTime: '2024-01-05'
  }
])

// 权限模块数据
const permissionModules = ref([
  {
    id: 1,
    label: '系统管理',
    type: 'module',
    children: [
      { id: 11, label: '用户管理', type: 'permission' },
      { id: 12, label: '角色管理', type: 'permission' },
      { id: 13, label: '权限管理', type: 'permission' },
      { id: 14, label: '系统配置', type: 'permission' }
    ]
  },
  {
    id: 2,
    label: '业务管理',
    type: 'module',
    children: [
      { id: 21, label: '销售分析', type: 'permission' },
      { id: 22, label: '库存管理', type: 'permission' },
      { id: 23, label: '订单管理', type: 'permission' },
      { id: 24, label: '客户管理', type: 'permission' }
    ]
  },
  {
    id: 3,
    label: '数据管理',
    type: 'module',
    children: [
      { id: 31, label: '数据采集', type: 'permission' },
      { id: 32, label: '数据导入', type: 'permission' },
      { id: 33, label: '数据导出', type: 'permission' },
      { id: 34, label: '数据清理', type: 'permission' }
    ]
  }
])

// 选中的权限
const checkedPermissions = ref([11, 12, 13, 14, 21, 22, 23, 24, 31, 32, 33, 34])

// 日志数据
const logLevel = ref('')
const logModule = ref('')
const logDateRange = ref([])
const systemLogs = ref([
  {
    timestamp: '2024-01-16 10:30:15',
    level: 'INFO',
    module: '系统核心',
    message: '系统启动成功',
    user: 'admin',
    ip: '127.0.0.1'
  },
  {
    timestamp: '2024-01-16 10:25:30',
    level: 'WARN',
    module: '数据采集',
    message: '数据采集任务延迟',
    user: 'system',
    ip: '127.0.0.1'
  },
  {
    timestamp: '2024-01-16 10:20:45',
    level: 'ERROR',
    module: '用户管理',
    message: '用户登录失败',
    user: 'guest',
    ip: '192.168.1.100'
  },
  {
    timestamp: '2024-01-16 10:15:20',
    level: 'INFO',
    module: '数据管理',
    message: '数据同步完成',
    user: 'admin',
    ip: '127.0.0.1'
  },
  {
    timestamp: '2024-01-16 10:10:10',
    level: 'DEBUG',
    module: '系统核心',
    message: '内存使用率检查',
    user: 'system',
    ip: '127.0.0.1'
  }
])

// 图表引用
const performanceChart = ref(null)

// 方法
const handleTabChange = (tabName) => {
  console.log('切换到标签页:', tabName)
  if (tabName === 'monitor') {
    // 延迟初始化图表，确保DOM已渲染
    setTimeout(() => {
      initPerformanceChart()
    }, 100)
  }
}

const saveConfig = () => {
  ElMessage.success('系统配置保存成功')
}

const testConnection = () => {
  ElMessage.success('数据库连接测试成功')
}

const resetConfig = () => {
  ElMessage.warning('配置已重置为默认值')
}

const addRole = () => {
  ElMessage.info('添加角色功能开发中')
}

const savePermissions = () => {
  ElMessage.success('权限配置保存成功')
}

const editRole = (role) => {
  ElMessage.info(`编辑角色: ${role.name}`)
}

const viewPermissions = (role) => {
  ElMessage.info(`查看角色权限: ${role.name}`)
}

const deleteRole = (role) => {
  ElMessage.warning(`删除角色: ${role.name}`)
}

const handlePermissionCheck = (data, checked) => {
  console.log('权限选择变化:', data, checked)
}

const refreshLogs = () => {
  ElMessage.success('日志已刷新')
}

const exportLogs = () => {
  ElMessage.success('日志导出成功')
}

const clearLogs = () => {
  ElMessage.warning('日志已清空')
}

const filterLogs = () => {
  ElMessage.info('日志筛选完成')
}

const viewLogDetail = (log) => {
  ElMessage.info(`查看日志详情: ${log.message}`)
}

const getLogLevelType = (level) => {
  const typeMap = {
    'ERROR': 'danger',
    'WARN': 'warning',
    'INFO': 'success',
    'DEBUG': 'info'
  }
  return typeMap[level] || 'info'
}

// 初始化性能监控图表
const initPerformanceChart = () => {
  if (!performanceChart.value) return
  
  const chart = echarts.init(performanceChart.value)
  const option = {
    title: {
      text: '系统性能趋势',
      left: 'center',
      textStyle: {
        fontSize: 14
      }
    },
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: ['CPU使用率', '内存使用率', '磁盘使用率'],
      bottom: 0
    },
    xAxis: {
      type: 'category',
      data: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00']
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: {
        formatter: '{value}%'
      }
    },
    series: [
      {
        name: 'CPU使用率',
        type: 'line',
        data: [20, 25, 30, 45, 40, 35, 30],
        smooth: true,
        itemStyle: { color: '#409EFF' }
      },
      {
        name: '内存使用率',
        type: 'line',
        data: [50, 55, 60, 68, 65, 62, 58],
        smooth: true,
        itemStyle: { color: '#67C23A' }
      },
      {
        name: '磁盘使用率',
        type: 'line',
        data: [25, 28, 30, 32, 31, 30, 29],
        smooth: true,
        itemStyle: { color: '#E6A23C' }
      }
    ]
  }
  
  chart.setOption(option)
  
  // 响应式调整
  window.addEventListener('resize', () => {
    chart.resize()
  })
}

// 组件挂载
onMounted(() => {
  console.log('系统设置页面已加载')
})
import { Setting, Refresh } from '@element-plus/icons-vue'

const refreshData = () => {
  ElMessage.success('系统数据已刷新')
}
</script>

<style scoped>
.system-settings {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.page-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-description {
  margin: 8px 0 0 0;
  opacity: 0.9;
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.function-nav {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.analysis-card {
  border-radius: 8px;
  border: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.analysis-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  color: #303133;
}

.config-management {
  padding: 10px 0;
}

.config-actions {
  padding: 10px 0;
}

.permission-management {
  padding: 10px 0;
}

.permission-modules {
  padding: 10px 0;
  max-height: 400px;
  overflow-y: auto;
}

.permission-node {
  display: flex;
  align-items: center;
  gap: 8px;
}

.permission-stats {
  padding: 20px 0;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
}

.stat-item:last-child {
  border-bottom: none;
}

.stat-label {
  font-size: 14px;
  color: #606266;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.stat-change {
  font-size: 12px;
  font-weight: 500;
}

.stat-change.positive {
  color: #67c23a;
}

.stat-change.negative {
  color: #f56c6c;
}

.metric-card {
  border-radius: 8px;
  border: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.metric-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.metric-content {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 10px 0;
}

.metric-icon {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: white;
}

.metric-icon.cpu {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.metric-icon.memory {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.metric-icon.disk {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.metric-icon.network {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
}

.metric-info {
  flex: 1;
}

.metric-label {
  font-size: 14px;
  color: #606266;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 2px;
}

.metric-change {
  font-size: 12px;
  font-weight: 500;
}

.chart-container {
  padding: 10px 0;
}

.chart {
  width: 100%;
  height: 300px;
}

.service-status {
  padding: 10px 0;
}

.service-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
}

.service-item:last-child {
  border-bottom: none;
}

.service-name {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
}

.service-status-value {
  margin: 0 10px;
}

.service-uptime {
  font-size: 12px;
  color: #909399;
}

.logs-management {
  padding: 10px 0;
}

.log-filters {
  padding: 15px 0;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 20px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .system-settings {
    padding: 10px;
  }
  
  .page-header {
    padding: 15px;
  }
  
  .page-title {
    font-size: 20px;
  }
  
  .header-actions {
    flex-direction: column;
    gap: 5px;
  }
  
  .metric-content {
    flex-direction: column;
    text-align: center;
    gap: 10px;
  }
  
  .service-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 5px;
  }
}
</style>
