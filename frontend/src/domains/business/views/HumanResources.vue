<template>
  <div class="human-resources erp-page-container">
    <!-- 页面头部 -->
    <PageHeader
      title="人力管理"
      subtitle="提升团队效率，优化人力资源配置"
      family="admin"
    >
      <template #actions>
        <el-button plain @click="handleOpenPayrollRunbook">
          工资单运行手册
        </el-button>
        <el-button type="primary" @click="refreshData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
      </template>
    </PageHeader>

    <p class="page-note">
      员工档案默认只看正式员工与在职状态，访客档案可用「身份」筛选单独查看；
      员工离职请在员工管理页使用「办理离职」，系统不做物理删除，工资单、绩效、提成与店铺归属记录全部保留。
    </p>

    <!-- 功能导航区域 -->
    <div class="function-nav">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <!-- 员工管理 Tab -->
        <el-tab-pane label="员工管理" name="employees">
          <EmployeeTab
            ref="employeeTabRef"
            :offboard-handler="handleOffboardEmployee"
          />
        </el-tab-pane>

        <!-- 部门管理 Tab -->
        <el-tab-pane label="部门管理" name="departments">
          <div class="departments-content">
            <el-card class="analysis-card" shadow="hover">
              <template #header>
                <div class="card-header">
                  <span>组织架构管理</span>
                  <div class="header-actions">
                    <el-button type="primary" @click="showDepartmentDialog()">
                      <el-icon><Plus /></el-icon>
                      添加部门
                    </el-button>
                  </div>
                </div>
              </template>
              <el-alert
                title="薪资维护已迁移到员工薪资页。固定薪资、月度奖金/扣款、工资单确认和发放请统一在员工薪资页处理。"
                type="info"
                :closable="false"
                style="margin-bottom: 16px"
              />
              <el-table
                :data="departments"
                style="width: 100%"
                v-loading="loadingDepartments"
                row-key="id"
                default-expand-all
              >
                <el-table-column
                  prop="department_code"
                  label="部门编码"
                  width="120"
                ></el-table-column>
                <el-table-column
                  prop="department_name"
                  label="部门名称"
                  width="150"
                ></el-table-column>
                <el-table-column prop="level" label="层级" width="80">
                  <template #default="scope">
                    <el-tag size="small">L{{ scope.row.level }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="description"
                  label="描述"
                  show-overflow-tooltip
                ></el-table-column>
                <el-table-column prop="status" label="状态" width="80">
                  <template #default="scope">
                    <el-tag
                      :type="scope.row.status === 'active' ? 'success' : 'info'"
                      size="small"
                    >
                      {{ scope.row.status === "active" ? "启用" : "停用" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="150">
                  <template #default="scope">
                    <el-button
                      type="primary"
                      size="small"
                      @click="showDepartmentDialog(scope.row)"
                      >编辑</el-button
                    >
                    <el-popconfirm
                      title="确定删除该部门？"
                      @confirm="deleteDepartment(scope.row)"
                    >
                      <template #reference>
                        <el-button type="danger" size="small">删除</el-button>
                      </template>
                    </el-popconfirm>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="220" fixed="right">
                  <template #default="scope">
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="primary"
                      @click="handleOpenEmployeeSalary"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="success"
                      @click="handleOpenEmployeeSalary"
                    >
                      确认
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'confirmed'"
                      link
                      type="warning"
                      @click="handleOpenEmployeeSalary"
                    >
                      退回草稿
                    </el-button>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="220" fixed="right">
                  <template #default="scope">
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="primary"
                      @click="handleOpenEmployeeSalary"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="success"
                      @click="handleOpenEmployeeSalary"
                    >
                      确认
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'confirmed'"
                      link
                      type="warning"
                      @click="handleOpenEmployeeSalary"
                    >
                      退回草稿
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- 职位管理 Tab -->
        <el-tab-pane label="职位管理" name="positions">
          <div class="positions-content">
            <el-card class="analysis-card" shadow="hover">
              <template #header>
                <div class="card-header">
                  <span>职位体系管理</span>
                  <div class="header-actions">
                    <el-button type="primary" @click="showPositionDialog()">
                      <el-icon><Plus /></el-icon>
                      添加职位
                    </el-button>
                  </div>
                </div>
              </template>
              <el-table
                :data="positions"
                style="width: 100%"
                v-loading="loadingPositions"
              >
                <el-table-column
                  prop="position_code"
                  label="职位编码"
                  width="120"
                ></el-table-column>
                <el-table-column
                  prop="position_name"
                  label="职位名称"
                  width="150"
                ></el-table-column>
                <el-table-column prop="position_level" label="职级" width="80">
                  <template #default="scope">
                    <el-tag type="warning" size="small"
                      >P{{ scope.row.position_level }}</el-tag
                    >
                  </template>
                </el-table-column>
                <el-table-column label="薪资范围" width="180">
                  <template #default="scope">
                    <span v-if="scope.row.min_salary || scope.row.max_salary">
                      {{ formatMoney(scope.row.min_salary) }} -
                      {{ formatMoney(scope.row.max_salary) }}
                    </span>
                    <span v-else class="text-muted">未设置</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="description"
                  label="职位描述"
                  show-overflow-tooltip
                ></el-table-column>
                <el-table-column prop="status" label="状态" width="80">
                  <template #default="scope">
                    <el-tag
                      :type="scope.row.status === 'active' ? 'success' : 'info'"
                      size="small"
                    >
                      {{ scope.row.status === "active" ? "启用" : "停用" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="150">
                  <template #default="scope">
                    <el-button
                      type="primary"
                      size="small"
                      @click="showPositionDialog(scope.row)"
                      >编辑</el-button
                    >
                    <el-popconfirm
                      title="确定删除该职位？"
                      @confirm="deletePosition(scope.row)"
                    >
                      <template #reference>
                        <el-button type="danger" size="small">删除</el-button>
                      </template>
                    </el-popconfirm>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- 考勤管理 Tab -->
        <el-tab-pane label="考勤管理" name="attendance">
          <div class="attendance-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="analysis-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>考勤记录</span>
                      <div class="header-actions">
                        <el-date-picker
                          v-model="attendanceDateRange"
                          type="daterange"
                          range-separator="至"
                          start-placeholder="开始日期"
                          end-placeholder="结束日期"
                          format="YYYY-MM-DD"
                          value-format="YYYY-MM-DD"
                          @change="loadAttendance"
                        />
                        <el-button
                          type="primary"
                          @click="showAttendanceDialog()"
                        >
                          <el-icon><Plus /></el-icon>
                          添加记录
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <el-table
                    :data="attendanceRecords"
                    style="width: 100%"
                    v-loading="loadingAttendance"
                  >
                    <el-table-column
                      prop="employee_code"
                      label="员工"
                      width="120"
                    >
                      <template #default="scope">
                        {{ getEmployeeName(scope.row.employee_code) }}
                      </template>
                    </el-table-column>
                    <el-table-column
                      prop="attendance_date"
                      label="日期"
                      width="110"
                    ></el-table-column>
                    <el-table-column label="上班时间" width="100">
                      <template #default="scope">
                        {{ formatTime(scope.row.clock_in_time) }}
                      </template>
                    </el-table-column>
                    <el-table-column label="下班时间" width="100">
                      <template #default="scope">
                        {{ formatTime(scope.row.clock_out_time) }}
                      </template>
                    </el-table-column>
                    <el-table-column label="工作时长" width="100">
                      <template #default="scope">
                        {{
                          scope.row.work_hours
                            ? scope.row.work_hours.toFixed(1) + "h"
                            : "-"
                        }}
                      </template>
                    </el-table-column>
                    <el-table-column label="加班时长" width="100">
                      <template #default="scope">
                        {{
                          scope.row.overtime_hours
                            ? scope.row.overtime_hours.toFixed(1) + "h"
                            : "-"
                        }}
                      </template>
                    </el-table-column>
                    <el-table-column prop="status" label="状态" width="90">
                      <template #default="scope">
                        <el-tag
                          :type="getAttendanceStatusType(scope.row.status)"
                          size="small"
                        >
                          {{ getAttendanceStatusLabel(scope.row.status) }}
                        </el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column
                      prop="remark"
                      label="备注"
                      show-overflow-tooltip
                    ></el-table-column>
                  </el-table>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <!-- 薪资管理 Tab -->
        <el-tab-pane label="薪资管理" name="salary">
          <div class="salary-content">
            <el-card class="analysis-card" shadow="hover">
              <template #header>
                <div class="card-header">
                  <span>工资单记录</span>
                  <div class="header-actions">
                    <el-select
                      v-model="salaryMonth"
                      placeholder="选择月份"
                      @change="loadPayroll"
                    >
                      <el-option
                        v-for="month in recentMonths"
                        :key="month"
                        :label="month"
                        :value="month"
                      />
                    </el-select>
                    <el-button type="primary" @click="handleOpenEmployeeSalary">
                      前往员工薪资
                    </el-button>
                  </div>
                </div>
              </template>
              <el-table
                :data="payrollRecords"
                style="width: 100%"
                v-loading="loadingPayroll"
                show-summary
                :summary-method="getPayrollSummary"
              >
                <el-table-column prop="employee_code" label="员工" width="120">
                  <template #default="scope">
                    {{ getEmployeeName(scope.row.employee_code) }}
                  </template>
                </el-table-column>
                <el-table-column
                  prop="year_month"
                  label="月份"
                  width="100"
                ></el-table-column>
                <el-table-column label="基本工资" width="110" align="right">
                  <template #default="scope">
                    {{ formatMoney(scope.row.base_salary) }}
                  </template>
                </el-table-column>
                <el-table-column label="绩效工资" width="110" align="right">
                  <template #default="scope">
                    {{ formatMoney(scope.row.performance_salary) }}
                  </template>
                </el-table-column>
                <el-table-column label="津贴" width="100" align="right">
                  <template #default="scope">
                    {{ formatMoney(scope.row.allowances) }}
                  </template>
                </el-table-column>
                <el-table-column label="应发合计" width="110" align="right">
                  <template #default="scope">
                    <span class="text-primary">{{
                      formatMoney(scope.row.gross_salary)
                    }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="扣款合计" width="110" align="right">
                  <template #default="scope">
                    <span class="text-danger">{{
                      formatMoney(scope.row.total_deductions)
                    }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="实发工资" width="120" align="right">
                  <template #default="scope">
                    <span class="net-salary">{{
                      formatMoney(scope.row.net_salary)
                    }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="80">
                  <template #default="scope">
                    <el-tag
                      :type="payrollStatusTagType(scope.row.status)"
                      size="small"
                    >
                      {{ payrollStatusLabel(scope.row.status) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="工资单操作" width="300" fixed="right">
                  <template #default="scope">
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="primary"
                      @click="handleOpenEmployeeSalary"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="success"
                      @click="handleOpenEmployeeSalary"
                    >
                      确认
                    </el-button>
                    <el-button
                      v-if="showPayrollPayAction(scope.row)"
                      link
                      type="primary"
                      @click="handleOpenEmployeeSalary"
                    >
                      已发放
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'confirmed'"
                      link
                      type="warning"
                      @click="handleOpenEmployeeSalary"
                    >
                      退回草稿
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 部门表单弹窗 -->
    <el-dialog
      v-model="departmentDialogVisible"
      :title="editingDepartment ? '编辑部门' : '添加部门'"
      width="500px"
      destroy-on-close
    >
      <el-form
        ref="departmentFormRef"
        :model="departmentForm"
        :rules="departmentRules"
        label-width="100px"
      >
        <el-form-item label="部门编码" prop="department_code">
          <el-input
            v-model="departmentForm.department_code"
            :disabled="!!editingDepartment"
            placeholder="如：DEPT001"
          />
        </el-form-item>
        <el-form-item label="部门名称" prop="department_name">
          <el-input
            v-model="departmentForm.department_name"
            placeholder="请输入部门名称"
          />
        </el-form-item>
        <el-form-item label="上级部门" prop="parent_id">
          <el-select
            v-model="departmentForm.parent_id"
            placeholder="选择上级部门（可选）"
            style="width: 100%"
            clearable
          >
            <el-option
              v-for="dept in departments.filter(
                (d) => d.id !== editingDepartment?.id,
              )"
              :key="dept.id"
              :label="dept.department_name"
              :value="dept.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="部门层级" prop="level">
          <el-input-number v-model="departmentForm.level" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="departmentForm.description"
            type="textarea"
            :rows="2"
            placeholder="部门描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="departmentDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="saveDepartment"
          :loading="savingDepartment"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <!-- 职位表单弹窗 -->
    <el-dialog
      v-model="positionDialogVisible"
      :title="editingPosition ? '编辑职位' : '添加职位'"
      width="500px"
      destroy-on-close
    >
      <el-form
        ref="positionFormRef"
        :model="positionForm"
        :rules="positionRules"
        label-width="100px"
      >
        <el-form-item label="职位编码" prop="position_code">
          <el-input
            v-model="positionForm.position_code"
            :disabled="!!editingPosition"
            placeholder="如：POS001"
          />
        </el-form-item>
        <el-form-item label="职位名称" prop="position_name">
          <el-input
            v-model="positionForm.position_name"
            placeholder="请输入职位名称"
          />
        </el-form-item>
        <el-form-item label="职级" prop="position_level">
          <el-input-number
            v-model="positionForm.position_level"
            :min="1"
            :max="10"
          />
        </el-form-item>
        <el-form-item label="所属部门" prop="department_id">
          <el-select
            v-model="positionForm.department_id"
            placeholder="选择所属部门（可选）"
            style="width: 100%"
            clearable
          >
            <el-option
              v-for="dept in departments"
              :key="dept.id"
              :label="dept.department_name"
              :value="dept.id"
            />
          </el-select>
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="薪资下限" prop="min_salary">
              <el-input-number
                v-model="positionForm.min_salary"
                :min="0"
                :step="1000"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="薪资上限" prop="max_salary">
              <el-input-number
                v-model="positionForm.max_salary"
                :min="0"
                :step="1000"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="职位描述" prop="description">
          <el-input
            v-model="positionForm.description"
            type="textarea"
            :rows="2"
            placeholder="职位描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="positionDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="savePosition"
          :loading="savingPosition"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="payrollDialogVisible"
      title="编辑工资单草稿"
      width="700px"
      destroy-on-close
    >
      <el-form :model="payrollForm" label-width="150px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="加班费">
              <el-input-number v-model="payrollForm.overtime_pay" :min="0" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="奖金">
              <el-input-number v-model="payrollForm.bonus" :min="0" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="个人社保">
              <el-input-number v-model="payrollForm.social_insurance_personal" :min="0" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="个人公积金">
              <el-input-number v-model="payrollForm.housing_fund_personal" :min="0" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="个税">
              <el-input-number v-model="payrollForm.income_tax" :min="0" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="其他扣款">
              <el-input-number v-model="payrollForm.other_deductions" :min="0" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="公司社保">
              <el-input-number v-model="payrollForm.social_insurance_company" :min="0" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="公司公积金">
              <el-input-number v-model="payrollForm.housing_fund_company" :min="0" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="发薪日期">
          <el-date-picker v-model="payrollForm.pay_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="payrollForm.remark" type="textarea" :rows="3" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="payrollDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPayroll" @click="savePayroll">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { Plus, Refresh } from '@element-plus/icons-vue'
import api from '@/api'
import PageHeader from '@/components/common/PageHeader.vue'
import EmployeeTab from '@/domains/business/views/hr/EmployeeTab.vue'
import { payrollStatusLabel, payrollStatusTagType } from '@/constants/hr'

// ============================================================================
// 响应式数据
// ============================================================================

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const validTabs = ['employees', 'departments', 'positions', 'attendance', 'salary']
const activeTab = ref(
  validTabs.includes(route.query.tab) ? route.query.tab : 'employees'
)

// 员工 Tab 组件引用：办理离职后由页面统一刷新员工列表
const employeeTabRef = ref(null)

// 员工姓名映射：考勤 / 工资单 Tab 需要显示员工姓名。
// 员工列表本身由 EmployeeTab 自己持有，这里只做名称解析，避免跨文件隐式依赖。
const employees = ref([])

// 部门数据
const departments = ref([])
const loadingDepartments = ref(false)

// 职位数据
const positions = ref([])
const loadingPositions = ref(false)

// 考勤数据
const attendanceRecords = ref([])
const loadingAttendance = ref(false)
const attendanceDateRange = ref([])

// 薪资数据
const payrollRecords = ref([])
const loadingPayroll = ref(false)
const salaryMonth = ref('')
const payrollDialogVisible = ref(false)
const savingPayroll = ref(false)
const editingPayroll = ref(null)
const payrollForm = reactive({
  overtime_pay: 0,
  bonus: 0,
  social_insurance_personal: 0,
  housing_fund_personal: 0,
  income_tax: 0,
  other_deductions: 0,
  social_insurance_company: 0,
  housing_fund_company: 0,
  pay_date: '',
  remark: ''
})

const isPayrollAdmin = computed(() => {
  const user = authStore.user
  if (!user) return false
  if (user.is_superuser) return true
  const roles = Array.isArray(user.roles) ? user.roles : []
  return roles.some((role) => {
    if (typeof role === 'string') return role === 'admin'
    return role?.role_code === 'admin' || role?.role_name === 'admin'
  })
})

// 弹窗控制
const departmentDialogVisible = ref(false)
const positionDialogVisible = ref(false)

// 编辑状态
const editingDepartment = ref(null)
const editingPosition = ref(null)

const departmentForm = reactive({
  department_code: '',
  department_name: '',
  parent_id: null,
  level: 1,
  description: ''
})

const positionForm = reactive({
  position_code: '',
  position_name: '',
  position_level: 1,
  department_id: null,
  min_salary: null,
  max_salary: null,
  description: ''
})

// 保存状态
const savingDepartment = ref(false)
const savingPosition = ref(false)

// 表单引用
const departmentFormRef = ref(null)
const positionFormRef = ref(null)

// 表单验证规则
const departmentRules = {
  department_code: [
    { required: true, message: '请输入部门编码', trigger: 'blur' }
  ],
  department_name: [
    { required: true, message: '请输入部门名称', trigger: 'blur' }
  ]
}

const positionRules = {
  position_code: [
    { required: true, message: '请输入职位编码', trigger: 'blur' }
  ],
  position_name: [
    { required: true, message: '请输入职位名称', trigger: 'blur' }
  ]
}

// 最近月份列表
const recentMonths = computed(() => {
  const months = []
  const now = new Date()
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    months.push(
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    )
  }
  return months
})

// ============================================================================
// 生命周期
// ============================================================================

onMounted(async () => {
  salaryMonth.value = recentMonths.value[0]
  await loadInitialData()
})

// ============================================================================
// 数据加载方法
// ============================================================================

const loadInitialData = async () => {
  loading.value = true
  try {
    await Promise.all([
      loadDepartments(),
      loadPositions(),
      loadEmployeeNames()
    ])
  } catch (error) {
    console.error('加载初始数据失败:', error)
    ElMessage.error('加载数据失败，请刷新重试')
  } finally {
    loading.value = false
  }
}

const refreshData = () => {
  loadInitialData()
  ElMessage.success('数据已刷新')
}

const handleOpenPayrollRunbook = () => {
  router.push({ name: 'UserGuide', query: { topic: 'hr-payroll' } })
}

const handleOpenEmployeeSalary = () => {
  router.push({ name: 'EmployeeSalary' })
}

const handleTabChange = (tabName) => {
  if (tabName === 'attendance' && attendanceRecords.value.length === 0) {
    loadAttendance()
  } else if (tabName === 'salary' && payrollRecords.value.length === 0) {
    loadPayroll()
  }
}

// 加载部门列表
const loadDepartments = async () => {
  loadingDepartments.value = true
  try {
    const data = await api.getHrDepartments({ status: 'active' })
    departments.value = data || []
  } catch (error) {
    console.error('加载部门列表失败:', error)
    departments.value = []
  } finally {
    loadingDepartments.value = false
  }
}

// 加载职位列表
const loadPositions = async () => {
  loadingPositions.value = true
  try {
    const data = await api.getHrPositions({ status: 'active' })
    positions.value = data || []
  } catch (error) {
    console.error('加载职位列表失败:', error)
    positions.value = []
  } finally {
    loadingPositions.value = false
  }
}

// 加载员工姓名映射（考勤 / 工资单 Tab 用）
const loadEmployeeNames = async () => {
  try {
    const data = await api.getHrEmployees({ page: 1, page_size: 500 })
    employees.value = data || []
  } catch (error) {
    console.error('加载员工姓名失败:', error)
    employees.value = []
  }
}

// 加载考勤记录
const loadAttendance = async () => {
  loadingAttendance.value = true
  try {
    const params = {}
    if (attendanceDateRange.value && attendanceDateRange.value.length === 2) {
      params.start_date = attendanceDateRange.value[0]
      params.end_date = attendanceDateRange.value[1]
    }
    const data = await api.getHrAttendance(params)
    attendanceRecords.value = data || []
  } catch (error) {
    console.error('加载考勤记录失败:', error)
    attendanceRecords.value = []
  } finally {
    loadingAttendance.value = false
  }
}

// 加载工资单
const loadPayroll = async () => {
  loadingPayroll.value = true
  try {
    const data = await api.getHrPayrollRecords({
      year_month: salaryMonth.value
    })
    payrollRecords.value = data || []
  } catch (error) {
    console.error('加载工资单失败:', error)
    payrollRecords.value = []
  } finally {
    loadingPayroll.value = false
  }
}

// ============================================================================
// 员工操作方法
// ============================================================================

const savePayroll = async () => {
  if (!editingPayroll.value) return
  savingPayroll.value = true
  try {
    await api.updateHrPayrollRecord(editingPayroll.value.id, {
      overtime_pay: payrollForm.overtime_pay,
      bonus: payrollForm.bonus,
      social_insurance_personal: payrollForm.social_insurance_personal,
      housing_fund_personal: payrollForm.housing_fund_personal,
      income_tax: payrollForm.income_tax,
      other_deductions: payrollForm.other_deductions,
      social_insurance_company: payrollForm.social_insurance_company,
      housing_fund_company: payrollForm.housing_fund_company,
      pay_date: payrollForm.pay_date || null,
      remark: payrollForm.remark || null
    })
    payrollDialogVisible.value = false
    ElMessage.success('工资单草稿已更新')
    await loadPayroll()
  } catch (error) {
    console.error('更新工资单失败:', error)
    ElMessage.error(error.response?.data?.message || error.message || '更新工资单失败')
  } finally {
    savingPayroll.value = false
  }
}

const showPayrollPayAction = (record) =>
  record?.status === 'confirmed' && isPayrollAdmin.value

/**
 * 办理离职：页面级统一执行（成功提示 + 刷新员工列表都在这里），
 * 员工 Tab 只负责收集离职日期 / 最后发薪月 / 离职原因。
 */
const handleOffboardEmployee = async ({ employeeCode, payload }) => {
  const response = await api.offboardHrEmployee(employeeCode, payload)
  ElMessage.success('已办理离职')
  const pendingMonths =
    response?.pending_payroll_months || response?.data?.pending_payroll_months || []
  if (pendingMonths.length > 0) {
    ElMessage.warning(
      `还有草稿工资单未结算：${pendingMonths.join('、')}，请到员工薪资页确认或发放`
    )
  }
  await employeeTabRef.value?.reload()
  await loadEmployeeNames()
}

// ============================================================================
// 部门操作方法
// ============================================================================

const showDepartmentDialog = (department = null) => {
  editingDepartment.value = department
  if (department) {
    Object.assign(departmentForm, {
      department_code: department.department_code,
      department_name: department.department_name,
      parent_id: department.parent_id,
      level: department.level,
      description: department.description || ''
    })
  } else {
    Object.assign(departmentForm, {
      department_code: '',
      department_name: '',
      parent_id: null,
      level: 1,
      description: ''
    })
  }
  departmentDialogVisible.value = true
}

const saveDepartment = async () => {
  if (!departmentFormRef.value) return
  await departmentFormRef.value.validate()

  savingDepartment.value = true
  try {
    if (editingDepartment.value) {
      await api.updateHrDepartment(editingDepartment.value.id, departmentForm)
      ElMessage.success('部门信息已更新')
    } else {
      await api.createHrDepartment(departmentForm)
      ElMessage.success('部门已添加')
    }
    departmentDialogVisible.value = false
    await loadDepartments()
  } catch (error) {
    console.error('保存部门失败:', error)
    ElMessage.error(error.message || '保存失败')
  } finally {
    savingDepartment.value = false
  }
}

const deleteDepartment = async (department) => {
  try {
    await api.deleteHrDepartment(department.id)
    ElMessage.success('部门已删除')
    await loadDepartments()
  } catch (error) {
    console.error('删除部门失败:', error)
    ElMessage.error(error.message || '删除失败')
  }
}

// ============================================================================
// 职位操作方法
// ============================================================================

const showPositionDialog = (position = null) => {
  editingPosition.value = position
  if (position) {
    Object.assign(positionForm, {
      position_code: position.position_code,
      position_name: position.position_name,
      position_level: position.position_level,
      department_id: position.department_id,
      min_salary: position.min_salary,
      max_salary: position.max_salary,
      description: position.description || ''
    })
  } else {
    Object.assign(positionForm, {
      position_code: '',
      position_name: '',
      position_level: 1,
      department_id: null,
      min_salary: null,
      max_salary: null,
      description: ''
    })
  }
  positionDialogVisible.value = true
}

const savePosition = async () => {
  if (!positionFormRef.value) return
  await positionFormRef.value.validate()

  savingPosition.value = true
  try {
    if (editingPosition.value) {
      await api.updateHrPosition(editingPosition.value.id, positionForm)
      ElMessage.success('职位信息已更新')
    } else {
      await api.createHrPosition(positionForm)
      ElMessage.success('职位已添加')
    }
    positionDialogVisible.value = false
    await loadPositions()
  } catch (error) {
    console.error('保存职位失败:', error)
    ElMessage.error(error.message || '保存失败')
  } finally {
    savingPosition.value = false
  }
}

const deletePosition = async (position) => {
  try {
    await api.deleteHrPosition(position.id)
    ElMessage.success('职位已删除')
    await loadPositions()
  } catch (error) {
    console.error('删除职位失败:', error)
    ElMessage.error(error.message || '删除失败')
  }
}

// ============================================================================
// 考勤操作方法
// ============================================================================

const showAttendanceDialog = () => {
  ElMessage.info('考勤记录添加功能开发中...')
}

// ============================================================================
// 辅助方法
// ============================================================================

const getEmployeeName = (employeeCode) => {
  const emp = (employees.value || []).find((e) => e.employee_code === employeeCode)
  return emp?.name || employeeCode
}

const getAttendanceStatusType = (status) => {
  const map = {
    normal: 'success',
    late: 'warning',
    early_leave: 'warning',
    absent: 'danger',
    leave: 'info'
  }
  return map[status] || 'info'
}

const getAttendanceStatusLabel = (status) => {
  const map = {
    normal: '正常',
    late: '迟到',
    early_leave: '早退',
    absent: '缺勤',
    leave: '请假'
  }
  return map[status] || status
}

const formatMoney = (value) => {
  if (value === null || value === undefined) return '-'
  return `¥${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const formatTime = (datetime) => {
  if (!datetime) return '-'
  try {
    const date = new Date(datetime)
    return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
  } catch {
    return '-'
  }
}

const getPayrollSummary = (param) => {
  const { columns } = param
  const sums = []
  columns.forEach((column, index) => {
    if (index === 0) {
      sums[index] = '合计'
    } else if (
      [
        'base_salary',
        'performance_salary',
        'allowances',
        'gross_salary',
        'total_deductions',
        'net_salary'
      ].includes(column.property)
    ) {
      const values = payrollRecords.value.map(
        (item) => Number(item[column.property]) || 0
      )
      const sum = values.reduce((acc, val) => acc + val, 0)
      sums[index] = formatMoney(sum)
    } else {
      sums[index] = ''
    }
  })
  return sums
}
</script>

<style scoped>
.human-resources {
  background: #f5f7fa;
  min-height: 100vh;
}

.departments-content :deep(.el-table__header-wrapper th:nth-child(7)),
.departments-content :deep(.el-table__header-wrapper th:nth-child(8)),
.departments-content :deep(.el-table__body-wrapper td:nth-child(7)),
.departments-content :deep(.el-table__body-wrapper td:nth-child(8)) {
  display: none;
}

.page-note {
  color: #909399;
  margin: 0 0 16px 0;
  line-height: 1.6;
}

.function-nav {
  background: white;
  border-radius: 8px;
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.text-primary {
  color: #409eff;
  font-weight: 500;
}

.text-danger {
  color: #f56c6c;
}

.text-muted {
  color: #999;
}

.net-salary {
  color: #52c41a;
  font-weight: 600;
  font-size: 15px;
}

.analysis-card {
  margin-bottom: 20px;
}

:deep(.el-tabs__item) {
  font-size: 15px;
}
</style>
