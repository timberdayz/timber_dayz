<template>
  <div class="human-resources">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          👥 人力管理
        </h1>
        <p class="page-subtitle">提升团队效率，优化人力资源配置</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="refreshData">
          🔄 刷新数据
        </el-button>
      </div>
    </div>

    <!-- 功能导航区域 -->
    <div class="function-nav">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="👥 员工管理" name="employees">
          <!-- 员工管理内容 -->
          <div class="employees-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>员工信息管理</span>
                      <div class="header-actions">
                        <el-button type="primary" @click="addEmployee">
                          <el-icon><Plus /></el-icon>
                          添加员工
                        </el-button>
                        <el-button type="success" @click="importEmployees">
                          <el-icon><Upload /></el-icon>
                          批量导入
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="employee-management">
                    <!-- 搜索和筛选 -->
                    <div class="search-filters">
                      <el-row :gutter="20">
                        <el-col :span="6">
                          <el-input v-model="searchKeyword" placeholder="搜索员工姓名/工号" clearable>
                            <template #prefix>
                              <el-icon><Search /></el-icon>
                            </template>
                          </el-input>
                        </el-col>
                        <el-col :span="4">
                          <el-select v-model="departmentFilter" placeholder="选择部门" clearable>
                            <el-option label="全部部门" value=""></el-option>
                            <el-option label="销售部" value="sales"></el-option>
                            <el-option label="运营部" value="operations"></el-option>
                            <el-option label="技术部" value="tech"></el-option>
                            <el-option label="财务部" value="finance"></el-option>
                          </el-select>
                        </el-col>
                        <el-col :span="4">
                          <el-select v-model="statusFilter" placeholder="选择状态" clearable>
                            <el-option label="全部状态" value=""></el-option>
                            <el-option label="在职" value="active"></el-option>
                            <el-option label="离职" value="inactive"></el-option>
                            <el-option label="试用期" value="probation"></el-option>
                          </el-select>
                        </el-col>
                        <el-col :span="4">
                          <el-button type="primary" @click="searchEmployees">搜索</el-button>
                        </el-col>
                      </el-row>
                    </div>

                    <!-- 员工表格 -->
                    <el-table :data="filteredEmployees" style="width: 100%; margin-top: 20px;">
                      <el-table-column prop="avatar" label="头像" width="80">
                        <template #default="scope">
                          <el-avatar :size="40" :src="scope.row.avatar">
                            {{ scope.row.name.charAt(0) }}
                          </el-avatar>
                        </template>
                      </el-table-column>
                      <el-table-column prop="name" label="姓名" width="120"></el-table-column>
                      <el-table-column prop="employeeId" label="工号" width="100"></el-table-column>
                      <el-table-column prop="department" label="部门" width="120"></el-table-column>
                      <el-table-column prop="position" label="职位" width="120"></el-table-column>
                      <el-table-column prop="phone" label="电话" width="130"></el-table-column>
                      <el-table-column prop="email" label="邮箱" width="180"></el-table-column>
                      <el-table-column prop="joinDate" label="入职日期" width="120"></el-table-column>
                      <el-table-column prop="status" label="状态" width="100">
                        <template #default="scope">
                          <el-tag :type="getStatusType(scope.row.status)">
                            {{ scope.row.status }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column label="操作" width="200">
                        <template #default="scope">
                          <el-button type="primary" size="small" @click="editEmployee(scope.row)">
                            编辑
                          </el-button>
                          <el-button type="info" size="small" @click="viewEmployeeDetail(scope.row)">
                            详情
                          </el-button>
                          <el-button type="danger" size="small" @click="deleteEmployee(scope.row)">
                            删除
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

        <el-tab-pane label="📊 绩效管理" name="performance">
          <!-- 绩效管理内容 -->
          <div class="performance-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>绩效考核管理</span>
                      <div class="header-actions">
                        <el-button type="primary" @click="createPerformanceReview">
                          <el-icon><Plus /></el-icon>
                          创建考核
                        </el-button>
                        <el-select v-model="performancePeriod" placeholder="选择考核周期">
                          <el-option label="月度考核" value="monthly"></el-option>
                          <el-option label="季度考核" value="quarterly"></el-option>
                          <el-option label="年度考核" value="yearly"></el-option>
                        </el-select>
                      </div>
                    </div>
                  </template>
                  <div class="performance-management">
                    <el-table :data="performanceData" style="width: 100%;">
                      <el-table-column prop="employee" label="员工" width="150"></el-table-column>
                      <el-table-column prop="department" label="部门" width="120"></el-table-column>
                      <el-table-column prop="position" label="职位" width="120"></el-table-column>
                      <el-table-column prop="kpiScore" label="KPI得分" width="100">
                        <template #default="scope">
                          <el-progress :percentage="scope.row.kpiScore" :color="getScoreColor(scope.row.kpiScore)"></el-progress>
                        </template>
                      </el-table-column>
                      <el-table-column prop="behaviorScore" label="行为得分" width="100">
                        <template #default="scope">
                          <el-progress :percentage="scope.row.behaviorScore" :color="getScoreColor(scope.row.behaviorScore)"></el-progress>
                        </template>
                      </el-table-column>
                      <el-table-column prop="totalScore" label="总分" width="100">
                        <template #default="scope">
                          <span :class="getScoreClass(scope.row.totalScore)">{{ scope.row.totalScore }}</span>
                        </template>
                      </el-table-column>
                      <el-table-column prop="level" label="等级" width="100">
                        <template #default="scope">
                          <el-tag :type="getLevelType(scope.row.level)">
                            {{ scope.row.level }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column prop="reviewDate" label="考核日期" width="120"></el-table-column>
                      <el-table-column label="操作" width="150">
                        <template #default="scope">
                          <el-button type="primary" size="small" @click="viewPerformanceDetail(scope.row)">
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
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>绩效分布统计</span>
                    </div>
                  </template>
                  <div class="chart-container">
                    <div ref="performanceDistributionChart" class="chart"></div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>部门绩效对比</span>
                    </div>
                  </template>
                  <div class="chart-container">
                    <div ref="departmentPerformanceChart" class="chart"></div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="⏰ 考勤管理" name="attendance">
          <!-- 考勤管理内容 -->
          <div class="attendance-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>考勤记录管理</span>
                      <div class="header-actions">
                        <el-date-picker v-model="attendanceDate" type="date" placeholder="选择日期"></el-date-picker>
                        <el-button type="primary" @click="exportAttendance">
                          <el-icon><Download /></el-icon>
                          导出考勤
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="attendance-management">
                    <el-table :data="attendanceData" style="width: 100%;">
                      <el-table-column prop="employee" label="员工" width="150"></el-table-column>
                      <el-table-column prop="date" label="日期" width="120"></el-table-column>
                      <el-table-column prop="checkIn" label="上班时间" width="120"></el-table-column>
                      <el-table-column prop="checkOut" label="下班时间" width="120"></el-table-column>
                      <el-table-column prop="workHours" label="工作时长" width="100"></el-table-column>
                      <el-table-column prop="overtimeHours" label="加班时长" width="100"></el-table-column>
                      <el-table-column prop="status" label="状态" width="100">
                        <template #default="scope">
                          <el-tag :type="getAttendanceStatusType(scope.row.status)">
                            {{ scope.row.status }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column label="操作" width="150">
                        <template #default="scope">
                          <el-button type="primary" size="small" @click="editAttendance(scope.row)">
                            编辑
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
                      <span>考勤统计</span>
                    </div>
                  </template>
                  <div class="attendance-stats">
                    <div class="stat-item">
                      <div class="stat-label">正常出勤</div>
                      <div class="stat-value">85%</div>
                      <div class="stat-change positive">+2.3%</div>
                    </div>
                    <div class="stat-item">
                      <div class="stat-label">迟到次数</div>
                      <div class="stat-value">12次</div>
                      <div class="stat-change negative">-3次</div>
                    </div>
                    <div class="stat-item">
                      <div class="stat-label">请假天数</div>
                      <div class="stat-value">5.5天</div>
                      <div class="stat-change positive">-1.2天</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="8">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>加班统计</span>
                    </div>
                  </template>
                  <div class="overtime-stats">
                    <div class="overtime-item">
                      <div class="overtime-label">本月加班总时长</div>
                      <div class="overtime-value">156小时</div>
                    </div>
                    <div class="overtime-item">
                      <div class="overtime-label">平均每人加班</div>
                      <div class="overtime-value">8.2小时</div>
                    </div>
                    <div class="overtime-item">
                      <div class="overtime-label">加班费总额</div>
                      <div class="overtime-value">¥12,480</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="8">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>请假统计</span>
                    </div>
                  </template>
                  <div class="leave-stats">
                    <div class="leave-item">
                      <div class="leave-label">年假</div>
                      <div class="leave-value">45天</div>
                      <div class="leave-used">已用: 32天</div>
                    </div>
                    <div class="leave-item">
                      <div class="leave-label">病假</div>
                      <div class="leave-value">8天</div>
                      <div class="leave-used">已用: 5天</div>
                    </div>
                    <div class="leave-item">
                      <div class="leave-label">事假</div>
                      <div class="leave-value">15天</div>
                      <div class="leave-used">已用: 12天</div>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="💰 薪资管理" name="salary">
          <!-- 薪资管理内容 -->
          <div class="salary-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>薪资管理</span>
                      <div class="header-actions">
                        <el-button type="primary" @click="calculateSalary">
                          <el-icon><Calculator /></el-icon>
                          计算薪资
                        </el-button>
                        <el-button type="success" @click="generatePayroll">
                          <el-icon><Document /></el-icon>
                          生成工资单
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="salary-management">
                    <el-table :data="salaryData" style="width: 100%;">
                      <el-table-column prop="employee" label="员工" width="150"></el-table-column>
                      <el-table-column prop="department" label="部门" width="120"></el-table-column>
                      <el-table-column prop="baseSalary" label="基本工资" width="120"></el-table-column>
                      <el-table-column prop="performanceBonus" label="绩效奖金" width="120"></el-table-column>
                      <el-table-column prop="overtimePay" label="加班费" width="120"></el-table-column>
                      <el-table-column prop="allowances" label="津贴" width="120"></el-table-column>
                      <el-table-column prop="deductions" label="扣除" width="120"></el-table-column>
                      <el-table-column prop="netSalary" label="实发工资" width="120">
                        <template #default="scope">
                          <span class="net-salary">{{ scope.row.netSalary }}</span>
                        </template>
                      </el-table-column>
                      <el-table-column prop="payDate" label="发薪日期" width="120"></el-table-column>
                      <el-table-column label="操作" width="150">
                        <template #default="scope">
                          <el-button type="primary" size="small" @click="viewSalaryDetail(scope.row)">
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
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>薪资结构分析</span>
                    </div>
                  </template>
                  <div class="chart-container">
                    <div ref="salaryStructureChart" class="chart"></div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>部门薪资对比</span>
                    </div>
                  </template>
                  <div class="chart-container">
                    <div ref="departmentSalaryChart" class="chart"></div>
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
// 图标已通过main.js全局注册

// 响应式数据
const activeTab = ref('employees')
const searchKeyword = ref('')
const departmentFilter = ref('')
const statusFilter = ref('')
const performancePeriod = ref('monthly')
const attendanceDate = ref('')

// 员工数据
const employees = ref([
  {
    id: 1,
    name: '张三',
    employeeId: 'EMP001',
    department: '销售部',
    position: '销售经理',
    phone: '13800138001',
    email: 'zhangsan@xihong-erp.com',
    joinDate: '2023-01-15',
    status: '在职',
    avatar: ''
  },
  {
    id: 2,
    name: '李四',
    employeeId: 'EMP002',
    department: '运营部',
    position: '运营专员',
    phone: '13800138002',
    email: 'lisi@xihong-erp.com',
    joinDate: '2023-03-20',
    status: '在职',
    avatar: ''
  },
  {
    id: 3,
    name: '王五',
    employeeId: 'EMP003',
    department: '技术部',
    position: '前端开发',
    phone: '13800138003',
    email: 'wangwu@xihong-erp.com',
    joinDate: '2023-05-10',
    status: '试用期',
    avatar: ''
  },
  {
    id: 4,
    name: '赵六',
    employeeId: 'EMP004',
    department: '财务部',
    position: '会计',
    phone: '13800138004',
    email: 'zhaoliu@xihong-erp.com',
    joinDate: '2022-12-01',
    status: '在职',
    avatar: ''
  }
])

// 绩效数据
const performanceData = ref([
  {
    employee: '张三',
    department: '销售部',
    position: '销售经理',
    kpiScore: 85,
    behaviorScore: 90,
    totalScore: 87,
    level: '优秀',
    reviewDate: '2024-01-15'
  },
  {
    employee: '李四',
    department: '运营部',
    position: '运营专员',
    kpiScore: 78,
    behaviorScore: 82,
    totalScore: 80,
    level: '良好',
    reviewDate: '2024-01-15'
  },
  {
    employee: '王五',
    department: '技术部',
    position: '前端开发',
    kpiScore: 92,
    behaviorScore: 88,
    totalScore: 90,
    level: '优秀',
    reviewDate: '2024-01-15'
  },
  {
    employee: '赵六',
    department: '财务部',
    position: '会计',
    kpiScore: 88,
    behaviorScore: 85,
    totalScore: 86,
    level: '优秀',
    reviewDate: '2024-01-15'
  }
])

// 考勤数据
const attendanceData = ref([
  {
    employee: '张三',
    date: '2024-01-15',
    checkIn: '09:00',
    checkOut: '18:00',
    workHours: '8.0',
    overtimeHours: '1.0',
    status: '正常'
  },
  {
    employee: '李四',
    date: '2024-01-15',
    checkIn: '09:15',
    checkOut: '18:30',
    workHours: '8.5',
    overtimeHours: '1.5',
    status: '迟到'
  },
  {
    employee: '王五',
    date: '2024-01-15',
    checkIn: '08:45',
    checkOut: '19:00',
    workHours: '9.0',
    overtimeHours: '2.0',
    status: '正常'
  },
  {
    employee: '赵六',
    date: '2024-01-15',
    checkIn: '09:00',
    checkOut: '17:30',
    workHours: '7.5',
    overtimeHours: '0',
    status: '早退'
  }
])

// 薪资数据
const salaryData = ref([
  {
    employee: '张三',
    department: '销售部',
    baseSalary: '¥15,000',
    performanceBonus: '¥3,000',
    overtimePay: '¥500',
    allowances: '¥1,000',
    deductions: '¥800',
    netSalary: '¥18,700',
    payDate: '2024-01-31'
  },
  {
    employee: '李四',
    department: '运营部',
    baseSalary: '¥12,000',
    performanceBonus: '¥2,000',
    overtimePay: '¥300',
    allowances: '¥800',
    deductions: '¥600',
    netSalary: '¥14,500',
    payDate: '2024-01-31'
  },
  {
    employee: '王五',
    department: '技术部',
    baseSalary: '¥18,000',
    performanceBonus: '¥4,000',
    overtimePay: '¥800',
    allowances: '¥1,200',
    deductions: '¥1,000',
    netSalary: '¥23,000',
    payDate: '2024-01-31'
  },
  {
    employee: '赵六',
    department: '财务部',
    baseSalary: '¥13,000',
    performanceBonus: '¥2,500',
    overtimePay: '¥200',
    allowances: '¥900',
    deductions: '¥700',
    netSalary: '¥15,900',
    payDate: '2024-01-31'
  }
])

// 计算属性
const filteredEmployees = computed(() => {
  let result = employees.value
  
  if (searchKeyword.value) {
    result = result.filter(emp => 
      emp.name.includes(searchKeyword.value) || 
      emp.employeeId.includes(searchKeyword.value)
    )
  }
  
  if (departmentFilter.value) {
    result = result.filter(emp => emp.department === departmentFilter.value)
  }
  
  if (statusFilter.value) {
    result = result.filter(emp => emp.status === statusFilter.value)
  }
  
  return result
})

// 方法
const refreshData = () => {
  ElMessage.success('人力数据已刷新')
}

const handleTabChange = (tabName) => {
  ElMessage.info(`切换到${tabName}标签页`)
}

const addEmployee = () => {
  ElMessage.info('添加员工功能开发中...')
}

const importEmployees = () => {
  ElMessage.info('批量导入员工功能开发中...')
}

const searchEmployees = () => {
  ElMessage.info('搜索员工功能开发中...')
}

const editEmployee = (row) => {
  ElMessage.info(`编辑员工: ${row.name}`)
}

const viewEmployeeDetail = (row) => {
  ElMessage.info(`查看员工详情: ${row.name}`)
}

const deleteEmployee = (row) => {
  ElMessage.info(`删除员工: ${row.name}`)
}

const createPerformanceReview = () => {
  ElMessage.info('创建绩效考核功能开发中...')
}

const viewPerformanceDetail = (row) => {
  ElMessage.info(`查看绩效详情: ${row.employee}`)
}

const exportAttendance = () => {
  ElMessage.info('导出考勤功能开发中...')
}

const editAttendance = (row) => {
  ElMessage.info(`编辑考勤: ${row.employee}`)
}

const calculateSalary = () => {
  ElMessage.info('计算薪资功能开发中...')
}

const generatePayroll = () => {
  ElMessage.info('生成工资单功能开发中...')
}

const viewSalaryDetail = (row) => {
  ElMessage.info(`查看薪资详情: ${row.employee}`)
}

const getStatusType = (status) => {
  const statusMap = {
    '在职': 'success',
    '离职': 'danger',
    '试用期': 'warning'
  }
  return statusMap[status] || 'info'
}

const getScoreColor = (score) => {
  if (score >= 90) return '#67C23A'
  if (score >= 80) return '#E6A23C'
  if (score >= 70) return '#F56C6C'
  return '#909399'
}

const getScoreClass = (score) => {
  if (score >= 90) return 'score-excellent'
  if (score >= 80) return 'score-good'
  if (score >= 70) return 'score-average'
  return 'score-poor'
}

const getLevelType = (level) => {
  const levelMap = {
    '优秀': 'success',
    '良好': 'primary',
    '一般': 'warning',
    '待改进': 'danger'
  }
  return levelMap[level] || 'info'
}

const getAttendanceStatusType = (status) => {
  const statusMap = {
    '正常': 'success',
    '迟到': 'warning',
    '早退': 'warning',
    '缺勤': 'danger'
  }
  return statusMap[status] || 'info'
}
</script>

<style scoped>
.human-resources {
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
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
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
