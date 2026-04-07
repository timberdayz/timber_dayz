<template>
  <div class="employee-salary-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">员工薪资</h1>
        <p class="page-subtitle">统一维护固定薪资、月度录入和工资单结果</p>
      </div>
      <el-button type="primary" @click="refreshCurrentView" :loading="pageLoading">
        刷新
      </el-button>
    </div>

    <div class="page-layout">
      <el-card class="employee-list-card" shadow="hover">
        <template #header>
          <div class="section-header">
            <span>员工列表</span>
          </div>
        </template>

        <el-input
          v-model="employeeKeyword"
          placeholder="搜索员工姓名/工号"
          clearable
          style="margin-bottom: 12px;"
        />

        <el-select
          v-model="employeeDepartment"
          placeholder="全部部门"
          clearable
          style="width: 100%; margin-bottom: 12px;"
        >
          <el-option label="全部部门" value="" />
          <el-option
            v-for="dept in departments"
            :key="dept.id"
            :label="dept.department_name"
            :value="dept.id"
          />
        </el-select>

        <div class="employee-list" v-loading="loadingEmployees">
          <button
            v-for="employee in filteredEmployees"
            :key="employee.employee_code"
            type="button"
            class="employee-item"
            :class="{ active: selectedEmployee?.employee_code === employee.employee_code }"
            @click="selectEmployee(employee)"
          >
            <div class="employee-name-row">
              <span class="employee-name">{{ employee.name || employee.employee_code }}</span>
              <el-tag size="small" :type="employee.status === 'active' ? 'success' : 'info'">
                {{ employee.status || 'unknown' }}
              </el-tag>
            </div>
            <div class="employee-meta">{{ employee.employee_code }}</div>
            <div class="employee-meta">
              {{ getDepartmentName(employee.department_id) }} / {{ getPositionName(employee.position_id) }}
            </div>
          </button>

          <el-empty v-if="!loadingEmployees && filteredEmployees.length === 0" description="暂无员工" />
        </div>
      </el-card>

      <div class="content-column">
        <el-alert
          v-if="!selectedEmployee"
          title="请先从左侧选择员工"
          type="info"
          :closable="false"
          style="margin-bottom: 16px;"
        />

        <template v-else>
          <el-card class="section-card" shadow="hover">
            <template #header>
              <div class="section-header">
                <span>固定薪资</span>
                <div class="section-actions">
                  <el-button size="small" @click="openNewVersionFromCurrent" :disabled="!selectedEmployee">
                    新建生效版本
                  </el-button>
                  <el-button
                    size="small"
                    type="primary"
                    @click="saveFixedSalary(false)"
                    :loading="savingSalaryStructure"
                    :disabled="!selectedEmployee"
                  >
                    保存固定薪资
                  </el-button>
                </div>
              </div>
            </template>

            <el-alert
              v-if="salaryStructureEmpty"
              title="该员工尚未配置固定薪资，请先录入底薪和岗位工资。"
              type="warning"
              :closable="false"
              style="margin-bottom: 16px;"
            />

            <el-form :model="salaryForm" label-width="120px">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="底薪">
                    <el-input-number v-model="salaryForm.base_salary" :min="0" :step="100" style="width: 100%;" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="岗位工资">
                    <el-input-number v-model="salaryForm.position_salary" :min="0" :step="100" style="width: 100%;" />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="住房补贴">
                    <el-input-number v-model="salaryForm.housing_allowance" :min="0" :step="100" style="width: 100%;" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="交通补贴">
                    <el-input-number v-model="salaryForm.transport_allowance" :min="0" :step="100" style="width: 100%;" />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="餐饮补贴">
                    <el-input-number v-model="salaryForm.meal_allowance" :min="0" :step="100" style="width: 100%;" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="通讯补贴">
                    <el-input-number v-model="salaryForm.communication_allowance" :min="0" :step="100" style="width: 100%;" />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="其他补贴">
                    <el-input-number v-model="salaryForm.other_allowance" :min="0" :step="100" style="width: 100%;" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="绩效比例">
                    <el-input-number v-model="salaryForm.performance_ratio_percent" :min="0" :max="100" :step="1" style="width: 100%;" />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="默认提成比例">
                    <el-input-number v-model="salaryForm.commission_ratio_percent" :min="0" :max="100" :step="1" style="width: 100%;" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="社保基数">
                    <el-input-number v-model="salaryForm.social_insurance_base" :min="0" :step="100" style="width: 100%;" />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="公积金基数">
                    <el-input-number v-model="salaryForm.housing_fund_base" :min="0" :step="100" style="width: 100%;" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="生效日期">
                    <el-date-picker
                      v-model="salaryForm.effective_date"
                      type="date"
                      value-format="YYYY-MM-DD"
                      placeholder="选择生效日期"
                      style="width: 100%;"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>

            <div class="history-section">
              <div class="history-title">历史版本</div>
              <el-table :data="salaryHistory" size="small" max-height="220" border>
                <el-table-column prop="effective_date" label="生效日期" width="120" />
                <el-table-column label="底薪" width="120" align="right">
                  <template #default="{ row }">{{ formatMoney(row.base_salary) }}</template>
                </el-table-column>
                <el-table-column label="岗位工资" width="120" align="right">
                  <template #default="{ row }">{{ formatMoney(row.position_salary) }}</template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="100" />
              </el-table>
            </div>
          </el-card>

          <el-card class="section-card" shadow="hover">
            <template #header>
              <div class="section-header">
                <span>月度录入</span>
                <div class="section-actions">
                  <el-select v-model="selectedMonth" style="width: 140px;" @change="loadPayrollRecord">
                    <el-option
                      v-for="month in recentMonths"
                      :key="month"
                      :label="month"
                      :value="month"
                    />
                  </el-select>
                  <el-button size="small" @click="copyPreviousMonthManualFields" :disabled="!selectedEmployee">
                    复制上月人工项
                  </el-button>
                  <el-button size="small" @click="refreshPayrollResult" :loading="refreshingPayroll" :disabled="!selectedEmployee">
                    按当前配置刷新结果
                  </el-button>
                  <el-button size="small" type="primary" @click="saveMonthlyDraft" :loading="savingPayroll" :disabled="!selectedEmployee">
                    保存月度草稿
                  </el-button>
                </div>
              </div>
            </template>

            <el-form :model="payrollForm" label-width="120px">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="月度奖金">
                    <el-input-number v-model="payrollForm.bonus" :min="0" :step="100" style="width: 100%;" :disabled="isLockedPayroll" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="加班费">
                    <el-input-number v-model="payrollForm.overtime_pay" :min="0" :step="100" style="width: 100%;" :disabled="isLockedPayroll" />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="个人社保">
                    <el-input-number v-model="payrollForm.social_insurance_personal" :min="0" :step="100" style="width: 100%;" :disabled="isLockedPayroll" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="个人公积金">
                    <el-input-number v-model="payrollForm.housing_fund_personal" :min="0" :step="100" style="width: 100%;" :disabled="isLockedPayroll" />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="个税">
                    <el-input-number v-model="payrollForm.income_tax" :min="0" :step="100" style="width: 100%;" :disabled="isLockedPayroll" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="其他扣款">
                    <el-input-number v-model="payrollForm.other_deductions" :min="0" :step="100" style="width: 100%;" :disabled="isLockedPayroll" />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="公司社保">
                    <el-input-number v-model="payrollForm.social_insurance_company" :min="0" :step="100" style="width: 100%;" :disabled="isLockedPayroll" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="公司公积金">
                    <el-input-number v-model="payrollForm.housing_fund_company" :min="0" :step="100" style="width: 100%;" :disabled="isLockedPayroll" />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="发薪日期">
                    <el-date-picker
                      v-model="payrollForm.pay_date"
                      type="date"
                      value-format="YYYY-MM-DD"
                      placeholder="选择日期"
                      style="width: 100%;"
                      :disabled="isLockedPayroll"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="备注">
                    <el-input v-model="payrollForm.remark" :disabled="isLockedPayroll" />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </el-card>

          <el-card class="section-card" shadow="hover">
            <template #header>
              <div class="section-header">
                <span>工资单结果</span>
                <div class="section-actions">
                  <el-tag :type="payrollStatusTagType">{{ payrollRecord?.status || 'draft' }}</el-tag>
                  <el-button size="small" type="success" @click="confirmPayroll" :disabled="!payrollRecord || payrollRecord.status !== 'draft'">
                    确认工资单
                  </el-button>
                  <el-button size="small" type="warning" @click="reopenPayroll" :disabled="!payrollRecord || payrollRecord.status !== 'confirmed'">
                    退回草稿
                  </el-button>
                  <el-button size="small" type="primary" @click="markPayrollPaid" :disabled="!canMarkPaid">
                    标记已发放
                  </el-button>
                </div>
              </div>
            </template>

            <el-row :gutter="16" class="result-grid">
              <el-col :span="8"><div class="result-item"><span>提成</span><strong>{{ formatMoney(payrollRecord?.commission) }}</strong></div></el-col>
              <el-col :span="8"><div class="result-item"><span>绩效工资</span><strong>{{ formatMoney(payrollRecord?.performance_salary) }}</strong></div></el-col>
              <el-col :span="8"><div class="result-item"><span>津贴合计</span><strong>{{ formatMoney(payrollRecord?.allowances) }}</strong></div></el-col>
              <el-col :span="8"><div class="result-item"><span>应发合计</span><strong>{{ formatMoney(payrollRecord?.gross_salary) }}</strong></div></el-col>
              <el-col :span="8"><div class="result-item"><span>扣款合计</span><strong>{{ formatMoney(payrollRecord?.total_deductions) }}</strong></div></el-col>
              <el-col :span="8"><div class="result-item"><span>实发工资</span><strong>{{ formatMoney(payrollRecord?.net_salary) }}</strong></div></el-col>
            </el-row>

            <el-alert
              v-if="lockedConflicts.length > 0"
              title="当前工资单存在锁定冲突，需先退回草稿再接受重算结果。"
              type="warning"
              :closable="false"
              style="margin-top: 16px;"
            />
          </el-card>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import api from '@/api'

