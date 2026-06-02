<template>
  <div class="expense-management erp-page-container erp-page--admin">
    <PageHeader
      title="费用管理"
      subtitle="按月份或按店铺维护费用数据。该模块中的相关费用列统一表示营销费用，不再作为员工工资录入入口。"
      family="admin"
    />

    <!-- 模式切换 Tab -->
    <el-tabs
      v-model="viewMode"
      @tab-change="handleModeChange"
      class="erp-mb-lg"
    >
      <el-tab-pane label="按月份查看" name="monthly">
        <template #label>
          <span
            ><el-icon><Calendar /></el-icon> 按月份查看</span
          >
        </template>
      </el-tab-pane>
      <el-tab-pane label="按店铺查看" name="shop">
        <template #label>
          <span
            ><el-icon><Shop /></el-icon> 按店铺查看</span
          >
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- 按月份查看模式 -->
    <div v-if="viewMode === 'monthly'">
      <!-- 操作栏 -->
      <div class="action-bar erp-mb-lg">
        <el-date-picker
          v-model="selectedMonth"
          type="month"
          placeholder="选择月份"
          value-format="YYYY-MM"
          size="default"
          class="erp-w-180"
          @change="handleMonthChange"
        />
        <el-button
          type="primary"
          @click="openQuickSplitDialog"
          class="erp-ml-sm"
        >
          快速拆分
        </el-button>
        <el-button
          type="success"
          @click="handleBatchSave"
          :loading="batchSaving"
          class="erp-ml-sm"
        >
          批量保存
        </el-button>
        <el-button
          :icon="Refresh"
          @click="loadMonthlyExpenses"
          class="erp-ml-sm"
        >
          刷新
        </el-button>
        <div class="erp-flex-spacer"></div>
      </div>

      <!-- 统计卡片（月度 + 年度） -->
      <el-row :gutter="20" class="erp-mb-lg">
        <el-col :span="4">
          <el-card class="stat-card monthly">
            <div class="stat-item">
              <div class="stat-label">本月总费用</div>
              <div class="stat-value primary">
                {{ formatNumber(monthlySummary.total_amount) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card class="stat-card yearly">
            <div class="stat-item">
              <div class="stat-label">年度累计</div>
              <div class="stat-value warning">
                {{ formatNumber(yearlySummary.total_amount) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月租金</div>
              <div class="stat-value">
                {{ formatNumber(monthlySummary.total_rent) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月营销费用</div>
              <div class="stat-value">
                {{ formatNumber(monthlySummary.total_marketing_fee) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月水电</div>
              <div class="stat-value">
                {{ formatNumber(monthlySummary.total_utilities) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月其他</div>
              <div class="stat-value">
                {{ formatNumber(monthlySummary.total_other) }}
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 月度费用表格 -->
      <el-card>
        <!-- 错误状态显示 -->
        <div v-if="monthlyError && !loading" class="error-state">
          <el-result icon="error" :title="monthlyError.message">
            <template #sub-title>
              <span>{{ monthlyError.recovery }}</span>
            </template>
            <template #extra>
              <el-button type="primary" @click="loadMonthlyExpenses">重新加载</el-button>
            </template>
          </el-result>
        </div>

        <!-- 正常表格（无错误时显示） -->
        <el-table
          v-if="!monthlyError"
          :data="monthlyTableData"
          stripe
          v-loading="loading"
          class="erp-table"
          border
        >
          <el-table-column
            prop="shop_name"
            label="店铺"
            width="200"
            fixed="left"
          >
            <template #default="{ row }">
              <el-select
                v-model="row.shop_id"
                placeholder="选择店铺"
                class="erp-w-full"
                :disabled="!!row.id"
                @change="handleShopChange(row)"
              >
                <el-option
                  v-for="shop in availableShops"
                  :key="shop.shop_id"
                  :label="shop.option_label || shop.shop_name"
                  :value="shop.shop_id"
                >
                  <div>{{ shop.shop_name }}</div>
                  <div v-if="shop.secondary_name" class="shop-option-secondary">{{ shop.secondary_name }}</div>
                </el-option>
              </el-select>
            </template>
          </el-table-column>
          <el-table-column
            prop="rent"
            label="租金"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.rent"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="marketing_fee"
            label="营销费用"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.marketing_fee"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="utilities"
            label="水电费"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.utilities"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="ai_token_cost"
            label="AI Token费用"
            width="140"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.ai_token_cost"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="other_costs"
            label="其他费用"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.other_costs"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="220">
            <template #default="{ row }">
              <el-input
                v-model="row.note"
                type="textarea"
                :rows="1"
                autosize
                placeholder="可选"
                @change="() => {}"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="total_cost"
            label="成本合计"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              <strong>{{ formatNumber(row.total_cost ?? row.total) }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.id" type="success" size="small">已保存</el-tag>
              <el-tag v-else type="info" size="small">新增</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row, $index }">
              <el-button
                size="small"
                type="primary"
                @click="handleSaveRow(row)"
                :loading="row.saving"
              >
                保存
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="handleDeleteRow(row, $index)"
                :disabled="!row.id"
              >
                删除
              </el-button>
              <el-button
                v-if="row.id"
                size="small"
                type="warning"
                plain
                @click="handleRestoreRow(row)"
              >
                恢复
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="deletedMonthlyData.length" class="erp-mt-md">
          <div class="deleted-expenses-title">已删除费用记录</div>
          <el-table :data="deletedMonthlyData" size="small" border>
            <el-table-column prop="year_month" label="月份" width="110" />
            <el-table-column prop="platform_code" label="平台" width="110" />
            <el-table-column prop="shop_id" label="店铺ID" min-width="180" />
            <el-table-column prop="total_cost" label="成本合计" width="120" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.total_cost) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button size="small" type="warning" plain @click="handleRestoreRow(row)">恢复</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>

      <el-dialog
        v-model="quickSplitDialogVisible"
        title="快速拆分"
        width="520px"
      >
        <div class="quick-split-tip">
          平均分摊到当前全部店铺。应用后会覆盖当前页面现有金额，保存前仍可逐店修改。
        </div>
        <div class="quick-split-meta">当前月份：{{ selectedMonth || '-' }}</div>
        <div class="quick-split-meta">拆分店铺数：{{ monthlyTableData.length }}</div>
        <el-form label-position="top" class="quick-split-form">
          <el-form-item label="总租金">
            <el-input-number
              v-model="quickSplitForm.rent"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
          <el-form-item label="总营销费用">
            <el-input-number
              v-model="quickSplitForm.marketing_fee"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
          <el-form-item label="总水电费">
            <el-input-number
              v-model="quickSplitForm.utilities"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
          <el-form-item label="总AI Token费用">
            <el-input-number
              v-model="quickSplitForm.ai_token_cost"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
          <el-form-item label="总其他费用">
            <el-input-number
              v-model="quickSplitForm.other_costs"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="quickSplitDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleApplyQuickSplit">应用拆分</el-button>
        </template>
      </el-dialog>
    </div>

    <!-- 按店铺查看模式 -->
    <div v-else-if="viewMode === 'shop'">
      <!-- 操作栏 -->
      <div class="action-bar erp-mb-lg">
        <el-select
          v-model="selectedShopId"
          placeholder="选择店铺"
          class="erp-w-250"
          @change="handleShopSelectChange"
          filterable
        >
          <el-option
            v-for="shop in availableShops"
            :key="shop.shop_id"
            :label="shop.option_label || shop.shop_name"
            :value="shop.shop_id"
          >
            <div>{{ shop.shop_name }}</div>
            <div v-if="shop.secondary_name" class="shop-option-secondary">{{ shop.secondary_name }}</div>
          </el-option>
        </el-select>
        <el-date-picker
          v-model="selectedYear"
          type="year"
          placeholder="选择年份"
          value-format="YYYY"
          size="default"
          class="erp-w-150 erp-ml-sm"
          @change="loadShopExpenses"
        />
        <el-button
          :icon="Refresh"
          @click="loadShopExpenses"
          class="erp-ml-sm"
        >
          刷新
        </el-button>
        <div class="erp-flex-spacer"></div>
      </div>

      <!-- 店铺年度汇总卡片 -->
      <el-row :gutter="20" class="erp-mb-lg">
        <el-col :span="4">
          <el-card class="stat-card yearly">
            <div class="stat-item">
              <div class="stat-label">年度总费用</div>
              <div class="stat-value primary">
                {{ formatNumber(shopSummary.total_amount) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">月均费用</div>
              <div class="stat-value">
                {{
                  formatNumber(
                    shopSummary.month_count > 0
                      ? shopSummary.total_amount / shopSummary.month_count
                      : 0,
                  )
                }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度租金</div>
              <div class="stat-value">
                {{ formatNumber(shopSummary.total_rent) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度营销费用</div>
              <div class="stat-value">
                {{ formatNumber(shopSummary.total_marketing_fee) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度水电</div>
              <div class="stat-value">
                {{ formatNumber(shopSummary.total_utilities) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度其他</div>
              <div class="stat-value">
                {{ formatNumber(shopSummary.total_other_costs) }}
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 店铺费用表格（按月份） -->
      <el-card>
        <el-table
          :data="shopTableData"
          stripe
          v-loading="loading"
          class="erp-table"
          border
        >
          <el-table-column
            prop="year_month"
            label="月份"
            width="120"
            fixed="left"
          >
            <template #default="{ row }">
              <el-tag v-if="row.id" type="primary">{{ row.year_month }}</el-tag>
              <el-date-picker
                v-else
                v-model="row.year_month"
                type="month"
                placeholder="选择月份"
                value-format="YYYY-MM"
                size="small"
                class="erp-w-full"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="rent"
            label="租金"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.rent"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="marketing_fee"
            label="营销费用"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.marketing_fee"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="utilities"
            label="水电费"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.utilities"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="ai_token_cost"
            label="AI Token费用"
            width="140"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.ai_token_cost"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="other_costs"
            label="其他费用"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.other_costs"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="220">
            <template #default="{ row }">
              <el-input
                v-model="row.note"
                type="textarea"
                :rows="1"
                autosize
                placeholder="可选"
                @change="() => {}"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="total_cost"
            label="成本合计"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              <strong>{{ formatNumber(row.total_cost ?? row.total) }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.id" type="success" size="small">已保存</el-tag>
              <el-tag v-else type="info" size="small">新增</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row, $index }">
              <el-button
                size="small"
                type="primary"
                @click="handleSaveShopRow(row)"
                :loading="row.saving"
              >
                保存
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="handleDeleteShopRow(row, $index)"
                :disabled="!row.id"
              >
                删除
              </el-button>
              <el-button
                v-if="row.id"
                size="small"
                type="warning"
                plain
                @click="handleRestoreShopRow(row)"
              >
                恢复
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="deletedShopData.length" class="erp-mt-md">
          <div class="deleted-expenses-title">已删除费用记录</div>
          <el-table :data="deletedShopData" size="small" border>
            <el-table-column prop="year_month" label="月份" width="110" />
            <el-table-column prop="platform_code" label="平台" width="110" />
            <el-table-column prop="total_cost" label="成本合计" width="120" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.total_cost) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button size="small" type="warning" plain @click="handleRestoreShopRow(row)">恢复</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 添加新月份按钮 -->
        <div class="erp-mt-md">
          <el-button
            type="primary"
            :icon="Plus"
            @click="handleAddMonthRow"
            :disabled="!selectedShopId"
          >
            添加月份
          </el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Calendar, Shop } from '@element-plus/icons-vue'
import api from '@/api'
import PageHeader from '@/components/common/PageHeader.vue'
import employeeTasksApi from '@/api/employeeTasks.js'
import { buildShopAccountLookup, resolveShopDisplay } from '@/utils/shopDisplay'

const route = useRoute()
let shopAccountLookup = new Map()

// ==================== 公共状态 ====================
const viewMode = ref('monthly') // monthly | shop
const availableShops = ref([])
const loading = ref(false)
const monthlyError = ref(null) // 月度数据加载错误状态
const shopError = ref(null) // 店铺数据加载错误状态

// ==================== 按月份查看模式 ====================
const selectedMonth = ref(null)
const monthlyTableData = ref([])
const batchSaving = ref(false)
const quickSplitDialogVisible = ref(false)
const quickSplitForm = reactive({
  rent: 0,
  marketing_fee: 0,
  utilities: 0,
  ai_token_cost: 0,
  other_costs: 0
})

// 月度汇总
const monthlySummary = reactive({
  total_amount: 0,
  total_rent: 0,
  total_marketing_fee: 0,
  total_utilities: 0,
  total_ai_token_cost: 0,
  total_other: 0
})

// 年度汇总
const yearlySummary = reactive({
  total_amount: 0,
  total_rent: 0,
  total_marketing_fee: 0,
  total_utilities: 0,
  total_ai_token_cost: 0,
  total_other_costs: 0
})

// ==================== 按店铺查看模式 ====================
const selectedShopId = ref(null)
const selectedYear = ref(null)
const shopTableData = ref([])
const deletedMonthlyData = ref([])
const deletedShopData = ref([])

// 店铺汇总
const shopSummary = reactive({
  total_amount: 0,
  total_rent: 0,
  total_marketing_fee: 0,
  total_utilities: 0,
  total_ai_token_cost: 0,
  total_other_costs: 0,
  month_count: 0
})

const taskContext = reactive({
  taskId: '',
  yearMonth: '',
  shopId: '',
  platformCode: ''
})

// ==================== 公共方法 ====================
const formatNumber = (num) => {
  if (num === null || num === undefined) return '0.00'
  return Number(num).toFixed(2)
}

const normalizeExpenseRow = (item = {}) => {
  const marketingFee = Number(item.marketing_fee) || 0
  const aiTokenCost = Number(item.ai_token_cost) || 0
  const displayMeta = resolveShopDisplay(item, shopAccountLookup)
  return {
    ...item,
    platform_code: item.platform_code ?? null,
    marketing_fee: marketingFee,
    ai_token_cost: aiTokenCost,
    note: item.note ?? '',
    total_cost: Number(item.total_cost ?? item.total) || 0,
    shop_name: displayMeta.display_name,
    secondary_name: displayMeta.secondary_name,
    canonical_shop_name: displayMeta.canonical_name,
    option_label: displayMeta.option_label,
    search_text: displayMeta.search_text
  }
}

const buildExpenseRowKey = (row = {}) =>
  `${row.platform_code || ''}|${row.shop_id || ''}`

const isMeaningfulExpenseRow = (row = {}) => {
  const note = String(row.note || '').trim()
  const attachments = Array.isArray(row.attachments) ? row.attachments : []
  return (
    (Number(row.rent) || 0) > 0 ||
    (Number(row.marketing_fee) || 0) > 0 ||
    (Number(row.utilities) || 0) > 0 ||
    (Number(row.ai_token_cost) || 0) > 0 ||
    (Number(row.other_costs) || 0) > 0 ||
    note.length > 0 ||
    attachments.length > 0
  )
}

const initTaskContext = () => {
  taskContext.taskId = typeof route.query.task_id === 'string' ? route.query.task_id : ''
  taskContext.yearMonth = typeof route.query.year_month === 'string' ? route.query.year_month : ''
  taskContext.shopId = typeof route.query.shop_id === 'string' ? route.query.shop_id : ''
  taskContext.platformCode = typeof route.query.platform_code === 'string' ? route.query.platform_code : ''
  if (taskContext.yearMonth) {
    selectedMonth.value = taskContext.yearMonth
  }
}

const tryCompleteTaskFromExpenseRow = async (row, yearMonthOverride = '') => {
  if (!taskContext.taskId) return
  const currentYearMonth = String(yearMonthOverride || row.year_month || selectedMonth.value || '')
  if (currentYearMonth !== String(taskContext.yearMonth || '')) return
  if (String(row.shop_id || '') !== String(taskContext.shopId || '')) return
  await employeeTasksApi.submitTask(taskContext.taskId, {
    completion_payload: {
      year_month: currentYearMonth,
      shop_id: row.shop_id,
      total: Number(row.total) || 0
    },
    result_comment: 'monthly cost entry submitted from expense management',
    requires_confirmation: true
  })
}

// 加载店铺列表
const loadShops = async () => {
  try {
    const [expenseShopsResult, shopDirectoryResult] = await Promise.allSettled([
      api.get('/expenses/shops'),
      api.getShopDirectory({ enabled: true })
    ])
    if (expenseShopsResult.status !== 'fulfilled') {
      throw expenseShopsResult.reason
    }
    const shopDirectory = shopDirectoryResult.status === 'fulfilled' ? shopDirectoryResult.value : []
    shopAccountLookup = buildShopAccountLookup(Array.isArray(shopDirectory) ? shopDirectory : [])
    const expenseShops = expenseShopsResult.value
    const rawShops = Array.isArray(expenseShops)
      ? expenseShops
      : (expenseShops?.data ?? expenseShops ?? [])
    availableShops.value = rawShops.map((shop) => {
      const displayMeta = resolveShopDisplay(shop, shopAccountLookup)
      return {
        ...shop,
        shop_name: displayMeta.display_name,
        secondary_name: displayMeta.secondary_name,
        canonical_shop_name: displayMeta.canonical_name,
        option_label: displayMeta.option_label,
        search_text: displayMeta.search_text
      }
    })
  } catch (error) {
    console.error('加载店铺列表失败:', error)
    ElMessage.error(error.message || '加载店铺列表失败')
    availableShops.value = []
  }
}

// 模式切换处理
const handleModeChange = (mode) => {
  if (mode === 'monthly' && selectedMonth.value) {
    loadMonthlyExpenses()
  } else if (mode === 'shop' && selectedShopId.value) {
    loadShopExpenses()
  }
}

// ==================== 按月份模式方法 ====================

// 加载月度费用
const loadMonthlyExpenses = async () => {
  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }

  loading.value = true
  monthlyError.value = null // 重置错误状态
  try {
    // 并行加载月度数据和年度汇总
    const [monthlyRes, yearlyRes, deletedRes] = await Promise.all([
      api.get('/expenses', {
        params: { year_month: selectedMonth.value, page_size: 1000 }
      }),
      api.get('/expenses/summary/yearly', {
        params: { year: selectedMonth.value.substring(0, 4) }
      }),
      api.get('/expenses/deleted', {
        params: { year_month: selectedMonth.value }
      })
    ])

    // 处理月度数据
    const existingData = monthlyRes.items || []
    const shopKeySet = new Set(existingData.map((item) => buildExpenseRowKey(item)))

    // 为没有数据的店铺创建空白行
    const newRows = availableShops.value
      .filter((shop) => !shopKeySet.has(buildExpenseRowKey(shop)))
      .map((shop) => ({
        id: null,
        platform_code: shop.platform_code,
        shop_id: shop.shop_id,
        shop_name: shop.shop_name,
        year_month: selectedMonth.value,
        rent: 0,
        marketing_fee: 0,
        utilities: 0,
        ai_token_cost: 0,
        other_costs: 0,
        total_cost: 0,
        total: 0,
        note: '',
        attachments: [],
        saving: false
      }))

    // 合并现有数据和空白行，只保留当月数据
    monthlyTableData.value = [
      ...existingData
        .filter((item) => item.year_month === selectedMonth.value)
        .map((item) => ({
          ...normalizeExpenseRow(item),
          shop_name:
            availableShops.value.find((s) => buildExpenseRowKey(s) === buildExpenseRowKey(item))
              ?.shop_name || item.shop_id,
          saving: false
        })),
      ...newRows
    ]

    // 计算月度汇总（只计算已保存的数据）
    calculateMonthlySummary()

    // 更新年度汇总
    if (yearlyRes) {
      yearlySummary.total_amount = yearlyRes.total_amount || 0
      yearlySummary.total_rent = yearlyRes.total_rent || 0
      yearlySummary.total_marketing_fee = yearlyRes.total_marketing_fee || 0
      yearlySummary.total_utilities = yearlyRes.total_utilities || 0
      yearlySummary.total_ai_token_cost = yearlyRes.total_ai_token_cost || 0
      yearlySummary.total_other_costs = yearlyRes.total_other_costs || 0
    }
    deletedMonthlyData.value = deletedRes.items || []
  } catch (error) {
    console.error('加载费用数据失败:', error)
    // 设置错误状态，区分"无数据"和"加载失败"
    monthlyError.value = {
      message: error.message || '加载费用数据失败',
      recovery: error.recovery_suggestion || '请检查网络连接或联系管理员'
    }
    monthlyTableData.value = []
    deletedMonthlyData.value = []
    ElMessage.error(monthlyError.value.message)
  } finally {
    loading.value = false
  }
}

// 计算月度汇总
const calculateMonthlySummary = () => {
  monthlySummary.total_amount = 0
  monthlySummary.total_rent = 0
  monthlySummary.total_marketing_fee = 0
  monthlySummary.total_utilities = 0
  monthlySummary.total_ai_token_cost = 0
  monthlySummary.total_other = 0

  monthlyTableData.value
    .forEach((item) => {
      const rent = Number(item.rent) || 0
      const marketingFee = Number(item.marketing_fee) || 0
      const utilities = Number(item.utilities) || 0
      const aiTokenCost = Number(item.ai_token_cost) || 0
      const otherCosts = Number(item.other_costs) || 0

      monthlySummary.total_amount += rent + marketingFee + utilities + aiTokenCost + otherCosts
      monthlySummary.total_rent += rent
      monthlySummary.total_marketing_fee += marketingFee
      monthlySummary.total_utilities += utilities
      monthlySummary.total_ai_token_cost += aiTokenCost
      monthlySummary.total_other += otherCosts
    })
}

// 更新行合计
const updateRowTotal = (row) => {
  row.total_cost =
    (Number(row.rent) || 0) +
    (Number(row.marketing_fee) || 0) +
    (Number(row.utilities) || 0) +
    (Number(row.ai_token_cost) || 0) +
    (Number(row.other_costs) || 0)
  row.total = row.total_cost
  calculateMonthlySummary()
}

// 店铺选择变化
const handleShopChange = (row) => {
  const shop = availableShops.value.find((s) => s.shop_id === row.shop_id)
  if (shop) {
    row.platform_code = shop.platform_code
    row.shop_name = shop.shop_name
  }
}

// 月份变化
const handleMonthChange = () => {
  if (selectedMonth.value) {
    loadMonthlyExpenses()
  } else {
    monthlyTableData.value = []
    calculateMonthlySummary()
  }
}

const resetQuickSplitForm = () => {
  quickSplitForm.rent = 0
  quickSplitForm.marketing_fee = 0
  quickSplitForm.utilities = 0
  quickSplitForm.other_costs = 0
}

const openQuickSplitDialog = () => {
  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }

  if (monthlyTableData.value.length === 0) {
    ElMessage.warning('当前月份没有可拆分的店铺')
    return
  }

  resetQuickSplitForm()
  quickSplitDialogVisible.value = true
}

const distributeEvenly = (totalAmount, count) => {
  const totalCents = Math.round((Number(totalAmount) || 0) * 100)
  const base = Math.floor(totalCents / count)
  let remainder = totalCents - (base * count)

  return Array.from({ length: count }, () => {
    const extra = remainder > 0 ? 1 : 0
    remainder -= extra
    return (base + extra) / 100
  })
}

const handleApplyQuickSplit = async () => {
  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }

  const rowCount = monthlyTableData.value.length
  if (rowCount === 0) {
    ElMessage.warning('当前月份没有可拆分的店铺')
    return
  }

  try {
    await ElMessageBox.confirm(
      `将按 ${rowCount} 个店铺平均拆分，并覆盖当前页面已有金额。是否继续？`,
      '确认快速拆分',
      { type: 'warning' }
    )
  } catch (error) {
    if (error === 'cancel') {
      return
    }
    throw error
  }

  const rentAllocations = distributeEvenly(quickSplitForm.rent, rowCount)
  const marketingAllocations = distributeEvenly(quickSplitForm.marketing_fee, rowCount)
  const utilityAllocations = distributeEvenly(quickSplitForm.utilities, rowCount)
  const aiTokenAllocations = distributeEvenly(quickSplitForm.ai_token_cost, rowCount)
  const otherAllocations = distributeEvenly(quickSplitForm.other_costs, rowCount)

  monthlyTableData.value.forEach((row, index) => {
    row.rent = rentAllocations[index]
    row.marketing_fee = marketingAllocations[index]
    row.utilities = utilityAllocations[index]
    row.ai_token_cost = aiTokenAllocations[index]
    row.other_costs = otherAllocations[index]
    updateRowTotal(row)
  })

  quickSplitDialogVisible.value = false
  ElMessage.success('快速拆分已应用，当前页面金额已覆盖，可继续逐店修改后保存')
}

// 保存单行
const handleSaveRow = async (row) => {
  if (!row.shop_id) {
    ElMessage.warning('请选择店铺')
    return
  }

  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }
  if (!isMeaningfulExpenseRow(row)) {
    ElMessage.warning('空白费用记录无需保存，请直接保留空白行')
    return
  }

  row.saving = true
  try {
    const payload = {
      platform_code: row.platform_code,
      shop_id: row.shop_id,
      year_month: selectedMonth.value,
      rent: Number(row.rent) || 0,
      marketing_fee: Number(row.marketing_fee) || 0,
      utilities: Number(row.utilities) || 0,
      ai_token_cost: Number(row.ai_token_cost) || 0,
      other_costs: Number(row.other_costs) || 0,
      note: row.note || null
    }

    await api.post('/expenses', payload)
    await tryCompleteTaskFromExpenseRow(row, selectedMonth.value)
    ElMessage.success('保存成功')
    await loadMonthlyExpenses()
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error(error.message || '保存失败')
  } finally {
    row.saving = false
  }
}

// 删除单行
const handleDeleteRow = async (row, index) => {
  if (!row.id) {
    monthlyTableData.value.splice(index, 1)
    calculateMonthlySummary()
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除 ${selectedMonth.value} / ${row.platform_code || '-'} / ${row.shop_name || row.shop_id} 的本月费用记录吗？删除后会保留一条空白编辑行，可重新保存恢复。`,
      '确认删除本月费用',
      { type: 'warning' }
    )

    await api.delete(`/expenses/${row.id}`)
    ElMessage.success('删除成功')
    await loadMonthlyExpenses()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error(error.message || '删除失败')
    }
  }
}

// 批量保存
const handleBatchSave = async () => {
  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }

  const rowsToSave = monthlyTableData.value.filter(
    (row) =>
      row.shop_id &&
      (row.rent > 0 ||
        row.marketing_fee > 0 ||
        row.utilities > 0 ||
        row.ai_token_cost > 0 ||
        row.other_costs > 0 ||
        (row.note && String(row.note).trim().length > 0))
  )

  if (rowsToSave.length === 0) {
    ElMessage.warning('没有需要保存的数据')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要批量保存 ${rowsToSave.length} 条费用记录吗？`,
      '确认批量保存',
      { type: 'info' }
    )

    batchSaving.value = true
    let successCount = 0
    let failCount = 0

    for (const row of rowsToSave) {
      try {
        const payload = {
          platform_code: row.platform_code,
          shop_id: row.shop_id,
          year_month: selectedMonth.value,
          rent: Number(row.rent) || 0,
          marketing_fee: Number(row.marketing_fee) || 0,
          utilities: Number(row.utilities) || 0,
          ai_token_cost: Number(row.ai_token_cost) || 0,
          other_costs: Number(row.other_costs) || 0,
          note: row.note || null
        }

        await api.post('/expenses', payload)
        await tryCompleteTaskFromExpenseRow(row, selectedMonth.value)
        successCount++
      } catch (error) {
        console.error(`保存店铺 ${row.shop_name || row.shop_id} 失败:`, error)
        failCount++
      }
    }

    if (failCount === 0) {
      ElMessage.success(`成功保存 ${successCount} 条记录`)
    } else {
      ElMessage.warning(`成功保存 ${successCount} 条，失败 ${failCount} 条`)
    }

    await loadMonthlyExpenses()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量保存失败:', error)
      ElMessage.error(error.message || '批量保存失败')
    }
  } finally {
    batchSaving.value = false
  }
}

// ==================== 按店铺模式方法 ====================

// 店铺选择变化
const handleShopSelectChange = () => {
  if (selectedShopId.value) {
    loadShopExpenses()
  } else {
    shopTableData.value = []
    resetShopSummary()
  }
}

// 加载店铺费用
const loadShopExpenses = async () => {
  if (!selectedShopId.value) {
    ElMessage.warning('请先选择店铺')
    return
  }

  loading.value = true
  try {
    const params = { shop_id: selectedShopId.value }
    if (selectedYear.value) {
      params.year = selectedYear.value
    }

    const [res, deletedRes] = await Promise.all([
      api.get('/expenses/by-shop', { params }),
      api.get('/expenses/deleted', { params })
    ])

    // 处理数据
    shopTableData.value = (res.items || []).map((item) => ({
      ...normalizeExpenseRow(item),
      saving: false
    }))
    deletedShopData.value = deletedRes.items || []

    // 更新汇总
    if (res.summary) {
      shopSummary.total_amount = res.summary.total_amount || 0
      shopSummary.total_rent = res.summary.total_rent || 0
      shopSummary.total_marketing_fee = res.summary.total_marketing_fee || 0
      shopSummary.total_utilities = res.summary.total_utilities || 0
      shopSummary.total_ai_token_cost = res.summary.total_ai_token_cost || 0
      shopSummary.total_other_costs = res.summary.total_other_costs || 0
      shopSummary.month_count = res.summary.month_count || 0
    } else {
      resetShopSummary()
    }
  } catch (error) {
    console.error('加载店铺费用失败:', error)
    ElMessage.error(error.message || '加载店铺费用失败')
    deletedShopData.value = []
  } finally {
    loading.value = false
  }
}

// 重置店铺汇总
const resetShopSummary = () => {
  shopSummary.total_amount = 0
  shopSummary.total_rent = 0
  shopSummary.total_marketing_fee = 0
  shopSummary.total_utilities = 0
  shopSummary.total_ai_token_cost = 0
  shopSummary.total_other_costs = 0
  shopSummary.month_count = 0
}

const handleRestoreRow = async (row) => {
  if (!row.id) return
  try {
    await api.post(`/expenses/${row.id}/restore`)
    ElMessage.success('恢复成功')
    await loadMonthlyExpenses()
  } catch (error) {
    console.error('恢复失败:', error)
    ElMessage.error(error.message || '恢复失败')
  }
}

// 更新店铺行合计
const updateShopRowTotal = (row) => {
  row.total_cost =
    (Number(row.rent) || 0) +
    (Number(row.marketing_fee) || 0) +
    (Number(row.utilities) || 0) +
    (Number(row.ai_token_cost) || 0) +
    (Number(row.other_costs) || 0)
  row.total = row.total_cost
}

// 添加月份行
const handleAddMonthRow = () => {
  if (!selectedShopId.value) {
    ElMessage.warning('请先选择店铺')
    return
  }

  shopTableData.value.push({
    id: null,
    platform_code:
      availableShops.value.find((shop) => shop.shop_id === selectedShopId.value)?.platform_code || null,
    shop_id: selectedShopId.value,
    year_month: '',
    rent: 0,
    marketing_fee: 0,
    utilities: 0,
    ai_token_cost: 0,
    other_costs: 0,
    total_cost: 0,
    total: 0,
    note: '',
    attachments: [],
    saving: false
  })
}

// 保存店铺行
const handleSaveShopRow = async (row) => {
  if (!row.year_month) {
    ElMessage.warning('请选择月份')
    return
  }
  if (!isMeaningfulExpenseRow(row)) {
    ElMessage.warning('空白费用记录无需保存，请直接保留空白行')
    return
  }

  row.saving = true
  try {
    const payload = {
      platform_code: row.platform_code,
      shop_id: selectedShopId.value,
      year_month: row.year_month,
      rent: Number(row.rent) || 0,
      marketing_fee: Number(row.marketing_fee) || 0,
      utilities: Number(row.utilities) || 0,
      ai_token_cost: Number(row.ai_token_cost) || 0,
      other_costs: Number(row.other_costs) || 0,
      note: row.note || null
    }

    await api.post('/expenses', payload)
    await tryCompleteTaskFromExpenseRow(row, row.year_month)
    ElMessage.success('保存成功')
    await loadShopExpenses()
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error(error.message || '保存失败')
  } finally {
    row.saving = false
  }
}

// 删除店铺行
const handleDeleteShopRow = async (row, index) => {
  if (!row.id) {
    shopTableData.value.splice(index, 1)
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除 ${row.year_month} / ${row.platform_code || '-'} / ${selectedShopId.value} 的费用记录吗？删除后可重新新增同月记录恢复。`,
      '确认删除费用记录',
      { type: 'warning' }
    )

    await api.delete(`/expenses/${row.id}`)
    ElMessage.success('删除成功')
    await loadShopExpenses()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error(error.message || '删除失败')
    }
  }
}

const handleRestoreShopRow = async (row) => {
  if (!row.id) return
  try {
    await api.post(`/expenses/${row.id}/restore`)
    ElMessage.success('恢复成功')
    await loadShopExpenses()
  } catch (error) {
    console.error('恢复失败:', error)
    ElMessage.error(error.message || '恢复失败')
  }
}

// ==================== 生命周期 ====================
onMounted(() => {
  initTaskContext()
  loadShops()
  // 默认选择当前月份和年份
  const now = new Date()
  if (!selectedMonth.value) {
    selectedMonth.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  }
  selectedYear.value = `${now.getFullYear()}`
  loadMonthlyExpenses()
})
</script>

<style scoped>
.expense-management {
  min-height: calc(100vh - var(--header-height));
}

.action-bar {
  display: flex;
  align-items: center;
}

.stat-item {
  text-align: center;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 22px;
  font-weight: bold;
  color: #303133;
}

.stat-value.primary {
  color: #409eff;
}

.stat-value.warning {
  color: #e6a23c;
}

.stat-card.monthly {
  border-left: 4px solid #409eff;
}

.stat-card.yearly {
  border-left: 4px solid #e6a23c;
}

:deep(.el-input-number) {
  width: 100%;
}

:deep(.el-input-number__input) {
  text-align: right;
}

:deep(.el-tabs__item) {
  font-size: 15px;
}

:deep(.el-tabs__item .el-icon) {
  margin-right: 5px;
}

/* 错误状态样式 */
.error-state {
  padding: 40px 20px;
  text-align: center;
}

.error-state :deep(.el-result__title) {
  font-size: 16px;
  color: #303133;
}

.error-state :deep(.el-result__subtitle) {
  font-size: 14px;
  color: #909399;
}

.quick-split-tip {
  margin-bottom: 12px;
  color: #606266;
  line-height: 1.6;
}

.quick-split-meta {
  margin-bottom: 8px;
  color: #909399;
  font-size: 13px;
}

.quick-split-form {
  margin-top: 16px;
}

.shop-option-secondary {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}
</style>
