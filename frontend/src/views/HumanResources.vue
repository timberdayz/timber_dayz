<template>
  <div class="human-resources">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><UserFilled /></el-icon>
          人力管理
        </h1>
        <p class="page-subtitle">提升团队效率，优化人力资源配置</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="refreshData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
      </div>
    </div>

    <!-- 功能导航区域 -->
    <div class="function-nav">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <!-- 员工管理 Tab -->
        <el-tab-pane label="员工管理" name="employees">
          <div class="employees-content">
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
                        @keyup.enter="loadEmployees"
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
                        @change="loadEmployees"
                      >
                        <el-option label="全部部门" value=""></el-option>
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
                        @change="loadEmployees"
                      >
                        <el-option label="全部状态" value=""></el-option>
                        <el-option label="在职" value="active"></el-option>
                        <el-option label="离职" value="inactive"></el-option>
                        <el-option label="试用期" value="probation"></el-option>
                      </el-select>
                    </el-col>
                    <el-col :span="4">
                      <el-button type="primary" @click="loadEmployees"
                        >搜索</el-button
                      >
                      <el-button @click="resetFilters">重置</el-button>
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
                          <div class="stat-value">
                            {{ employeeStats.active }}
                          </div>
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
                          <div class="stat-value">
                            {{ employeeStats.probation }}
                          </div>
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
                          <div class="stat-value">
                            {{ employeeStats.inactive }}
                          </div>
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
                          <div class="stat-value">
                            {{ employeeStats.total }}
                          </div>
                          <div class="stat-label">员工总数</div>
                        </div>
                      </div>
                    </el-col>
                  </el-row>
                </div>

                <!-- 员工表格 -->
                <el-table
                  :data="employees"
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
                  <el-table-column
                    prop="employee_code"
                    label="工号"
                    width="100"
                  ></el-table-column>
                  <el-table-column
                    prop="name"
                    label="姓名"
                    width="100"
                  ></el-table-column>
                  <el-table-column label="登录账号" width="120">
                    <template #default="scope">
                      {{ scope.row.username || '—' }}
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
                  <el-table-column
                    prop="phone"
                    label="电话"
                    width="130"
                  ></el-table-column>
                  <el-table-column
                    prop="email"
                    label="邮箱"
                    width="180"
                    show-overflow-tooltip
                  ></el-table-column>
                  <el-table-column
                    prop="hire_date"
                    label="入职日期"
                    width="110"
                  ></el-table-column>
                  <el-table-column prop="status" label="状态" width="90">
                    <template #default="scope">
                      <el-tag
                        :type="getStatusType(scope.row.status)"
                        size="small"
                      >
                        {{ getStatusLabel(scope.row.status) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="180" fixed="right">
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
                      <el-popconfirm
                        title="确定要删除该员工吗？"
                        @confirm="deleteEmployee(scope.row)"
                      >
                        <template #reference>
                          <el-button type="danger" size="small">删除</el-button>
                        </template>
                      </el-popconfirm>
                    </template>
                  </el-table-column>
                </el-table>

                <!-- 分页 -->
                <div class="pagination-wrapper">
                  <el-pagination
                    v-model:current-page="pagination.page"
                    v-model:page-size="pagination.pageSize"
                    :page-sizes="[10, 20, 50, 100]"
                    :total="pagination.total"
                    layout="total, sizes, prev, pager, next, jumper"
                    @size-change="loadEmployees"
                    @current-change="loadEmployees"
                  />
                </div>
              </div>
            </el-card>
          </div>
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
                      @click="showPayrollDialog(scope.row)"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="success"
                      @click="confirmPayroll(scope.row)"
                    >
                      确认
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'confirmed'"
                      link
                      type="warning"
                      @click="reopenPayroll(scope.row)"
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
                      @click="showPayrollDialog(scope.row)"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="success"
                      @click="confirmPayroll(scope.row)"
                    >
                      确认
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'confirmed'"
                      link
                      type="warning"
                      @click="reopenPayroll(scope.row)"
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
                      :type="getPayrollStatusType(scope.row.status)"
                      size="small"
                    >
                      {{ getPayrollStatusLabel(scope.row.status) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="工资单操作" width="240" fixed="right">
                  <template #default="scope">
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="primary"
                      @click="showPayrollDialog(scope.row)"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'draft'"
                      link
                      type="success"
                      @click="confirmPayroll(scope.row)"
                    >
                      确认
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'confirmed'"
                      link
                      type="warning"
                      @click="reopenPayroll(scope.row)"
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
              <el-input
                v-model="employeeForm.phone"
                placeholder="请输入手机号"
              />
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
                <el-option label="在职" value="active" />
                <el-option label="试用期" value="probation" />
                <el-option label="已离职" value="inactive" />
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
              :label="`${u.username}${u.email ? ' (' + u.email + ')' : ''}`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="证件号码" prop="id_number">
              <el-input
                v-model="employeeForm.id_number"
                placeholder="身份证号码"
              />
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
              <el-input
                v-model="employeeForm.emergency_contact"
                placeholder="紧急联系人姓名"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="紧急电话" prop="emergency_phone">
              <el-input
                v-model="employeeForm.emergency_phone"
                placeholder="紧急联系人电话"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="employeeDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="saveEmployee"
          :loading="savingEmployee"
          >保存</el-button
        >
      </template>
    </el-dialog>

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

    <!-- 员工详情弹窗 -->
    <el-dialog v-model="employeeDetailVisible" title="员工详情" width="600px">
      <el-descriptions :column="2" border v-if="selectedEmployee">
        <el-descriptions-item label="员工编号">{{
          selectedEmployee.employee_code
        }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{
          selectedEmployee.name
        }}</el-descriptions-item>
        <el-descriptions-item label="性别">{{
          getGenderLabel(selectedEmployee.gender)
        }}</el-descriptions-item>
        <el-descriptions-item label="出生日期">{{
          selectedEmployee.birth_date || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="手机号码">{{
          selectedEmployee.phone || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{
          selectedEmployee.email || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="部门">{{
          getDepartmentName(selectedEmployee.department_id)
        }}</el-descriptions-item>
        <el-descriptions-item label="职位">{{
          getPositionName(selectedEmployee.position_id)
        }}</el-descriptions-item>
        <el-descriptions-item label="入职日期">{{
          selectedEmployee.hire_date || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(selectedEmployee.status)" size="small">
            {{ getStatusLabel(selectedEmployee.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="合同类型">{{
          getContractTypeLabel(selectedEmployee.contract_type)
        }}</el-descriptions-item>
        <el-descriptions-item label="证件号码">{{
          selectedEmployee.id_number || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="现居地址" :span="2">{{
          selectedEmployee.address || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="紧急联系人">{{
          selectedEmployee.emergency_contact || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="紧急电话">{{
          selectedEmployee.emergency_phone || "-"
        }}</el-descriptions-item>
      </el-descriptions>
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
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  UserFilled,
  Refresh,
  Plus,
  Search,
  User,
  Clock,
  CircleClose,
  DataLine
} from '@element-plus/icons-vue'
import api from '@/api'

// ============================================================================
// 响应式数据
// ============================================================================

const route = useRoute()
const loading = ref(false)
const validTabs = ['employees', 'departments', 'positions', 'attendance', 'salary']
const activeTab = ref(
  validTabs.includes(route.query.tab) ? route.query.tab : 'employees'
)

// 员工数据
const employees = ref([])
const loadingEmployees = ref(false)
const searchKeyword = ref('')
const departmentFilter = ref('')
const statusFilter = ref('')
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})
const employeeStats = reactive({
  active: 0,
  probation: 0,
  inactive: 0,
  total: 0
})

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

// 弹窗控制
const employeeDialogVisible = ref(false)
const departmentDialogVisible = ref(false)
const positionDialogVisible = ref(false)
const employeeDetailVisible = ref(false)

// 编辑状态
const editingEmployee = ref(null)
const editingDepartment = ref(null)
const editingPosition = ref(null)
const selectedEmployee = ref(null)

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
  status: 'active',
  user_id: null,
  id_number: '',
  contract_type: '',
  address: '',
  emergency_contact: '',
  emergency_phone: ''
})

// 关联登录账号下拉选项（未关联用户 + 当前已关联用户）
const linkedUserOptions = ref([])

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
const savingEmployee = ref(false)
const savingDepartment = ref(false)
const savingPosition = ref(false)

// 表单引用
const employeeFormRef = ref(null)
const departmentFormRef = ref(null)
const positionFormRef = ref(null)

// 表单验证规则
const employeeRules = {
  employee_code: [
    { required: false }
  ],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }]
}

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
    await Promise.all([loadDepartments(), loadPositions(), loadEmployees()])
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

// 加载员工列表
const loadEmployees = async () => {
  loadingEmployees.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize
    }
    if (searchKeyword.value) params.keyword = searchKeyword.value
    if (departmentFilter.value) params.department_id = departmentFilter.value
    if (statusFilter.value) params.status = statusFilter.value

    const data = await api.getHrEmployees(params)
    employees.value = data || []

    // 加载员工统计
    await loadEmployeeStats()
  } catch (error) {
    console.error('加载员工列表失败:', error)
    employees.value = []
  } finally {
    loadingEmployees.value = false
  }
}

// 加载员工统计
const loadEmployeeStats = async () => {
  try {
    const [activeRes, probationRes, inactiveRes] = await Promise.all([
      api.getHrEmployeeCount('active'),
      api.getHrEmployeeCount('probation'),
      api.getHrEmployeeCount('inactive')
    ])
    employeeStats.active = activeRes?.count || 0
    employeeStats.probation = probationRes?.count || 0
    employeeStats.inactive = inactiveRes?.count || 0
    employeeStats.total =
      employeeStats.active + employeeStats.probation + employeeStats.inactive
  } catch (error) {
    console.error('加载员工统计失败:', error)
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

const showPayrollDialog = (record) => {
  editingPayroll.value = record
  payrollForm.overtime_pay = Number(record.overtime_pay || 0)
  payrollForm.bonus = Number(record.bonus || 0)
  payrollForm.social_insurance_personal = Number(record.social_insurance_personal || 0)
  payrollForm.housing_fund_personal = Number(record.housing_fund_personal || 0)
  payrollForm.income_tax = Number(record.income_tax || 0)
  payrollForm.other_deductions = Number(record.other_deductions || 0)
  payrollForm.social_insurance_company = Number(record.social_insurance_company || 0)
  payrollForm.housing_fund_company = Number(record.housing_fund_company || 0)
  payrollForm.pay_date = record.pay_date || ''
  payrollForm.remark = record.remark || ''
  payrollDialogVisible.value = true
}

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

const confirmPayroll = async (record) => {
  try {
    await ElMessageBox.confirm('确认后系统不会再自动覆盖该工资单，是否继续？', '确认工资单', {
      type: 'warning'
    })
    await api.confirmHrPayrollRecord(record.id)
    ElMessage.success('工资单已确认')
    await loadPayroll()
  } catch (error) {
    if (error === 'cancel') return
    console.error('确认工资单失败:', error)
    ElMessage.error(error.response?.data?.message || error.message || '确认工资单失败')
  }
}

const reopenPayroll = async (record) => {
  try {
    await ElMessageBox.confirm('退回草稿后，后续绩效重算可以再次覆盖自动计算字段，是否继续？', '退回草稿', {
      type: 'warning'
    })
    await api.reopenHrPayrollRecord(record.id)
    ElMessage.success('工资单已退回草稿')
    await loadPayroll()
  } catch (error) {
    if (error === 'cancel') return
    console.error('退回工资单失败:', error)
    ElMessage.error(error.response?.data?.message || error.message || '退回工资单失败')
  }
}

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
      department_id: employee.department_id,
      position_id: employee.position_id,
      hire_date: employee.hire_date || '',
      status: employee.status,
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
      status: 'active',
      user_id: null,
      id_number: '',
      contract_type: '',
      address: '',
      emergency_contact: '',
      emergency_phone: ''
    })
  }
  try {
    const res = await usersApi.getUnlinkedUsers()
    const list = res?.data ?? res
    const arr = Array.isArray(list) ? list : (list ?? [])
    linkedUserOptions.value = [...arr]
    if (employee?.user_id && employee?.username) {
      const has = linkedUserOptions.value.some((u) => u.id === employee.user_id)
      if (!has) {
        linkedUserOptions.value = [{ id: employee.user_id, username: employee.username, email: '' }, ...linkedUserOptions.value]
      }
    }
  } catch (e) {
    linkedUserOptions.value = []
    if (employee?.user_id && employee?.username) {
      linkedUserOptions.value = [{ id: employee.user_id, username: employee.username, email: '' }]
    }
  }
  employeeDialogVisible.value = true
}

/** 提交前清洗：空字符串转 null，避免后端 422；创建时不传员工编号由后端自动生成 */
function cleanEmployeePayload(isCreate) {
  const raw = { ...employeeForm }
  const cleaned = {}
  for (const [k, v] of Object.entries(raw)) {
    if (v === '' || v === undefined) {
      cleaned[k] = null
    } else if (typeof v === 'string' && v.trim() === '') {
      cleaned[k] = null
    } else {
      cleaned[k] = v
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
    ElMessage.error(error.response?.data?.detail || error.message || '保存失败')
  } finally {
    savingEmployee.value = false
  }
}

const deleteEmployee = async (employee) => {
  try {
    await api.deleteHrEmployee(employee.employee_code)
    ElMessage.success('员工已删除')
    await loadEmployees()
  } catch (error) {
    console.error('删除员工失败:', error)
    ElMessage.error(error.message || '删除失败')
  }
}

const viewEmployeeDetail = (employee) => {
  selectedEmployee.value = employee
  employeeDetailVisible.value = true
}

const resetFilters = () => {
  searchKeyword.value = ''
  departmentFilter.value = ''
  statusFilter.value = ''
  pagination.page = 1
  loadEmployees()
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

const getDepartmentName = (departmentId) => {
  if (!departmentId) return '-'
  const dept = departments.value.find((d) => d.id === departmentId)
  return dept?.department_name || '-'
}

const getPositionName = (positionId) => {
  if (!positionId) return '-'
  const pos = positions.value.find((p) => p.id === positionId)
  return pos?.position_name || '-'
}

const getEmployeeName = (employeeCode) => {
  const emp = employees.value.find((e) => e.employee_code === employeeCode)
  return emp?.name || employeeCode
}

const getStatusType = (status) => {
  const map = { active: 'success', inactive: 'danger', probation: 'warning' }
  return map[status] || 'info'
}

const getStatusLabel = (status) => {
  const map = { active: '在职', inactive: '已离职', probation: '试用期' }
  return map[status] || status
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

const getPayrollStatusType = (status) => {
  const map = { draft: 'info', confirmed: 'warning', paid: 'success' }
  return map[status] || 'info'
}

const getPayrollStatusLabel = (status) => {
  const map = { draft: '草稿', confirmed: '已确认', paid: '已发放' }
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
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.departments-content :deep(.el-table__header-wrapper th:nth-child(7)),
.departments-content :deep(.el-table__header-wrapper th:nth-child(8)),
.departments-content :deep(.el-table__body-wrapper td:nth-child(7)),
.departments-content :deep(.el-table__body-wrapper td:nth-child(8)) {
  display: none;
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
  align-items: center;
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

.search-filters {
  margin-bottom: 16px;
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