const authStore = useAuthStore()

const pageLoading = ref(false)
const loadingEmployees = ref(false)
const savingSalaryStructure = ref(false)
const savingPayroll = ref(false)
const refreshingPayroll = ref(false)

const employees = ref([])
const departments = ref([])
const positions = ref([])
const employeeKeyword = ref('')
const employeeDepartment = ref('')
const selectedEmployee = ref(null)
const selectedMonth = ref('')

const salaryStructureEmpty = ref(true)
const salaryHistory = ref([])
const payrollRecord = ref(null)
const lockedConflicts = ref([])

const salaryForm = reactive({
  base_salary: 0,
  position_salary: 0,
  housing_allowance: 0,
  transport_allowance: 0,
  meal_allowance: 0,
  communication_allowance: 0,
  other_allowance: 0,
  performance_ratio_percent: 0,
  commission_ratio_percent: 0,
  social_insurance_base: 0,
  housing_fund_base: 0,
  effective_date: ''
})

const payrollForm = reactive({
  bonus: 0,
  overtime_pay: 0,
  social_insurance_personal: 0,
  housing_fund_personal: 0,
  income_tax: 0,
  other_deductions: 0,
  social_insurance_company: 0,
  housing_fund_company: 0,
  pay_date: '',
  remark: ''
})

