<template>
  <div class="performance-management erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">绩效管理</h1>
    <p style="color: #909399; margin-bottom: 20px;">用于查看店铺/人员绩效、执行月度重算、维护绩效权重，以及录入个人绩效调整项。</p>
    
    <!-- 操作栏：月份、维度切换与功能按钮 -->
    <div class="action-bar" style="margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
      <el-date-picker
        v-model="filters.period"
        type="month"
        format="YYYY-MM"
        value-format="YYYY-MM"
        placeholder="选择月份"
        size="default"
        style="width: 180px;"
        @change="handlePeriodChange"
      />
      <el-radio-group v-model="filters.groupBy" size="default" @change="handleGroupByChange">
        <el-radio-button value="shop">按店铺</el-radio-button>
        <el-radio-button value="person">按人员</el-radio-button>
      </el-radio-group>
      <el-button :icon="Refresh" @click="handleRefreshAll">刷新</el-button>
      <el-button
        type="warning"
        :loading="calculating"
        @click="handleRecalculate"
        v-if="hasPermission('performance:config')"
      >
        重新计算
      </el-button>
      <el-button type="primary" :icon="Setting" @click="handleConfig" v-if="hasPermission('performance:config')">
        配置权重
      </el-button>
      <el-button :icon="Download" @click="handleExport" v-if="hasPermission('performance:export')">导出报表</el-button>
      <el-select v-if="filters.groupBy === 'shop'" v-model="poolFilter" size="default" style="width: 120px;" @change="() => {}">
        <el-option label="全部池" value="all" />
        <el-option label="正式池" value="official" />
        <el-option label="观察池" value="observation" />
      </el-select>
      <el-select v-if="filters.groupBy === 'shop'" v-model="alertFilter" size="default" style="width: 130px;" @change="() => {}">
        <el-option label="全部预警" value="all" />
        <el-option label="无预警" value="none" />
        <el-option label="黄牌" value="yellow" />
        <el-option label="红牌" value="red" />
        <el-option label="淘汰评估" value="elimination" />
      </el-select>
      <el-select v-if="filters.groupBy === 'shop'" v-model="filters.platform" placeholder="选择平台" clearable size="default" style="width: 140px; margin-left: auto;" @change="loadPerformanceList">
        <el-option label="全部平台" value="" />
        <el-option label="Shopee" value="Shopee" />
        <el-option label="Lazada" value="Lazada" />
      </el-select>
    </div>

    <el-card shadow="never" class="policy-card">
      <template #header>
        <div class="card-header">
          <span>口径说明</span>
        </div>
      </template>
      <div class="policy-grid">
        <div class="policy-item">
          <div class="policy-label">赛马池</div>
          <div class="policy-text">正式池参与公司总榜赛马并生成系数；观察池仅展示绩效，不参与正式奖惩。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">预警规则</div>
          <div class="policy-text">绩效分低于 70 为黄牌，低于 60 为红牌；连续红牌达到条件时升级为淘汰评估。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">{{ filters.groupBy === 'person' ? '人员维度' : '店铺维度' }}</div>
          <div class="policy-text">{{ currentGroupPolicyText }}</div>
        </div>
      </div>
    </el-card>
    
    <!-- 绩效表格 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>绩效管理视图</span>
          <div style="font-size: 12px; color: #909399;">
            绩效构成：{{ formulaText }}
          </div>
        </div>
      </template>
      
      <el-table :data="filteredPerformanceData" stripe v-loading="performanceList.loading" class="erp-table" border>
        <el-table-column :prop="filters.groupBy === 'person' ? 'employee_name' : 'shop_name'" :label="filters.groupBy === 'person' ? '人员' : '店铺'" width="180" fixed="left" show-overflow-tooltip>
          <template #default="{ row }">{{ filters.groupBy === 'person' ? (row.employee_name || row.employee_code || '—') : (row.shop_name || row.shop_id || '—') }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额目标" width="110" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_target) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额达成" width="110" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额达成率" width="120" align="right">
          <template #default="{ row }">{{ formatPercent(row.sales_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额得分" width="100" align="right">
          <template #default="{ row }">{{ row.sales_score != null ? Number(row.sales_score).toFixed(1) : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利目标" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.profit_target) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利达成" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.profit_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利达成率" width="110" align="right">
          <template #default="{ row }">{{ formatPercent(row.profit_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利得分" width="90" align="right">
          <template #default="{ row }">{{ row.profit_score != null ? Number(row.profit_score).toFixed(1) : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="重点产品目标" width="120" align="right">
          <template #default="{ row }">{{ formatCell(row.key_product_target) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="重点产品达成" width="120" align="right">
          <template #default="{ row }">{{ formatCell(row.key_product_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="重点产品达成率" width="130" align="right">
          <template #default="{ row }">{{ formatPercent(row.key_product_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="重点产品得分" width="110" align="right">
          <template #default="{ row }">{{ row.key_product_score != null ? Number(row.key_product_score).toFixed(1) : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" prop="operation_score" label="店铺运营得分" width="120" align="right" sortable>
          <template #default="{ row }">{{ row.operation_score != null ? Number(row.operation_score).toFixed(1) : '—' }}</template>
        </el-table-column>

        <el-table-column v-if="filters.groupBy === 'person'" label="实际销售额" width="120" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'person'" label="店铺汇总达成率" width="140" align="right">
          <template #default="{ row }">{{ formatPercent(row.sales_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'person'" label="个人运营加减分(人工)" width="160" align="right">
          <template #default="{ row }">
            <el-tag v-if="row.personal_adjustment_total != null" :type="Number(row.personal_adjustment_total || 0) >= 0 ? 'success' : 'danger'" size="small">
              {{ Number(row.personal_adjustment_total || 0) > 0 ? '+' : '' }}{{ Number(row.personal_adjustment_total || 0).toFixed(1) }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>

        <el-table-column prop="total_score" :label="filters.groupBy === 'person' ? '个人绩效总分' : '总分'" width="120" align="right" sortable>
          <template #default="{ row }">
            <el-tag v-if="row.total_score != null" :type="row.total_score >= 90 ? 'success' : row.total_score >= 80 ? 'warning' : 'danger'" size="small">{{ Number(row.total_score).toFixed(1) }}</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="rank" label="排名" width="80" align="center" sortable>
          <template #default="{ row }">{{ row.rank != null ? `第${row.rank}名` : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" prop="performance_coefficient" label="绩效系数" width="100" align="right" sortable>
          <template #default="{ row }">{{ row.performance_coefficient != null ? Number(row.performance_coefficient).toFixed(2) : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="赛马池" width="100" align="center">
          <template #default="{ row }">{{ rankingPoolText(row) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="预警" width="120" align="center">
          <template #default="{ row }">{{ performanceAlertText(row) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handleViewDetail(row)" v-if="row.platform_code && row.shop_id">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <div v-if="performanceList.data.length === 0 && !performanceList.loading" style="padding: 40px; text-align: center; color: #909399;">
        <template v-if="loadError">查询失败，请稍后重试或联系管理员。</template>
        <template v-else>
          <div style="margin-bottom: 12px;">暂无绩效数据，请选择月份并确认已执行绩效计算。</div>
          <el-button type="warning" :loading="calculating" @click="handleRecalculate" v-if="hasPermission('performance:config')">
            重新计算当月绩效
          </el-button>
        </template>
      </div>
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
    
    <!-- 绩效详情 -->


    <el-card v-if="hasPermission('performance:config') && filters.groupBy === 'person'" style="margin-top: 20px;">
      <template #header>
        <div class="card-header">
          <span>个人绩效调整项</span>
          <div class="card-actions">
            <el-button size="small" @click="loadAdjustmentList">刷新</el-button>
            <el-button size="small" type="primary" @click="openCreateAdjustment">新增调整项</el-button>
          </div>
        </div>
      </template>
      <el-table :data="adjustmentList.data" stripe v-loading="adjustmentList.loading" class="erp-table" border>
        <el-table-column prop="employee_name" label="人员" width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.employee_name || row.employee_code || '—' }}</template>
        </el-table-column>
        <el-table-column prop="year_month" label="月份" width="100" />
        <el-table-column prop="adjustment_type" label="调整类型" width="140" />
        <el-table-column prop="score_delta" label="分值变化" width="100" align="right">
          <template #default="{ row }">
            <el-tag :type="Number(row.score_delta || 0) >= 0 ? 'success' : 'danger'" size="small">
              {{ Number(row.score_delta || 0) > 0 ? '+' : '' }}{{ Number(row.score_delta || 0).toFixed(1) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="140" show-overflow-tooltip />
        <el-table-column prop="reason" label="原因/备注" min-width="220" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEditAdjustment(row)">编辑</el-button>
            <el-button size="small" type="danger" link @click="handleDeleteAdjustment(row)">停用</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="adjustmentList.data.length === 0 && !adjustmentList.loading" class="empty-state small">
        当前月份暂无个人绩效调整项。
      </div>
    </el-card>

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
            <el-tag :type="performanceDetail.data.total_score != null ? (performanceDetail.data.total_score >= 90 ? 'success' : performanceDetail.data.total_score >= 80 ? 'warning' : 'danger') : 'info'" size="large">
              {{ performanceDetail.data.total_score != null ? performanceDetail.data.total_score.toFixed(1) : '未完成' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="排名">
            <el-tag :type="performanceDetail.data.rank === 1 ? 'success' : performanceDetail.data.rank === 2 ? 'warning' : performanceDetail.data.rank === 3 ? 'info' : 'info'" size="small">
              {{ performanceDetail.data.rank != null ? `第${performanceDetail.data.rank}名` : '未参与正式赛马' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="绩效系数">
            <el-tag :type="performanceDetail.data.performance_coefficient != null ? (performanceDetail.data.performance_coefficient >= 1.2 ? 'success' : performanceDetail.data.performance_coefficient >= 1.0 ? 'warning' : 'danger') : 'info'" size="small">
              {{ performanceDetail.data.performance_coefficient != null ? performanceDetail.data.performance_coefficient.toFixed(2) : '未完成' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="赛马池">{{ rankingPoolText(performanceDetail.data) }}</el-descriptions-item>
          <el-descriptions-item label="预警">{{ performanceAlertText(performanceDetail.data) }}</el-descriptions-item>
        </el-descriptions>
        
        <el-card style="margin-top: 20px;">
          <template #header>
            <span>得分详情</span>
          </template>
          <el-card
            v-for="card in detailMetricCards"
            :key="card.key"
            shadow="never"
            style="margin-bottom: 15px;"
          >
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <span style="font-weight: bold;">{{ card.label }}（权重 {{ card.weight }}%）</span>
              <el-tag :type="metricTagType(card.metric, card.successThreshold, card.warningThreshold)" size="small">
                {{ metricScoreText(card.metric) }}
              </el-tag>
            </div>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="状态">{{ isMetricCalculated(card.metric) ? '已计算' : '未就绪' }}</el-descriptions-item>
              <el-descriptions-item label="数据来源">{{ card.metric?.source || '—' }}</el-descriptions-item>
              <el-descriptions-item label="目标">{{ metricValueText(card.metric, 'target', card.targetType) }}</el-descriptions-item>
              <el-descriptions-item label="达成">{{ metricValueText(card.metric, 'achieved', card.achievedType) }}</el-descriptions-item>
              <el-descriptions-item label="达成率">{{ metricValueText(card.metric, 'rate', 'percent') }}</el-descriptions-item>
              <el-descriptions-item label="说明">{{ metricMessageText(card.metric) }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-card>
      </div>
    </el-dialog>
    
    <!-- 绩效权重配置 -->
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
        <el-divider content-position="left">得分比例说明（达成率 &gt; 100% 按满分计算，≤100% 按达成率乘满分）</el-divider>
        <el-form-item label="销售额满分" prop="sales_max_score">
          <el-input-number v-model="configForm.sales_max_score" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="毛利满分" prop="profit_max_score">
          <el-input-number v-model="configForm.profit_max_score" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="重点产品满分" prop="key_product_max_score">
          <el-input-number v-model="configForm.key_product_max_score" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="运营满分" prop="operation_max_score">
          <el-input-number v-model="configForm.operation_max_score" :min="0" :max="100" :precision="0" style="width: 100%;" />
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

    <el-dialog
      v-model="adjustmentDialogVisible"
      :title="adjustmentMode === 'create' ? '新增个人绩效调整项' : '编辑个人绩效调整项'"
      width="520px"
    >
      <el-form :model="adjustmentForm" label-width="110px">
        <el-form-item label="月份"><el-input v-model="adjustmentForm.year_month" disabled /></el-form-item>
        <el-form-item label="人员" required>
          <el-select v-model="adjustmentForm.employee_code" filterable placeholder="选择人员" style="width: 100%;">
            <el-option v-for="employee in adjustmentEmployeeOptions" :key="employee.employee_code" :label="`${employee.name} (${employee.employee_code})`" :value="employee.employee_code" />
          </el-select>
        </el-form-item>
        <el-form-item label="调整类型" required>
          <el-select v-model="adjustmentForm.adjustment_type" placeholder="选择调整类型" style="width: 100%;">
            <el-option label="考试" value="exam_score" />
            <el-option label="培训检核" value="training_check" />
            <el-option label="人工奖惩" value="manual_other" />
            <el-option label="考勤扣分" value="attendance_penalty" />
          </el-select>
        </el-form-item>
        <el-form-item label="分值变化" required><el-input-number v-model="adjustmentForm.score_delta" :min="-100" :max="100" :step="0.5" :precision="1" style="width: 100%;" /></el-form-item>
        <el-form-item label="来源"><el-input v-model="adjustmentForm.source" placeholder="例如 manual_exam / training_review" /></el-form-item>
        <el-form-item label="原因/备注"><el-input v-model="adjustmentForm.reason" type="textarea" :rows="3" placeholder="填写本次调整原因" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustmentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="adjustmentSubmitting" @click="handleSubmitAdjustment">保存</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Setting, Download } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import api from '@/api'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatNumber, formatPercent, formatInteger } from '@/utils/dataFormatter'
import { formatPayrollLockedConflictSummary } from '@/utils/payrollConflict'

const userStore = useUserStore()

// 角色编码规范化（中文角色 -> 英文角色）
const normalizeRoleCode = (role) => {
  if (!role) return ''
  const map = { 管理员: 'admin', 主管: 'manager', 经理: 'manager', 操作员: 'operator', 运营: 'operator', 财务: 'finance' }
  return map[role] || role
}

// 权限检查：优先基于当前激活角色，其次回退到用户全部角色
const hasPermission = (permission) => {
  // 获取当前激活角色（与 SimpleAccountSwitcher 保持一致）
  const activeRole = normalizeRoleCode(localStorage.getItem('activeRole'))
  
  // 管理员拥有全部绩效权限
  if (activeRole === 'admin') return true
  
  // 检查用户是否具备管理员角色，即使当前未激活
  const userRoles = (userStore.roles || []).map(normalizeRoleCode)
  if (userRoles.includes('admin')) return true
  
  // 主管只能查看和导出
  if (activeRole === 'manager') {
    return ['performance:read', 'performance:export'].includes(permission)
  }
  
  // 其他角色只保留只读权限
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
  period: new Date().toISOString().slice(0, 7),
  platform: '',
  shopId: null,
  groupBy: 'shop'
})

// 绩效详情
const performanceDetail = reactive({
  data: null,
  loading: false
})

const detailVisible = ref(false)
const poolFilter = ref('all')
const alertFilter = ref('all')
const loadError = ref(false)
const calculating = ref(false)
const configVisible = ref(false)
const configSubmitting = ref(false)
const configFormRef = ref(null)
const employeeDirectory = ref([])
const adjustmentDialogVisible = ref(false)
const adjustmentSubmitting = ref(false)
// 新增/编辑模式
const adjustmentMode = ref('create')

const adjustmentList = reactive({
  data: [],
  total: 0,
  loading: false
})

// 配置表单
const configForm = reactive({
  sales_weight: 30,
  profit_weight: 25,
  key_product_weight: 25,
  operation_weight: 20,
  sales_max_score: 30,
  profit_max_score: 25,
  key_product_max_score: 25,
  operation_max_score: 20
})
const weightConfig = reactive({
  sales_weight: 30,
  profit_weight: 25,
  key_product_weight: 25,
  operation_weight: 20
})
const adjustmentForm = reactive({
  id: null,
  year_month: '',
  employee_code: '',
  adjustment_type: 'exam_score',
  score_delta: 0,
  source: '',
  reason: ''
})

// 总权重计算
const totalWeight = computed(() => {
  return configForm.sales_weight + configForm.profit_weight + 
         configForm.key_product_weight + configForm.operation_weight
})
const formulaText = computed(() => {
  if (filters.groupBy === 'person') {
    return '店铺汇总绩效分 + 个人运营加减分(人工) + 考勤扣分(自动)，最终限制在 0-100'
  }
  return `销售额(${weightConfig.sales_weight}%) + 毛利(${weightConfig.profit_weight}%) + 重点产品(${weightConfig.key_product_weight}%) + 店铺运营得分(${weightConfig.operation_weight}%)`
})

const currentGroupPolicyText = computed(() => {
  if (filters.groupBy === 'person') {
    return '人员绩效总分=挂店店铺绩效聚合 + 个人运营加减分(人工录入，未来可对接飞书) + 考勤扣分(自动)；最终限制在 0-100。'
  }
  return '店铺总分由销售、毛利、重点产品和运营四项组成；正式池店铺按公司总榜排名并叠加分数底线生成赛马系数。'
})

// 表单验证规则
const adjustmentEmployeeOptions = computed(() => {
  return (employeeDirectory.value || []).filter((item) => !item.status || item.status === 'active')
})

const configRules = {
  sales_weight: [
    { required: true, message: '销售额权重不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '权重范围为 0-100', trigger: 'blur' }
  ],
  profit_weight: [
    { required: true, message: '毛利权重不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '权重范围为 0-100', trigger: 'blur' }
  ],
  key_product_weight: [
    { required: true, message: '重点产品权重不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '权重范围为 0-100', trigger: 'blur' }
  ],
  operation_weight: [
    { required: true, message: '运营权重不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '权重范围为 0-100', trigger: 'blur' }
  ]
}

function formatCell(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return String(v)
}

// 加载绩效列表
function isMetricCalculated(metric) {
  return metric?.status === 'calculated'
}

function metricTagType(metric, successThreshold, warningThreshold) {
  if (!isMetricCalculated(metric)) return 'info'
  const score = Number(metric?.score || 0)
  if (score >= successThreshold) return 'success'
  if (score >= warningThreshold) return 'warning'
  return 'danger'
}

function metricScoreText(metric) {
  if (!isMetricCalculated(metric) || metric?.score == null) return '未就绪'
  return `${Number(metric.score).toFixed(1)}分`
}

function metricValueText(metric, field, valueType = 'text') {
  const value = metric?.[field]
  if (value == null || value === '') return '—'
  if (valueType === 'currency') return formatCurrency(value)
  if (valueType === 'percent') return formatPercent(value)
  if (typeof value === 'number') return Number(value).toFixed(1)
  return String(value)
}

function metricMessageText(metric) {
  return metric?.calculation || metric?.message || '—'
}

function rankingPoolText(row) {
  const status = row?.score_details?.summary?.ranking_pool_status
  if (status === 'official') return '正式池'
  if (status === 'observation') return '观察池'
  return '—'
}

function performanceAlertText(row) {
  const level = row?.score_details?.summary?.performance_alert_level
  const types = row?.score_details?.summary?.performance_alert_types || []
  if (types.includes('performance_elimination_review')) return '淘汰评估'
  if (level === 'critical') return '红牌'
  if (level === 'warning') return '黄牌'
  return '—'
}

const filteredPerformanceData = computed(() => {
  if (filters.groupBy !== 'shop') {
    return performanceList.data || []
  }
  return (performanceList.data || []).filter((row) => {
    const pool = row?.score_details?.summary?.ranking_pool_status || 'unknown'
    const alertTypes = row?.score_details?.summary?.performance_alert_types || []
    const alert = alertTypes.includes('performance_elimination_review')
      ? 'elimination'
      : alertTypes.includes('performance_red_card')
        ? 'red'
        : alertTypes.includes('performance_yellow_card')
          ? 'yellow'
          : 'none'
    const poolOk = poolFilter.value === 'all' || pool === poolFilter.value
    const alertOk = alertFilter.value === 'all' || alert === alertFilter.value
    return poolOk && alertOk
  })
})

const detailMetricCards = computed(() => {
  const data = performanceDetail.data || {}
  return [
    {
      key: 'sales_score',
      label: '销售额得分',
      weight: weightConfig.sales_weight,
      metric: data.sales_score,
      successThreshold: 27,
      warningThreshold: 24,
      targetType: 'currency',
      achievedType: 'currency',
    },
    {
      key: 'profit_score',
      label: '毛利得分',
      weight: weightConfig.profit_weight,
      metric: data.profit_score,
      successThreshold: 22.5,
      warningThreshold: 20,
      targetType: 'currency',
      achievedType: 'currency',
    },
    {
      key: 'key_product_score',
      label: '重点产品得分',
      weight: weightConfig.key_product_weight,
      metric: data.key_product_score,
      successThreshold: 22.5,
      warningThreshold: 20,
      targetType: 'text',
      achievedType: 'text',
    },
    {
      key: 'operation_score',
      label: '店铺运营得分',
      weight: weightConfig.operation_weight,
      metric: data.operation_score,
      successThreshold: 18,
      warningThreshold: 16,
      targetType: 'text',
      achievedType: 'text',
    },
  ]
})

const loadPerformanceList = async () => {
  performanceList.loading = true
  loadError.value = false
  try {
    const period = typeof filters.period === 'string' ? filters.period : 
      (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : undefined)
    
    const response = await api.getPerformanceScores({
      period,
      platform: filters.platform || undefined,
      shop_id: filters.shopId || undefined,
      group_by: filters.groupBy,
      page: performanceList.page,
      page_size: performanceList.pageSize
    })
    
    // 兼容分页响应结构
    if (response && Array.isArray(response)) {
      performanceList.data = response
      performanceList.total = response.length
    } else {
      performanceList.data = response?.data || response || []
      performanceList.total = response?.total || 0
    }
  } catch (error) {
    loadError.value = true
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    performanceList.loading = false
  }
}

const loadWeightConfig = async () => {
  try {
    const response = await api.getPerformanceConfigs({ is_active: true, page: 1, page_size: 1 })
    const row = Array.isArray(response)
      ? response[0]
      : (response?.data?.[0] || response?.data || response)
    if (!row) return
    weightConfig.sales_weight = row.sales_weight ?? weightConfig.sales_weight
    weightConfig.profit_weight = row.profit_weight ?? weightConfig.profit_weight
    weightConfig.key_product_weight = row.key_product_weight ?? weightConfig.key_product_weight
    weightConfig.operation_weight = row.operation_weight ?? weightConfig.operation_weight
  } catch (error) {
    // 配置读取失败时不阻塞页面加载
  }
}

const loadEmployeeDirectory = async () => {
  if (!hasPermission('performance:config')) return
  try {
    const response = await api.getHrEmployees({ page: 1, page_size: 500 })
    const data = Array.isArray(response) ? response : (response?.items || response?.data?.items || response?.data || [])
    employeeDirectory.value = Array.isArray(data) ? data : []
  } catch (error) {
    employeeDirectory.value = []
  }
}

const loadAdjustmentList = async () => {
  if (!hasPermission('performance:config')) return
  adjustmentList.loading = true
  try {
    const response = await api.getHrPerformanceAdjustments({
      year_month: typeof filters.period === 'string' ? filters.period : undefined,
      page: 1,
      page_size: 100
    })
    adjustmentList.data = response?.items || []
    adjustmentList.total = response?.total || 0
  } catch (error) {
    adjustmentList.data = []
    adjustmentList.total = 0
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    adjustmentList.loading = false
  }
}

const handleRefreshAll = async () => {
  await loadPerformanceList()
  if (filters.groupBy === 'person') {
    await loadAdjustmentList()
  }
}

const handleGroupByChange = async () => {
  await loadPerformanceList()
  if (filters.groupBy === 'person') {
    await loadAdjustmentList()
  }
}

const handlePeriodChange = async () => {
  await handleRefreshAll()
}

const resetAdjustmentForm = () => {
  adjustmentForm.id = null
  adjustmentForm.year_month = typeof filters.period === 'string' ? filters.period : ''
  adjustmentForm.employee_code = ''
  adjustmentForm.adjustment_type = 'exam_score'
  adjustmentForm.score_delta = 0
  adjustmentForm.source = ''
  adjustmentForm.reason = ''
}

const openCreateAdjustment = () => {
  adjustmentMode.value = 'create'
  resetAdjustmentForm()
  adjustmentDialogVisible.value = true
}

const openEditAdjustment = (row) => {
  adjustmentMode.value = 'edit'
  adjustmentForm.id = row.id
  adjustmentForm.year_month = row.year_month
  adjustmentForm.employee_code = row.employee_code
  adjustmentForm.adjustment_type = row.adjustment_type
  adjustmentForm.score_delta = Number(row.score_delta || 0)
  adjustmentForm.source = row.source || ''
  adjustmentForm.reason = row.reason || ''
  adjustmentDialogVisible.value = true
}

const handleSubmitAdjustment = async () => {
  if (!adjustmentForm.year_month) {
    ElMessage.warning('请选择月份')
    return
  }
  if (!adjustmentForm.employee_code) {
    ElMessage.warning('请选择人员')
    return
  }
  adjustmentSubmitting.value = true
  try {
    const payload = {
      year_month: adjustmentForm.year_month,
      employee_code: adjustmentForm.employee_code,
      adjustment_type: adjustmentForm.adjustment_type,
      score_delta: Number(adjustmentForm.score_delta || 0),
      source: adjustmentForm.source || null,
      reason: adjustmentForm.reason || null
    }
    if (adjustmentMode.value === 'create') {
      await api.createHrPerformanceAdjustment(payload)
    } else {
      await api.updateHrPerformanceAdjustment(adjustmentForm.id, payload)
    }
    ElMessage.success('个人绩效调整项保存成功')
    adjustmentDialogVisible.value = false
    await loadAdjustmentList()
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    adjustmentSubmitting.value = false
  }
}

const handleDeleteAdjustment = async (row) => {
  try {
    await ElMessageBox.confirm('确认停用该个人绩效调整项吗？', '确认停用', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await api.deleteHrPerformanceAdjustment(row.id)
    ElMessage.success('已停用该调整项')
    await loadAdjustmentList()
  } catch (error) {
    if (error !== 'cancel') {
      handleApiError(error, { showMessage: true, logError: true })
    }
  }
}

const handleRecalculate = async () => {
  const period = typeof filters.period === 'string'
    ? filters.period
    : (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : '')
  if (!period) {
    ElMessage.warning('请选择考核月份')
    return
  }
  calculating.value = true
  try {
    const result = await api.calculatePerformanceScores(period)
    ElMessage.success('已完成当月店铺绩效、个人绩效和提成重算，请刷新查看最新结果')
    const lockedConflicts = result?.payroll_locked_conflicts || 0
    const conflictDetails = result?.payroll_locked_conflict_details || []
    if (lockedConflicts > 0) {
      const summary = formatPayrollLockedConflictSummary(conflictDetails, lockedConflicts)
      await ElMessageBox.alert(summary, '工资单锁定冲突', {
        type: 'warning',
        confirmButtonText: '知道了'
      })
    }
    await handleRefreshAll()
  } catch (error) {
    const code = error?.response?.data?.data?.error_code
    if (code === 'PERF_CALC_NOT_READY') {
      ElMessage.warning('绩效计算能力未就绪，请先完成 PostgreSQL 数据链路与目标分解配置')
    } else if (code === 'PERF_CONFIG_NOT_FOUND') {
      ElMessage.warning('当前考核周期无可用绩效配置，请先配置权重和生效周期')
    } else {
      handleApiError(error, { showMessage: true, logError: true })
    }
  } finally {
    calculating.value = false
  }
}

// 查看详情
const handleViewDetail = async (row) => {
  detailVisible.value = true
  performanceDetail.loading = true
  try {
    const period = typeof filters.period === 'string' ? filters.period : 
      (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : undefined)
    const response = await api.getShopPerformanceDetail(row.platform_code, row.shop_id, period)
    performanceDetail.data = response?.data ?? response ?? {}
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    performanceDetail.loading = false
  }
}

// 配置权重
const handleConfig = async () => {
  const response = await api.getPerformanceConfigs({})
  // 兼容列表响应，取第一条有效配置
  const setForm = (config) => {
    configForm.sales_weight = config.sales_weight ?? 30
    configForm.profit_weight = config.profit_weight ?? 25
    configForm.key_product_weight = config.key_product_weight ?? 25
    configForm.operation_weight = config.operation_weight ?? 20
    configForm.sales_max_score = config.sales_max_score ?? 30
    configForm.profit_max_score = config.profit_max_score ?? 25
    configForm.key_product_max_score = config.key_product_max_score ?? 25
    configForm.operation_max_score = config.operation_max_score ?? 20
  }
  if (response && Array.isArray(response) && response.length > 0) {
    setForm(response[0])
  } else if (response && response.pagination && response.data && response.data.length > 0) {
    setForm(response.data[0])
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
    // 当前先沿用新增配置的方式，后续可切换为显式更新
    await api.createPerformanceConfig({
      sales_weight: configForm.sales_weight,
      profit_weight: configForm.profit_weight,
      key_product_weight: configForm.key_product_weight,
      operation_weight: configForm.operation_weight,
      sales_max_score: configForm.sales_max_score,
      profit_max_score: configForm.profit_max_score,
      key_product_max_score: configForm.key_product_max_score,
      operation_max_score: configForm.operation_max_score,
      effective_from: new Date().toISOString().slice(0, 10)
    })
    
    ElMessage.success('配置更新成功')
    configVisible.value = false
    await loadWeightConfig()
    await loadPerformanceList()
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
  ElMessage.info('导出功能开发中（当前为占位实现）')
  // TODO: 实现 Excel 导出功能
}

// formatCurrency 已从 dataFormatter 导入，无需重复声明

onMounted(async () => {
  await loadWeightConfig()
  await loadEmployeeDirectory()
  await handleRefreshAll()
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

.policy-card {
  margin-bottom: 20px;
}

.policy-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.policy-item {
  padding: 12px 14px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}

.policy-label {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.policy-text {
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

/* 浼佷笟绾ц〃鏍兼牱寮?*/
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


