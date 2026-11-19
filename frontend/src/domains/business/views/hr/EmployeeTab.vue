<template>
  <div class="employee-tab">
    <el-card class="analysis-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>员工信息管理</span>
          <div class="header-actions">
            <el-button type="primary" @click="showEmployeeDialog()">
              <el-icon><Plus /></el-icon>
              添加员工
            </el-button>
          </div>
        </div>
      </template>

      <div class="employee-management">
        <!-- 搜索和筛选 -->
        <div class="search-filters">
          <el-row :gutter="20">
            <el-col :span="6">
              <el-input
                v-model="searchKeyword"
                placeholder="搜索员工姓名/工号"
                clearable
                @keyup.enter="applyFilters"
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
            </el-col>
            <el-col :span="4">
              <el-select
                v-model="departmentFilter"
                placeholder="选择部门"
                clearable
                @change="applyFilters"
              >
                <el-option label="全部部门" value="" />
                <el-option
                  v-for="dept in departments"
                  :key="dept.id"
                  :label="dept.department_name"
                  :value="dept.id"
                />
              </el-select>
            </el-col>
            <el-col :span="4">
              <el-select
                v-model="statusFilter"
                placeholder="选择状态"
                clearable
                @change="handleStatusFilterChange"
              >
                <el-option label="全部状态" value="" />
                <el-option
                  v-for="option in statusOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-col>
            <el-col :span="4">
              <el-select
                v-model="identityFilter"
                placeholder="选择身份"
                @change="applyFilters"
              >
                <el-option label="全部身份" value="" />
                <el-option
                  v-for="option in identityOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-col>
            <el-col :span="6">
              <div class="filter-actions">
                <el-switch
                  v-model="showInactive"
                  active-text="显示已离职"
                  @change="handleShowInactiveChange"
                />
                <el-button @click="resetFilters">重置</el-button>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 员工统计 -->
        <div class="employee-stats">
          <el-row :gutter="16">
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-icon active">
                  <el-icon><User /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-value">{{ employeeStats.active }}</div>
                  <div class="stat-label">在职员工</div>
                </div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-icon probation">
                  <el-icon><Clock /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-value">{{ employeeStats.probation }}</div>
                  <div class="stat-label">试用期</div>
                </div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-icon inactive">
                  <el-icon><CircleClose /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-value">{{ employeeStats.inactive }}</div>
                  <div class="stat-label">已离职</div>
                </div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-icon total">
                  <el-icon><DataLine /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-value">{{ employeeStats.total }}</div>
                  <div class="stat-label">员工总数</div>
                </div>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 员工表格 -->
        <el-table
          :data="pagedEmployees"
          style="width: 100%; margin-top: 20px"
          v-loading="loadingEmployees"
          stripe
        >
          <el-table-column prop="avatar_url" label="头像" width="70">
            <template #default="scope">
              <el-avatar :size="40" :src="scope.row.avatar_url">
                {{ scope.row.name?.charAt(0) || "?" }}
              </el-avatar>
            </template>
          </el-table-column>
          <el-table-column prop="employee_code" label="工号" width="100" />
          <el-table-column prop="name" label="姓名" width="100" />
          <el-table-column label="登录账号" width="120">
            <template #default="scope">
              {{ scope.row.username || '待注册' }}
            </template>
          </el-table-column>
          <el-table-column label="身份" width="100">
            <template #default="scope">
              <el-tag
                size="small"
                :type="isVisitorRow(scope.row) ? 'info' : 'primary'"
              >
                {{ employeeIdentityLabel(scope.row.employee_identity_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="部门" width="120">
            <template #default="scope">
              {{ getDepartmentName(scope.row.department_id) }}
            </template>
          </el-table-column>
          <el-table-column label="职位" width="120">
            <template #default="scope">
              {{ getPositionName(scope.row.position_id) }}
            </template>
          </el-table-column>
          <el-table-column prop="phone" label="电话" width="130" />
          <el-table-column prop="email" label="邮箱" width="180" show-overflow-tooltip />
          <el-table-column prop="hire_date" label="入职日期" width="110" />
          <el-table-column label="最后发薪月" width="110">
            <template #default="scope">
              {{ scope.row.last_payroll_month || '—' }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="90">
            <template #default="scope">
              <el-tag
                :type="employeeStatusTagType(scope.row.status)"
                size="small"
              >
                {{ employeeStatusLabel(scope.row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="scope">
              <el-button
                type="primary"
                size="small"
                @click="showEmployeeDialog(scope.row)"
              >
                编辑
              </el-button>
              <el-button
                type="info"
                size="small"
                @click="viewEmployeeDetail(scope.row)"
              >
                详情
              </el-button>
              <el-dropdown trigger="click" @command="handleRowCommand($event, scope.row)">
                <el-button size="small" type="warning" plain>
                  更多
                  <el-icon><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="offboard" :disabled="isInactiveRow(scope.row)">
                      办理离职
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="filteredTotal"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="handleSizeChange"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </el-card>

    <!-- 员工表单弹窗 -->
    <el-dialog
      v-model="employeeDialogVisible"
      :title="editingEmployee ? '编辑员工' : '添加员工'"
      width="700px"
      destroy-on-close
    >
      <el-form
        ref="employeeFormRef"
        :model="employeeForm"
        :rules="employeeRules"
        label-width="100px"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="员工编号" prop="employee_code">
              <el-input
                v-model="employeeForm.employee_code"
                :disabled="true"
                :placeholder="editingEmployee ? '' : '保存时自动生成'"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓名" prop="name">
              <el-input v-model="employeeForm.name" placeholder="请输入姓名" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="性别" prop="gender">
              <el-select
                v-model="employeeForm.gender"
                placeholder="选择性别"
                style="width: 100%"
              >
                <el-option label="男" value="male" />
                <el-option label="女" value="female" />
                <el-option label="其他" value="other" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="出生日期" prop="birth_date">
              <el-date-picker
                v-model="employeeForm.birth_date"
                type="date"
                placeholder="选择日期"
                style="width: 100%"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="手机号码" prop="phone">
              <el-input v-model="employeeForm.phone" placeholder="请输入手机号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="employeeForm.email" placeholder="请输入邮箱" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="部门" prop="department_id">
              <el-select
                v-model="employeeForm.department_id"
                placeholder="选择部门"
                style="width: 100%"
              >
                <el-option
                  v-for="dept in departments"
                  :key="dept.id"
                  :label="dept.department_name"
                  :value="dept.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="职位" prop="position_id">
              <el-select
                v-model="employeeForm.position_id"
                placeholder="选择职位"
                style="width: 100%"
              >
                <el-option
                  v-for="pos in positions"
                  :key="pos.id"
                  :label="pos.position_name"
                  :value="pos.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="入职日期" prop="hire_date">
              <el-date-picker
                v-model="employeeForm.hire_date"
                type="date"
                placeholder="选择日期"
                style="width: 100%"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态" prop="status">
              <el-select
                v-model="employeeForm.status"
                placeholder="选择状态"
                style="width: 100%"
              >
                <el-option
                  v-for="option in statusOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="关联登录账号">
          <el-select
            v-model="employeeForm.user_id"
            placeholder="请选择关联登录账号（可清空解除关联）"
            clearable
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="u in linkedUserOptions"
              :key="u.id"
              :label="formatLinkedUserOption(u)"
              :value="u.id"
            />
          </el-select>
          <div v-if="occupiedByDepartedCount > 0" class="account-hint">
            有 {{ occupiedByDepartedCount }} 个账号被已离职员工占用，请先解除关联或改派他人
          </div>
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="证件号码" prop="id_number">
              <el-input v-model="employeeForm.id_number" placeholder="身份证号码" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合同类型" prop="contract_type">
              <el-select
                v-model="employeeForm.contract_type"
                placeholder="选择合同类型"
                style="width: 100%"
              >
                <el-option label="固定期限" value="fixed_term" />
                <el-option label="无固定期限" value="indefinite" />
                <el-option label="实习" value="internship" />
                <el-option label="兼职" value="part_time" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="现居地址" prop="address">
          <el-input
            v-model="employeeForm.address"
            type="textarea"
            :rows="2"
            placeholder="请输入地址"
          />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="紧急联系人" prop="emergency_contact">
              <el-input v-model="employeeForm.emergency_contact" placeholder="紧急联系人姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="紧急电话" prop="emergency_phone">
              <el-input v-model="employeeForm.emergency_phone" placeholder="紧急联系人电话" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="employeeDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEmployee" :loading="savingEmployee">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 员工详情弹窗 -->
    <el-dialog v-model="employeeDetailVisible" title="员工详情" width="600px">
      <el-descriptions :column="2" border v-if="selectedEmployee">
        <el-descriptions-item label="员工编号">
          {{ selectedEmployee.employee_code }}
        </el-descriptions-item>
        <el-descriptions-item label="姓名">
          {{ selectedEmployee.name }}
        </el-descriptions-item>
        <el-descriptions-item label="性别">
          {{ getGenderLabel(selectedEmployee.gender) }}
        </el-descriptions-item>
        <el-descriptions-item label="出生日期">
          {{ selectedEmployee.birth_date || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="手机号码">
          {{ selectedEmployee.phone || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="邮箱">
          {{ selectedEmployee.email || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="身份">
          <el-tag size="small" :type="isVisitorRow(selectedEmployee) ? 'info' : 'primary'">
            {{ employeeIdentityLabel(selectedEmployee.employee_identity_type) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="部门">
          {{ getDepartmentName(selectedEmployee.department_id) }}
        </el-descriptions-item>
        <el-descriptions-item label="职位">
          {{ getPositionName(selectedEmployee.position_id) }}
        </el-descriptions-item>
        <el-descriptions-item label="入职日期">
          {{ selectedEmployee.hire_date || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="离职日期">
          {{ selectedEmployee.leave_date || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="最后发薪月">
          {{ selectedEmployee.last_payroll_month || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="employeeStatusTagType(selectedEmployee.status)" size="small">
            {{ employeeStatusLabel(selectedEmployee.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="合同类型">
          {{ getContractTypeLabel(selectedEmployee.contract_type) }}
        </el-descriptions-item>
        <el-descriptions-item label="证件号码">
          {{ selectedEmployee.id_number || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="现居地址" :span="2">
          {{ selectedEmployee.address || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="紧急联系人">
          {{ selectedEmployee.emergency_contact || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="紧急电话">
          {{ selectedEmployee.emergency_phone || "-" }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 办理离职弹窗 -->
    <el-dialog
      v-model="offboardDialogVisible"
      title="办理离职"
      width="520px"
      destroy-on-close
    >
      <el-alert
        title="办理离职不会删除历史数据：工资单、绩效、提成与店铺归属记录全部保留，只把员工状态置为已离职并锁定发薪边界。"
        type="info"
        :closable="false"
        style="margin-bottom: 16px"
      />
      <el-form ref="offboardFormRef" :model="offboardForm" :rules="offboardRules" label-width="110px">
        <el-form-item label="员工">
          <span>{{ offboardTargetName }}</span>
        </el-form-item>
        <el-form-item label="离职日期" prop="leave_date">
          <el-date-picker
            v-model="offboardForm.leave_date"
            type="date"
            placeholder="选择离职日期"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="最后发薪月" prop="last_payroll_month">
          <el-date-picker
            v-model="offboardForm.last_payroll_month"
            type="month"
            placeholder="选择最后发薪月"
            value-format="YYYY-MM"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="离职原因" prop="leave_reason">
          <el-input
            v-model="offboardForm.leave_reason"
            type="textarea"
            :rows="3"
            placeholder="选填，例如：个人原因"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="offboardDialogVisible = false">取消</el-button>
        <el-button type="warning" @click="submitOffboard" :loading="submittingOffboard">
          确认办理离职
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowDown,
  CircleClose,
  Clock,
  DataLine,
  Plus,
  Search,
  User
} from '@element-plus/icons-vue'
import api from '@/api'
import usersApi from '@/api/users'
import {
  EMPLOYEE_IDENTITY,
  EMPLOYEE_IDENTITY_LABEL,
  EMPLOYEE_STATUS,
  EMPLOYEE_STATUS_LABEL,
  employeeIdentityLabel,
  employeeStatusLabel,
  employeeStatusTagType,
  isInactiveEmployeeStatus
} from '@/constants/hr'

const props = defineProps({
  // 办理离职动作由父页面统一执行（页面级刷新与提示集中在一处），子组件只负责收集表单。
  offboardHandler: {
    type: Function,
    default: null
  }
})

// ============================================================================
// 响应式数据
// ============================================================================

const allEmployees = ref([])
const loadingEmployees = ref(false)
const searchKeyword = ref('')
const departmentFilter = ref('')
const statusFilter = ref('')
// 默认只看正式员工：访客档案单独筛出来看，不混在员工列表里。
const identityFilter = ref(EMPLOYEE_IDENTITY.EMPLOYEE)
// 默认不显示已离职员工。
const showInactive = ref(false)

const departments = ref([])
const positions = ref([])
const linkedUserOptions = ref([])
/** 被已离职员工占着的账号数量（后端顶层字段 ``occupied_by_departed_employee``）。 */
const occupiedByDepartedCount = ref(0)

const pagination = reactive({
  page: 1,
  pageSize: 20
})

const employeeStats = reactive({
  active: 0,
  probation: 0,
  inactive: 0,
  leave: 0,
  total: 0
})

// 弹窗控制
const employeeDialogVisible = ref(false)
const employeeDetailVisible = ref(false)
const offboardDialogVisible = ref(false)

// 编辑状态
const editingEmployee = ref(null)
const selectedEmployee = ref(null)
const offboardTarget = ref(null)

// 表单数据
const employeeForm = reactive({
  employee_code: '',
  name: '',
  gender: '',
  birth_date: '',
  phone: '',
  email: '',
  department_id: null,
  position_id: null,
  hire_date: '',
  status: EMPLOYEE_STATUS.ACTIVE,
  user_id: null,
  id_number: '',
  contract_type: '',
  address: '',
  emergency_contact: '',
  emergency_phone: ''
})

const offboardForm = reactive({
  leave_date: '',
  last_payroll_month: '',
  leave_reason: ''
})

// 保存状态
const savingEmployee = ref(false)
const submittingOffboard = ref(false)

// 表单引用
const employeeFormRef = ref(null)
const offboardFormRef = ref(null)

// 表单验证规则
const employeeRules = {
  employee_code: [{ required: false }],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }]
}

const offboardRules = {
  leave_date: [{ required: true, message: '请选择离职日期', trigger: 'change' }],
  last_payroll_month: [
    { required: true, message: '请选择最后发薪月', trigger: 'change' }
  ]
}

// ============================================================================
// 计算属性
// ============================================================================

const statusOptions = computed(() =>
  Object.entries(EMPLOYEE_STATUS_LABEL).map(([value, label]) => ({ value, label }))
)

const identityOptions = computed(() =>
  Object.entries(EMPLOYEE_IDENTITY_LABEL).map(([value, label]) => ({ value, label }))
)

/**
 * 员工列表过滤：关键词 / 部门 / 状态 / 身份。
 * 「显示已离职」开关关闭时，已离职员工不出现在列表里。
 */
const filteredEmployees = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  return (allEmployees.value || []).filter((row) => {
    if (!row) return false
    const matchesKeyword =
      !keyword ||
      `${row.name || ''}${row.employee_code || ''}`.toLowerCase().includes(keyword)
    const matchesDepartment =
      !departmentFilter.value || row.department_id === departmentFilter.value
    const matchesStatusFilter =
      !statusFilter.value || row.status === statusFilter.value
    const matchesIdentity =
      !identityFilter.value ||
      (row.employee_identity_type || EMPLOYEE_IDENTITY.EMPLOYEE) === identityFilter.value
    const matchesInactive =
      showInactive.value || !isInactiveEmployeeStatus(row.status)
    return (
      matchesKeyword &&
      matchesDepartment &&
      matchesStatusFilter &&
      matchesIdentity &&
      matchesInactive
    )
  })
})

const filteredTotal = computed(() => filteredEmployees.value.length)

const pagedEmployees = computed(() => {
  const start = (pagination.page - 1) * pagination.pageSize
  return filteredEmployees.value.slice(start, start + pagination.pageSize)
})

const offboardTargetName = computed(() => {
  const target = offboardTarget.value
  if (!target) return ''
  return `${target.name || ''}（${target.employee_code || ''}）`
})

// ============================================================================
// 生命周期
// ============================================================================

onMounted(async () => {
  await Promise.all([loadDepartments(), loadPositions(), loadEmployees()])
})

// 过滤条件变化后回到第一页，避免停在一个空页上
watch(
  [searchKeyword, departmentFilter, statusFilter, identityFilter, showInactive],
  () => {
    pagination.page = 1
  }
)

// ============================================================================
// 数据加载
// ============================================================================

const loadDepartments = async () => {
  try {
    const data = await api.getHrDepartments({ status: 'active' })
    departments.value = data || []
  } catch (error) {
    console.error('加载部门列表失败:', error)
    departments.value = []
  }
}

const loadPositions = async () => {
  try {
    const data = await api.getHrPositions({ status: 'active' })
    positions.value = data || []
  } catch (error) {
    console.error('加载职位列表失败:', error)
    positions.value = []
  }
}

/**
 * 员工档案一次性取回（上限 500 条），过滤与分页在前端做：
 * 「显示已离职」「身份」这类组合筛选没法用一个后端参数表达，
 * 若在后端分页再前端过滤，会出现空页与总数不一致。
 */
const loadEmployees = async () => {
  loadingEmployees.value = true
  try {
    const data = await api.getHrEmployees({ page: 1, page_size: 500 })
    allEmployees.value = data || []
    await loadEmployeeStats()
  } catch (error) {
    console.error('加载员工列表失败:', error)
    allEmployees.value = []
  } finally {
    loadingEmployees.value = false
  }
}

const loadEmployeeStats = async () => {
  try {
    const [activeRes, probationRes, inactiveRes, leaveRes] = await Promise.all([
      api.getHrEmployeeCount(EMPLOYEE_STATUS.ACTIVE),
      api.getHrEmployeeCount(EMPLOYEE_STATUS.PROBATION),
      api.getHrEmployeeCount(EMPLOYEE_STATUS.INACTIVE),
      api.getHrEmployeeCount(EMPLOYEE_STATUS.LEAVE)
    ])
    employeeStats.active = activeRes?.count || 0
    employeeStats.probation = probationRes?.count || 0
    employeeStats.inactive = inactiveRes?.count || 0
    employeeStats.leave = leaveRes?.count || 0
    employeeStats.total =
      employeeStats.active +
      employeeStats.probation +
      employeeStats.leave +
      employeeStats.inactive
  } catch (error) {
    console.error('加载员工统计失败:', error)
  }
}

// ============================================================================
// 筛选与分页
// ============================================================================

const applyFilters = () => {
  pagination.page = 1
}

const handleSizeChange = (size) => {
  pagination.pageSize = size
  pagination.page = 1
}

const handlePageChange = (page) => {
  pagination.page = page
}

/** 选中「已离职」时自动打开「显示已离职」，两个口径保持一致 */
const handleStatusFilterChange = (value) => {
  if (value === EMPLOYEE_STATUS.INACTIVE) {
    showInactive.value = true
  }
}

/** 关闭「显示已离职」时，如果状态筛选正好是「已离职」，一并清掉 */
const handleShowInactiveChange = (value) => {
  if (!value && statusFilter.value === EMPLOYEE_STATUS.INACTIVE) {
    statusFilter.value = ''
  }
}

const resetFilters = () => {
  searchKeyword.value = ''
  departmentFilter.value = ''
  statusFilter.value = ''
  identityFilter.value = EMPLOYEE_IDENTITY.EMPLOYEE
  showInactive.value = false
  pagination.page = 1
}

// ============================================================================
// 员工操作
// ============================================================================

const showEmployeeDialog = async (employee = null) => {
  editingEmployee.value = employee
  if (employee) {
    Object.assign(employeeForm, {
      employee_code: employee.employee_code,
      name: employee.name,
      gender: employee.gender || '',
      birth_date: employee.birth_date || '',
      phone: employee.phone || '',
      email: employee.email || '',
      department_id: employee.department_id ?? null,
      position_id: employee.position_id ?? null,
      hire_date: employee.hire_date || '',
      status: employee.status || EMPLOYEE_STATUS.ACTIVE,
      user_id: employee.user_id ?? null,
      id_number: employee.id_number || '',
      contract_type: employee.contract_type || '',
      address: employee.address || '',
      emergency_contact: employee.emergency_contact || '',
      emergency_phone: employee.emergency_phone || ''
    })
  } else {
    Object.assign(employeeForm, {
      employee_code: '',
      name: '',
      gender: '',
      birth_date: '',
      phone: '',
      email: '',
      department_id: null,
      position_id: null,
      hire_date: '',
      status: EMPLOYEE_STATUS.ACTIVE,
      user_id: null,
      id_number: '',
      contract_type: '',
      address: '',
      emergency_contact: '',
      emergency_phone: ''
    })
  }

  await loadLinkedUserOptions(employee)
  employeeDialogVisible.value = true
}

const loadLinkedUserOptions = async (employee) => {
  try {
    const res = await usersApi.getUnlinkedUsers()
    const list = res?.data ?? res
    const arr = Array.isArray(list) ? list : list || []
    linkedUserOptions.value = [...arr]
    // ⚠️ 后端把「被已离职员工占着的账号」放在**顶层** ``occupied_by_departed_employee``，
    // 不在 ``data`` 里 ⇒ 这里单独取一次，给管理员一句明确提示。
    const occupied = res?.occupied_by_departed_employee
    occupiedByDepartedCount.value = Array.isArray(occupied) ? occupied.length : 0
    if (employee?.user_id && employee?.username) {
      const exists = linkedUserOptions.value.some((u) => u.id === employee.user_id)
      if (!exists) {
        linkedUserOptions.value = [
          { id: employee.user_id, username: employee.username, email: '' },
          ...linkedUserOptions.value
        ]
      }
    }
  } catch (error) {
    console.error('加载可关联账号失败:', error)
    linkedUserOptions.value =
      employee?.user_id && employee?.username
        ? [{ id: employee.user_id, username: employee.username, email: '' }]
        : []
  }
}

/**
 * 可关联账号的选项文案：
 * 被离职员工占用的账号会标出来，避免管理员以为这是空闲账号。
 */
const formatLinkedUserOption = (user) => {
  if (!user) return ''
  const base = `${user.username || ''}${user.email ? ' (' + user.email + ')' : ''}`
  const blocker = user.blocked_by_employee
  if (blocker?.employee_code) {
    return `${base}（已被离职员工 ${blocker.employee_code} 占用）`
  }
  return base
}

/** 提交前清洗：空字符串转 null，避免后端 422；创建时不传员工编号由后端自动生成 */
function cleanEmployeePayload(isCreate) {
  const raw = { ...employeeForm }
  const cleaned = {}
  for (const [key, value] of Object.entries(raw)) {
    if (value === '' || value === undefined) {
      cleaned[key] = null
    } else if (typeof value === 'string' && value.trim() === '') {
      cleaned[key] = null
    } else {
      cleaned[key] = value
    }
  }
  if (isCreate) {
    cleaned.employee_code = null
  }
  return cleaned
}

const saveEmployee = async () => {
  if (!employeeFormRef.value) return
  await employeeFormRef.value.validate()

  savingEmployee.value = true
  try {
    if (editingEmployee.value) {
      const payload = cleanEmployeePayload(false)
      await api.updateHrEmployee(payload.employee_code, payload)
      ElMessage.success('员工信息已更新')
    } else {
      const payload = cleanEmployeePayload(true)
      await api.createHrEmployee(payload)
      ElMessage.success('员工已添加')
    }
    employeeDialogVisible.value = false
    await loadEmployees()
  } catch (error) {
    console.error('保存员工失败:', error)
    ElMessage.error(
      error.response?.data?.detail || error.response?.data?.message || error.message || '保存失败'
    )
  } finally {
    savingEmployee.value = false
  }
}

const viewEmployeeDetail = (employee) => {
  selectedEmployee.value = employee
  employeeDetailVisible.value = true
}

// ============================================================================
// 办理离职
// ============================================================================

const isInactiveRow = (row) => isInactiveEmployeeStatus(row?.status)

const isVisitorRow = (row) =>
  (row?.employee_identity_type || EMPLOYEE_IDENTITY.EMPLOYEE) === EMPLOYEE_IDENTITY.VISITOR

const handleRowCommand = (command, row) => {
  if (command === 'offboard') {
    openOffboardDialog(row)
  }
}

const openOffboardDialog = (row) => {
  offboardTarget.value = row
  offboardForm.leave_date = row?.leave_date || ''
  offboardForm.last_payroll_month = row?.last_payroll_month || ''
  offboardForm.leave_reason = ''
  offboardDialogVisible.value = true
}

const submitOffboard = async () => {
  if (!offboardFormRef.value) return
  const valid = await offboardFormRef.value.validate().catch(() => false)
  if (!valid) return

  const target = offboardTarget.value
  if (!target?.employee_code) {
    ElMessage.error('缺少员工编号，无法办理离职')
    return
  }

  submittingOffboard.value = true
  try {
    const payload = {
      leave_date: offboardForm.leave_date || null,
      last_payroll_month: offboardForm.last_payroll_month || null,
      leave_reason: offboardForm.leave_reason?.trim() || null
    }
    if (typeof props.offboardHandler === 'function') {
      await props.offboardHandler({ employeeCode: target.employee_code, payload })
    } else {
      await api.offboardHrEmployee(target.employee_code, payload)
      ElMessage.success('已办理离职')
      await loadEmployees()
    }
    offboardDialogVisible.value = false
  } catch (error) {
    console.error('办理离职失败:', error)
    ElMessage.error(
      error.response?.data?.message ||
        error.response?.data?.detail ||
        error.message ||
        '办理离职失败'
    )
  } finally {
    submittingOffboard.value = false
  }
}

// ============================================================================
// 辅助方法
// ============================================================================

const getDepartmentName = (departmentId) => {
  if (!departmentId) return '-'
  const dept = (departments.value || []).find((d) => d.id === departmentId)
  return dept?.department_name || '-'
}

const getPositionName = (positionId) => {
  if (!positionId) return '-'
  const pos = (positions.value || []).find((p) => p.id === positionId)
  return pos?.position_name || '-'
}

const getGenderLabel = (gender) => {
  const map = { male: '男', female: '女', other: '其他' }
  return map[gender] || '-'
}

const getContractTypeLabel = (type) => {
  const map = {
    fixed_term: '固定期限',
    indefinite: '无固定期限',
    internship: '实习',
    part_time: '兼职'
  }
  return map[type] || '-'
}

// 供父页面在办理离职后刷新列表
defineExpose({ reload: loadEmployees })
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.account-hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 18px;
  color: var(--el-color-warning);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-filters {
  margin-bottom: 16px;
}

.filter-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.employee-stats {
  margin: 20px 0;
}

.stat-card {
  display: flex;
  align-items: center;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16px;
  font-size: 24px;
}

.stat-icon.active {
  background: #e6f7e6;
  color: #52c41a;
}

.stat-icon.probation {
  background: #fff7e6;
  color: #faad14;
}

.stat-icon.inactive {
  background: #fff1f0;
  color: #ff4d4f;
}

.stat-icon.total {
  background: #e6f7ff;
  color: #1890ff;
}

.stat-info .stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #333;
}

.stat-info .stat-label {
  font-size: 14px;
  color: #666;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.analysis-card {
  margin-bottom: 20px;
}
</style>