const recentMonths = computed(() => {
  const months = []
  const now = new Date()
  for (let i = 0; i < 12; i += 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }
  return months
})

const filteredEmployees = computed(() => {
  return employees.value.filter((employee) => {
    const keyword = employeeKeyword.value.trim().toLowerCase()
    const matchesKeyword = !keyword || `${employee.name || ''}${employee.employee_code || ''}`.toLowerCase().includes(keyword)
    const matchesDepartment = !employeeDepartment.value || employee.department_id === employeeDepartment.value
    return matchesKeyword && matchesDepartment
  })
})

const isLockedPayroll = computed(() => ['confirmed', 'paid'].includes(payrollRecord.value?.status))
const payrollStatusTagType = computed(() => {
  const status = payrollRecord.value?.status
  if (status === 'paid') return 'success'
  if (status === 'confirmed') return 'warning'
  return 'info'
})
const canMarkPaid = computed(() => {
  const user = authStore.user
  if (!user) return false
  const isAdmin = user.is_superuser || (Array.isArray(user.roles) && user.roles.some((role) => {
    if (typeof role === 'string') return role === 'admin'
    return role?.role_code === 'admin' || role?.role_name === 'admin'
  }))
  return isAdmin && payrollRecord.value?.status === 'confirmed'
})
const previousMonth = computed(() => {
  const index = recentMonths.value.indexOf(selectedMonth.value)
  if (index === -1 || index === recentMonths.value.length - 1) return null
  return recentMonths.value[index + 1]
})

const formatMoney = (value) => {
  if (value == null) return '¥0.00'
  return `¥${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const getDepartmentName = (departmentId) => {
  return departments.value.find((item) => item.id === departmentId)?.department_name || '-'
}

const getPositionName = (positionId) => {
  return positions.value.find((item) => item.id === positionId)?.position_name || '-'
}

const resetSalaryForm = () => {
  Object.assign(salaryForm, {
    base_salary: 0,
    position_salary: 0,
    housing_allowance: 0,
    transport_allowance: 0,
    meal_allowance: 0,
    communication_allowance: 0,
    other_allowance: 0,
    performance_ratio_percent: 0,
    commission_ratio_percent: 0,
    social_insurance_base: 0,
    housing_fund_base: 0,
    effective_date: ''
  })
}

const resetPayrollForm = () => {
  Object.assign(payrollForm, {
    bonus: 0,
    overtime_pay: 0,
    social_insurance_personal: 0,
    housing_fund_personal: 0,
    income_tax: 0,
    other_deductions: 0,
    social_insurance_company: 0,
    housing_fund_company: 0,
    pay_date: '',
    remark: ''
  })
}

const applySalaryStructure = (record) => {
  if (!record) {
    salaryStructureEmpty.value = true
    resetSalaryForm()
    return
  }
  salaryStructureEmpty.value = false
  Object.assign(salaryForm, {
    base_salary: Number(record.base_salary || 0),
    position_salary: Number(record.position_salary || 0),
    housing_allowance: Number(record.housing_allowance || 0),
    transport_allowance: Number(record.transport_allowance || 0),
    meal_allowance: Number(record.meal_allowance || 0),
    communication_allowance: Number(record.communication_allowance || 0),
    other_allowance: Number(record.other_allowance || 0),
    performance_ratio_percent: Number(record.performance_ratio || 0) * 100,
    commission_ratio_percent: Number(record.commission_ratio || 0) * 100,
    social_insurance_base: Number(record.social_insurance_base || 0),
    housing_fund_base: Number(record.housing_fund_base || 0),
    effective_date: record.effective_date || ''
  })
}

const applyPayrollRecord = (record) => {
  payrollRecord.value = record
  if (!record) {
    resetPayrollForm()
    return
  }
  Object.assign(payrollForm, {
    bonus: Number(record.bonus || 0),
    overtime_pay: Number(record.overtime_pay || 0),
    social_insurance_personal: Number(record.social_insurance_personal || 0),
    housing_fund_personal: Number(record.housing_fund_personal || 0),
    income_tax: Number(record.income_tax || 0),
    other_deductions: Number(record.other_deductions || 0),
    social_insurance_company: Number(record.social_insurance_company || 0),
    housing_fund_company: Number(record.housing_fund_company || 0),
    pay_date: record.pay_date || '',
    remark: record.remark || ''
  })
}

const buildSalaryPayload = () => ({
  employee_code: selectedEmployee.value.employee_code,
  base_salary: Number(salaryForm.base_salary || 0),
  position_salary: Number(salaryForm.position_salary || 0),
  housing_allowance: Number(salaryForm.housing_allowance || 0),
  transport_allowance: Number(salaryForm.transport_allowance || 0),
  meal_allowance: Number(salaryForm.meal_allowance || 0),
  communication_allowance: Number(salaryForm.communication_allowance || 0),
  other_allowance: Number(salaryForm.other_allowance || 0),
  performance_ratio: Number(salaryForm.performance_ratio_percent || 0) / 100,
  commission_ratio: Number(salaryForm.commission_ratio_percent || 0) / 100,
  social_insurance_base: Number(salaryForm.social_insurance_base || 0),
  housing_fund_base: Number(salaryForm.housing_fund_base || 0),
  effective_date: salaryForm.effective_date,
  status: 'active'
})

const loadBaseData = async () => {
  pageLoading.value = true
  loadingEmployees.value = true
  try {
    const [employeeData, departmentData, positionData] = await Promise.all([
      api.getHrEmployees({ page: 1, page_size: 200 }),
      api.getHrDepartments({ status: 'active' }),
      api.getHrPositions({ status: 'active' })
    ])
    employees.value = employeeData || []
    departments.value = departmentData || []
    positions.value = positionData || []
    if (!selectedMonth.value) {
      selectedMonth.value = recentMonths.value[0]
    }
    if (!selectedEmployee.value && employees.value.length > 0) {
      await selectEmployee(employees.value[0])
    }
  } catch (error) {
    console.error('加载员工薪资基础数据失败:', error)
    ElMessage.error(error.message || '加载员工薪资基础数据失败')
  } finally {
    loadingEmployees.value = false
    pageLoading.value = false
  }
}

const loadSalaryStructure = async () => {
  if (!selectedEmployee.value) return
  try {
    const record = await api.getHrSalaryStructure(selectedEmployee.value.employee_code)
    applySalaryStructure(record)
  } catch (error) {
    applySalaryStructure(null)
    if (error?.response?.status && error.response.status !== 404) {
      ElMessage.error(error.response?.data?.message || error.message || '加载固定薪资失败')
    }
  }
}

const loadSalaryHistory = async () => {
  if (!selectedEmployee.value) return
  try {
    const rows = await api.getHrSalaryStructureHistory(selectedEmployee.value.employee_code)
    salaryHistory.value = rows || []
  } catch (error) {
    salaryHistory.value = []
    if (error?.response?.status && error.response.status !== 404) {
      ElMessage.error(error.response?.data?.message || error.message || '加载历史版本失败')
    }
  }
}

const loadPayrollRecord = async () => {
  if (!selectedEmployee.value || !selectedMonth.value) return
  lockedConflicts.value = []
  try {
    const response = await api.getHrPayrollRecord(selectedEmployee.value.employee_code, selectedMonth.value)
    applyPayrollRecord(response?.data || response)
  } catch (error) {
    applyPayrollRecord(null)
    if (error?.response?.status && error.response.status !== 404) {
      ElMessage.error(error.response?.data?.message || error.message || '加载工资单失败')
    }
  }
}

const selectEmployee = async (employee) => {
  selectedEmployee.value = employee
  await Promise.all([loadSalaryStructure(), loadSalaryHistory(), loadPayrollRecord()])
}

const refreshCurrentView = async () => {
  if (!selectedEmployee.value) {
    await loadBaseData()
    return
  }
  pageLoading.value = true
  try {
    await Promise.all([loadSalaryStructure(), loadSalaryHistory(), loadPayrollRecord()])
  } finally {
    pageLoading.value = false
  }
}

const saveFixedSalary = async (forceCreateVersion) => {
  if (!selectedEmployee.value) return
  if (!salaryForm.effective_date) {
    ElMessage.warning('请先选择生效日期')
    return
  }
  savingSalaryStructure.value = true
  try {
    const payload = buildSalaryPayload()
    if (salaryStructureEmpty.value || forceCreateVersion) {
      await api.createHrSalaryStructure(payload)
      ElMessage.success('固定薪资已创建')
    } else {
      await api.updateHrSalaryStructure(selectedEmployee.value.employee_code, payload)
      ElMessage.success('固定薪资已更新')
    }
    await Promise.all([loadSalaryStructure(), loadSalaryHistory()])
  } catch (error) {
    console.error('保存固定薪资失败:', error)
    ElMessage.error(error.response?.data?.message || error.message || '保存固定薪资失败')
  } finally {
    savingSalaryStructure.value = false
  }
}

const openNewVersionFromCurrent = async () => {
  if (!selectedEmployee.value) return
  await saveFixedSalary(true)
}

const refreshPayrollResult = async () => {
  if (!selectedEmployee.value || !selectedMonth.value) return
  refreshingPayroll.value = true
  try {
    const response = await api.refreshHrPayrollRecord(selectedEmployee.value.employee_code, selectedMonth.value)
    lockedConflicts.value = response?.locked_conflict_details || []
    applyPayrollRecord(response?.data || null)
    ElMessage.success('工资单结果已刷新')
  } catch (error) {
    console.error('刷新工资单结果失败:', error)
    ElMessage.error(error.response?.data?.message || error.message || '刷新工资单结果失败')
  } finally {
    refreshingPayroll.value = false
  }
}

const ensurePayrollRecord = async () => {
  if (payrollRecord.value?.id) return payrollRecord.value
  const response = await api.refreshHrPayrollRecord(selectedEmployee.value.employee_code, selectedMonth.value)
  lockedConflicts.value = response?.locked_conflict_details || []
  applyPayrollRecord(response?.data || null)
  return payrollRecord.value
}

const saveMonthlyDraft = async () => {
  if (!selectedEmployee.value || !selectedMonth.value) return
  savingPayroll.value = true
  try {
    const record = await ensurePayrollRecord()
    if (!record?.id) {
      throw new Error('当前月份还没有可编辑工资单，请先配置固定薪资后刷新结果')
    }
    await api.updateHrPayrollRecord(record.id, {
      bonus: payrollForm.bonus,
      overtime_pay: payrollForm.overtime_pay,
      social_insurance_personal: payrollForm.social_insurance_personal,
      housing_fund_personal: payrollForm.housing_fund_personal,
      income_tax: payrollForm.income_tax,
      other_deductions: payrollForm.other_deductions,
      social_insurance_company: payrollForm.social_insurance_company,
      housing_fund_company: payrollForm.housing_fund_company,
      pay_date: payrollForm.pay_date || null,
      remark: payrollForm.remark || null
    })
    ElMessage.success('月度草稿已保存')
    await loadPayrollRecord()
  } catch (error) {
    console.error('保存月度草稿失败:', error)
    ElMessage.error(error.response?.data?.message || error.message || '保存月度草稿失败')
  } finally {
    savingPayroll.value = false
  }
}

const copyPreviousMonthManualFields = async () => {
  if (!selectedEmployee.value || !previousMonth.value) return
  try {
    const response = await api.getHrPayrollRecord(selectedEmployee.value.employee_code, previousMonth.value)
    const prev = response?.data || response
    Object.assign(payrollForm, {
      bonus: Number(prev?.bonus || 0),
      overtime_pay: Number(prev?.overtime_pay || 0),
      social_insurance_personal: Number(prev?.social_insurance_personal || 0),
      housing_fund_personal: Number(prev?.housing_fund_personal || 0),
      income_tax: Number(prev?.income_tax || 0),
      other_deductions: Number(prev?.other_deductions || 0),
      social_insurance_company: Number(prev?.social_insurance_company || 0),
      housing_fund_company: Number(prev?.housing_fund_company || 0),
      pay_date: prev?.pay_date || '',
      remark: prev?.remark || ''
    })
    ElMessage.success('已复制上月人工项')
  } catch (error) {
    console.error('复制上月人工项失败:', error)
    ElMessage.warning('上月没有可复制的工资单草稿')
  }
}

const confirmPayroll = async () => {
  if (!payrollRecord.value?.id) return
  try {
    await ElMessageBox.confirm('确认后系统不会自动覆盖该工资单，是否继续？', '确认工资单', { type: 'warning' })
    await api.confirmHrPayrollRecord(payrollRecord.value.id)
    ElMessage.success('工资单已确认')
    await loadPayrollRecord()
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error.response?.data?.message || error.message || '确认工资单失败')
  }
}

const reopenPayroll = async () => {
  if (!payrollRecord.value?.id) return
  try {
    await ElMessageBox.confirm('退回草稿后可重新接受系统重算，是否继续？', '退回草稿', { type: 'warning' })
    await api.reopenHrPayrollRecord(payrollRecord.value.id)
    ElMessage.success('工资单已退回草稿')
    await loadPayrollRecord()
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error.response?.data?.message || error.message || '退回工资单失败')
  }
}

const markPayrollPaid = async () => {
  if (!payrollRecord.value?.id) return
  try {
    await ElMessageBox.confirm('标记已发放后工资单将只读，是否继续？', '标记已发放', { type: 'warning' })
    await api.markHrPayrollRecordPaid(payrollRecord.value.id)
    ElMessage.success('工资单已标记为已发放')
    await loadPayrollRecord()
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error.response?.data?.message || error.message || '标记已发放失败')
  }
}

onMounted(async () => {
  selectedMonth.value = recentMonths.value[0]
  await loadBaseData()
})
</script>

<style scoped>
.employee-salary-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
}

.page-subtitle {
  margin: 6px 0 0;
  color: #606266;
}

.page-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
}

.content-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.employee-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 720px;
  overflow: auto;
}

.employee-item {
  width: 100%;
  text-align: left;
  border: 1px solid #dcdfe6;
  border-radius: 10px;
  padding: 12px;
  background: #fff;
  cursor: pointer;
}

.employee-item.active {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.12);
}

.employee-name-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.employee-name {
  font-weight: 600;
}

.employee-meta {
  color: #606266;
  font-size: 13px;
  line-height: 1.5;
}

.history-section {
  margin-top: 12px;
}

.history-title {
  margin-bottom: 8px;
  font-weight: 600;
}

.result-grid {
  row-gap: 12px;
}

.result-item {
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #fafafa;
}

.result-item span {
  color: #606266;
}

.result-item strong {
  font-size: 18px;
}

@media (max-width: 1200px) {
  .page-layout {
    grid-template-columns: 1fr;
  }
}
</style>
