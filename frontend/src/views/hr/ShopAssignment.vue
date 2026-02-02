<template>
  <div class="shop-assignment-page erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">人员店铺归属和提成比</h1>
    <p style="color: #909399; margin-bottom: 20px;">配置员工负责的店铺及提成比例，用于后续提成计算。本模块仅管理员可见。店铺与平台已在账号管理配置，此处仅需配置可分配利润率及主管/操作员。配置保存至数据库表 <code>a_class.employee_shop_assignments</code>。</p>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" style="margin-bottom: 20px;">
      <el-tab-pane label="人员店铺归属和提成比配置" name="config">
        <template #label>
          <span><el-icon><Setting /></el-icon> 配置</span>
        </template>
      </el-tab-pane>
      <el-tab-pane label="店铺利润和人员利润统计" name="stats">
        <template #label>
          <span><el-icon><DataAnalysis /></el-icon> 统计</span>
        </template>
      </el-tab-pane>
      <el-tab-pane label="年度统计" name="annual">
        <template #label>
          <span><el-icon><Calendar /></el-icon> 年度统计</span>
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- 配置子页：以店铺为行，直接显示可用店铺，行内编辑 -->
    <div v-if="activeTab === 'config'">
      <div class="action-bar" style="margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
        <el-date-picker
          v-model="configMonth"
          type="month"
          placeholder="选择月份"
          value-format="YYYY-MM"
          size="default"
          style="width: 180px"
          @change="handleConfigMonthChange"
        />
        <el-button type="warning" @click="handleCopyFromPrevMonth" :loading="copyLoading" :disabled="!configMonth">
          复制上月配置
        </el-button>
        <el-button type="primary" @click="handleAddAllShops" style="margin-left: 10px;">
          为所有店铺添加
        </el-button>
        <el-button type="success" @click="handleBatchSave" :loading="batchSaving" style="margin-left: 10px;">
          批量保存
        </el-button>
        <el-button @click="loadConfigData" style="margin-left: 10px;">
          刷新
        </el-button>
      </div>
      <el-card>
        <el-table
          :data="configTableRows"
          stripe
          v-loading="configLoading"
          class="erp-table"
          border
          :span-method="configSpanMethod"
        >
          <el-table-column label="平台" width="100" fixed="left" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row._isFirst">{{ row.platform_code }}</span>
            </template>
          </el-table-column>
          <el-table-column label="店铺" width="180" fixed="left" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row._isFirst">{{ row.shop_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="当月销售额" width="120" align="right">
            <template #default="{ row }">
              <span v-if="row._isFirst">¥{{ formatNumber(row.monthly_sales) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="当月利润" width="120" align="right">
            <template #default="{ row }">
              <span v-if="row._isFirst">¥{{ formatNumber(row.monthly_profit) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="当月目标达成率" width="130" align="right">
            <template #default="{ row }">
              <span v-if="row._isFirst">{{ row.achievement_rate != null ? Number(row.achievement_rate).toFixed(1) + '%' : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="可分配利润率" width="140" align="right">
            <template #default="{ row }">
              <span v-if="row._isFirst" class="allocatable-rate-wrap">
                <el-input-number
                  :model-value="(row.allocatable_profit_rate ?? 0) * 100"
                  @update:model-value="(v) => { row.allocatable_profit_rate = v != null ? Number(v) / 100 : 0 }"
                  :min="0"
                  :max="100"
                  :step="0.01"
                  :precision="2"
                  :controls="false"
                  placeholder="0-100%"
                  size="small"
                  class="allocatable-rate-input"
                />
                <span class="allocatable-rate-suffix">%</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="人员" width="180" min-width="160">
            <template #default="{ row }">
              <template v-if="row._isAddRow">
                <el-button size="small" link type="primary" @click="openAddForShop(row._shop)">+ 添加</el-button>
              </template>
              <template v-else>
                <span class="person-cell">
                  {{ (row._person && (row._person.employee_name || row._person.employee_code)) || '' }}
                  <el-tag v-if="row._person" size="small" type="info" style="margin-left: 4px;">
                    {{ row._person.role === 'supervisor' ? '主管' : '操作员' }}
                  </el-tag>
                  <el-button v-if="row._person" size="small" link type="danger" @click="removePersonLocal(row._shop, row._person)">×</el-button>
                </span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="提成比例" width="120" align="right">
            <template #default="{ row }">
              <span v-if="row._person" class="allocatable-rate-wrap">
                <el-input-number
                  :model-value="((row._person && row._person.commission_ratio) ?? 0) * 100"
                  @update:model-value="(v) => { if (row._person) row._person.commission_ratio = v != null ? Number(v) / 100 : 0 }"
                  :min="0"
                  :max="100"
                  :step="0.01"
                  :precision="2"
                  :controls="false"
                  placeholder="0-100%"
                  size="small"
                  class="allocatable-rate-input"
                />
                <span class="allocatable-rate-suffix">%</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row._isFirst && hasConfig(row)" type="success" size="small">已配置</el-tag>
              <el-tag v-else-if="row._isFirst" type="info" size="small">未配置</el-tag>
              <span v-else></span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <template v-if="row._isFirst">
                <el-button size="small" type="primary" @click="handleSaveRow(row)" :loading="row.saving">
                  保存
                </el-button>
                <el-button size="small" type="danger" @click="handleDeleteRow(row)" :disabled="!hasConfig(row)">
                  删除
                </el-button>
              </template>
              <span v-else></span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 统计子页：按月份展示 -->
    <div v-if="activeTab === 'stats'">
      <div class="action-bar" style="margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
        <el-date-picker
          v-model="statsMonth"
          type="month"
          placeholder="选择月份"
          value-format="YYYY-MM"
          size="default"
          style="width: 180px"
          @change="loadStatsData"
        />
        <el-button size="small" @click="loadStatsData">刷新</el-button>
      </div>
      <el-card>
        <el-table :data="statsRows" stripe v-loading="statsLoading" class="erp-table" border>
          <el-table-column prop="platform_code" label="平台" width="100" fixed="left" />
          <el-table-column prop="shop_name" label="店铺" width="180" fixed="left" show-overflow-tooltip />
          <el-table-column prop="monthly_sales" label="当月销售额" width="120" align="right">
            <template #default="{ row }">¥{{ formatNumber(row.monthly_sales) }}</template>
          </el-table-column>
          <el-table-column prop="monthly_profit" label="当月利润" width="120" align="right">
            <template #default="{ row }">¥{{ formatNumber(row.monthly_profit) }}</template>
          </el-table-column>
          <el-table-column prop="achievement_rate" label="当月目标达成率" width="140" align="right">
            <template #default="{ row }">{{ row.achievement_rate != null ? Number(row.achievement_rate).toFixed(1) + '%' : '—' }}</template>
          </el-table-column>
          <el-table-column prop="supervisor_profit" label="主管利润收入" width="130" align="right">
            <template #default="{ row }">¥{{ formatNumber(row.supervisor_profit) }}</template>
          </el-table-column>
          <el-table-column prop="operator_profit" label="操作员利润收入" width="140" align="right">
            <template #default="{ row }">¥{{ formatNumber(row.operator_profit) }}</template>
          </el-table-column>
        </el-table>
        <div v-if="statsRows.length === 0 && !statsLoading" style="padding: 40px; text-align: center; color: #909399;">
          暂无统计数据，请先配置店铺归属并确保有订单数据
        </div>
      </el-card>
    </div>

    <!-- 年度统计子页：按人员 / 按店铺 -->
    <div v-if="activeTab === 'annual'">
      <div class="action-bar" style="margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
        <el-date-picker
          v-model="annualYear"
          type="year"
          placeholder="选择年份"
          value-format="YYYY"
          size="default"
          style="width: 140px"
          @change="loadAnnualData"
        />
        <el-radio-group v-model="annualGroupBy" size="default">
          <el-radio-button value="employee">按人员</el-radio-button>
          <el-radio-button value="shop">按店铺</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="loadAnnualData">刷新</el-button>
      </div>
      <el-card>
        <!-- 按人员：员工 x 1月..12月 x 年度合计 -->
        <el-table
          v-if="annualGroupBy === 'employee'"
          :data="annualByEmployee"
          stripe
          v-loading="annualLoading"
          class="erp-table"
          border
        >
          <el-table-column prop="employee_code" label="员工工号" width="120" fixed="left" />
          <el-table-column prop="employee_name" label="姓名" width="100" fixed="left" />
          <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="100" align="right">
            <template #default="{ row }">
              ¥{{ formatNumber(row.months && row.months[String(m).padStart(2, '0')]) }}
            </template>
          </el-table-column>
          <el-table-column label="年度合计" width="120" align="right" fixed="right">
            <template #default="{ row }">¥{{ formatNumber(row.year_total_profit) }}</template>
          </el-table-column>
        </el-table>
        <!-- 按店铺：店铺 x 1月..12月(当月利润) x 年度合计 -->
        <el-table
          v-else
          :data="annualByShop"
          stripe
          v-loading="annualLoading"
          class="erp-table"
          border
        >
          <el-table-column prop="platform_code" label="平台" width="100" fixed="left" />
          <el-table-column prop="shop_name" label="店铺" width="180" fixed="left" show-overflow-tooltip />
          <el-table-column v-for="m in 12" :key="m" :label="`${m}月利润`" width="110" align="right">
            <template #default="{ row }">
              ¥{{ formatNumber(row.months && row.months[String(m).padStart(2, '0')] && row.months[String(m).padStart(2, '0')].monthly_profit) }}
            </template>
          </el-table-column>
          <el-table-column label="年度销售额" width="120" align="right">
            <template #default="{ row }">¥{{ formatNumber(row.year_total_sales) }}</template>
          </el-table-column>
          <el-table-column label="年度利润" width="120" align="right" fixed="right">
            <template #default="{ row }">¥{{ formatNumber(row.year_total_profit) }}</template>
          </el-table-column>
        </el-table>
        <div v-if="(annualGroupBy === 'employee' ? annualByEmployee.length : annualByShop.length) === 0 && !annualLoading" style="padding: 40px; text-align: center; color: #909399;">
          暂无年度数据，请选择年份并确保该年有归属配置与订单数据
        </div>
      </el-card>
    </div>

    <!-- 新增/编辑归属弹窗 -->
    <el-dialog v-model="dialogVisible" :title="addForShopRow ? '添加主管/操作员' : '新增归属'" width="500px" @close="resetForm">
      <el-form :model="form" label-width="100px">
        <el-form-item v-if="addForShopRow" label="店铺">
          <el-input :value="addForShopRow.shop_name || addForShopRow.shop_id" disabled />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="form.role" placeholder="选择角色" style="width: 100%;" :disabled="!!addForShopRow">
            <el-option label="主管" value="supervisor" />
            <el-option label="操作员" value="operator" />
          </el-select>
        </el-form-item>
        <el-form-item label="员工" required>
          <el-select v-model="form.employee_code" placeholder="选择员工" filterable style="width: 100%;">
            <el-option v-for="e in employeesActive" :key="e.employee_code" :label="`${e.name} (${e.employee_code})`" :value="e.employee_code" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!addForShopRow" label="平台" required>
          <el-select v-model="form.platform_code" placeholder="选择平台" style="width: 100%;" @change="onPlatformChange">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="妙手" value="miaoshou" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!addForShopRow" label="店铺" required>
          <el-select v-model="form.shop_id" placeholder="选择店铺" filterable style="width: 100%;">
            <el-option v-for="s in shopsFiltered" :key="`${s.platform_code}-${s.shop_id}`" :label="s.shop_name || s.shop_id" :value="s.shop_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="提成比例" required>
          <span class="allocatable-rate-wrap">
            <el-input-number
              :model-value="(form.commission_ratio ?? 0) * 100"
              @update:model-value="(v) => { form.commission_ratio = v != null ? Number(v) / 100 : 0 }"
              :min="0"
              :max="100"
              :step="0.01"
              :precision="2"
              placeholder="0-100%"
              style="width: 100%;"
            />
            <span class="allocatable-rate-suffix">%</span>
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitForm">{{ addForShopRow ? '添加' : '新增' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Setting, DataAnalysis, Calendar } from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const activeTab = ref('config')
const configMonth = ref(new Date().toISOString().slice(0, 7))  // YYYY-MM
const statsMonth = ref(new Date().toISOString().slice(0, 7))
const copyLoading = ref(false)
const batchSaving = ref(false)

const shopRows = ref([])
const configLoading = ref(false)
const statsRows = ref([])
const statsLoading = ref(false)

const annualYear = ref(new Date().getFullYear().toString())
const annualGroupBy = ref('employee')
const annualLoading = ref(false)
const annualData = ref({ year: null, by_employee: [], by_shop: [] })

const annualByEmployee = computed(() => annualData.value.by_employee || [])
const annualByShop = computed(() => annualData.value.by_shop || [])

const employees = ref([])
const employeesActive = computed(() => employees.value.filter((e) => e.status === 'active'))
const shops = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const addForShopRow = ref(null)
const submitLoading = ref(false)
const form = ref({
  employee_code: '',
  platform_code: '',
  shop_id: '',
  commission_ratio: 0.05,
  role: 'supervisor',
})

const shopsFiltered = computed(() => {
  const pc = form.value.platform_code
  if (!pc) return shops.value
  return shops.value.filter((s) => (s.platform_code || '').toLowerCase() === (pc || '').toLowerCase())
})

// 配置表 flattened 行：一店多人，每行一个人员或“添加”占位
const configTableRows = computed(() => {
  const rows = []
  for (const shop of shopRows.value) {
    const assignments = shop.assignments || []
    const shopKey = `${shop.platform_code}|${shop.shop_id}`
    let isFirst = true
    for (const p of assignments) {
      rows.push({
        ...shop,
        _shop: shop,
        _person: p,
        _isAddRow: false,
        _isFirst: isFirst,
        _shopKey: shopKey,
      })
      isFirst = false
    }
    rows.push({
      ...shop,
      _shop: shop,
      _person: null,
      _isAddRow: true,
      _isFirst: isFirst,
      _shopKey: shopKey,
    })
  }
  return rows
})

// 不再使用 rowspan:0 隐藏单元格，避免固定列 + 部分隐藏导致的错位。每行各占一单元格，非首行用 v-if 显示空。
function configSpanMethod() {
  return { rowspan: 1, colspan: 1 }
}

function formatNumber(v) {
  if (v == null || v === '') return '0.00'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onPlatformChange() {
  form.value.shop_id = ''
}

function resetForm() {
  form.value = { employee_code: '', platform_code: '', shop_id: '', commission_ratio: 0.05, role: 'operator' }
  editId.value = null
  isEdit.value = false
  addForShopRow.value = null
}

function hasConfig(row) {
  const assignments = row.assignments || row._shop?.assignments
  return (assignments && assignments.length > 0) || (Number(row.allocatable_profit_rate) ?? 0) > 0
}

function handleConfigMonthChange() {
  if (configMonth.value) loadConfigData()
}

function handleAddAllShops() {
  loadConfigData()
}

async function handleCopyFromPrevMonth() {
  if (!configMonth.value) {
    ElMessage.warning('请先选择配置月份')
    return
  }
  copyLoading.value = true
  try {
    const res = await api.copyHrEmployeeShopAssignmentsFromPrevMonth({ year_month: configMonth.value })
    const data = res?.data ?? res ?? {}
    const copied = data.copied ?? 0
    ElMessage.success(`已复制上月配置到 ${configMonth.value}，新增 ${copied} 条`)
    await loadConfigData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '复制失败')
  } finally {
    copyLoading.value = false
  }
}

async function handleSaveRow(row) {
  const shop = row._shop || row
  if (!configMonth.value) {
    ElMessage.warning('请先选择配置月份')
    return
  }
  shop.saving = true
  try {
    const targetAssignments = (shop.assignments || []).map((p) => ({
      id: p.id,
      employee_code: p.employee_code,
      role: p.role === 'supervisor' ? 'supervisor' : 'operator',
      commission_ratio: p.commission_ratio ?? 0,
    }))
    const assRes = await api.getHrEmployeeShopAssignments({ year_month: configMonth.value, platform_code: shop.platform_code, shop_id: shop.shop_id, page: 1, page_size: 100 })
    const assData = assRes?.data ?? assRes ?? {}
    const items = (assData?.items ?? (Array.isArray(assData) ? assData : [])) || []
    for (const a of items) {
      const ar = a.role || 'operator'
      const found = targetAssignments.find((t) => t.employee_code === a.employee_code && ((t.role || 'operator') === ar))
      if (found) {
        if (Math.abs((a.commission_ratio ?? 0) - (found.commission_ratio ?? 0)) > 0.001) {
          await api.updateHrEmployeeShopAssignment(a.id, { commission_ratio: found.commission_ratio })
        }
      } else {
        await api.deleteHrEmployeeShopAssignment(a.id)
      }
    }
    for (const p of targetAssignments) {
      const pr = p.role || 'operator'
      const exists = items.find((a) => a.employee_code === p.employee_code && ((a.role || 'operator') === pr))
      if (!exists) {
        await api.createHrEmployeeShopAssignment({ year_month: configMonth.value, employee_code: p.employee_code, platform_code: shop.platform_code, shop_id: shop.shop_id, commission_ratio: p.commission_ratio, role: p.role })
      }
    }
    // 保存可分配利润率
    const rate = Number(shop.allocatable_profit_rate)
    if (!Number.isNaN(rate) && rate >= 0 && rate <= 1) {
      await api.putHrShopCommissionConfig(shop.platform_code, shop.shop_id, { allocatable_profit_rate: rate })
    }
    ElMessage.success('已保存')
    await loadConfigData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    shop.saving = false
  }
}

async function handleDeleteRow(row) {
  const shop = row._shop || row
  if (!configMonth.value) {
    ElMessage.warning('请先选择配置月份')
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除 ${shop.shop_name || shop.shop_id} 的归属配置？删除后可重新编辑。`, '确认删除', { type: 'warning' })
    const assRes = await api.getHrEmployeeShopAssignments({ year_month: configMonth.value, platform_code: shop.platform_code, shop_id: shop.shop_id, page: 1, page_size: 100 })
    const assData = assRes?.data ?? assRes ?? {}
    const items = (assData?.items ?? (Array.isArray(assData) ? assData : [])) || []
    for (const a of items) await api.deleteHrEmployeeShopAssignment(a.id)
    shop.assignments = []
    shop.allocatable_profit_rate = 0
    await api.putHrShopCommissionConfig(shop.platform_code, shop.shop_id, { allocatable_profit_rate: 0 })
    ElMessage.success('已删除，可重新编辑')
    await loadConfigData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

async function handleBatchSave() {
  if (!configMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }
  batchSaving.value = true
  try {
    const toSave = shopRows.value.filter((r) => hasConfig(r))
    for (const row of toSave) await handleSaveRow(row)
    ElMessage.success(`已批量保存 ${toSave.length} 行`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '批量保存失败')
  } finally {
    batchSaving.value = false
  }
}

function removePersonLocal(shop, p) {
  const r1 = p.role || 'operator'
  shop.assignments = (shop.assignments || []).filter((x) => !(x.employee_code === p.employee_code && ((x.role || 'operator') === r1)))
}

async function loadEmployees() {
  try {
    const res = await api.getHrEmployees({ page: 1, page_size: 500 })
    employees.value = Array.isArray(res) ? res : (res?.data ?? res ?? [])
  } catch (_) {
    employees.value = []
  }
}

async function loadShops() {
  try {
    const res = await api.getTargetShops()
    const data = res?.data ?? res
    shops.value = Array.isArray(data) ? data : (data?.data ?? data ?? [])
  } catch (_) {
    shops.value = []
  }
}

async function loadConfigData() {
  if (!configMonth.value) return
  configLoading.value = true
  try {
    const [assignmentsRes, shopsRes, statsRes, configRes] = await Promise.all([
      api.getHrEmployeeShopAssignments({ year_month: configMonth.value, page: 1, page_size: 1000 }),
      api.getTargetShops(),
      api.getHrShopProfitStatistics({ month: configMonth.value }).catch(() => ({ data: [] })),
      api.getHrShopCommissionConfig().catch(() => ({ data: [] })),
    ])
    const shopData = shopsRes?.data ?? shopsRes ?? []
    const shopList = Array.isArray(shopData) ? shopData : (shopData?.data ?? shopData ?? [])
    const assData = assignmentsRes?.data ?? assignmentsRes ?? {}
    const items = (assData?.items ?? (Array.isArray(assData) ? assData : [])).filter(Boolean)
    const statsData = statsRes?.data ?? statsRes ?? []
    const statsList = Array.isArray(statsData) ? statsData : (statsData?.data ?? statsData ?? [])
    const configData = configRes?.data ?? configRes ?? []
    const configList = Array.isArray(configData) ? configData : (configData?.data ?? configData ?? [])

    const byShop = {}
    for (const s of shopList) {
      const key = `${(s.platform_code || '').toLowerCase()}|${s.shop_id}`
      byShop[key] = {
        platform_code: (s.platform_code || '').toLowerCase(),
        shop_id: s.shop_id,
        shop_name: s.shop_name || s.shop_id,
        allocatable_profit_rate: 0,
        assignments: [],
        saving: false,
        monthly_sales: 0,
        monthly_profit: 0,
        achievement_rate: null,
      }
    }
    for (const st of statsList) {
      const key = `${(st.platform_code || '').toLowerCase()}|${st.shop_id != null ? String(st.shop_id) : ''}`
      if (byShop[key]) {
        byShop[key].monthly_sales = st.monthly_sales ?? 0
        byShop[key].monthly_profit = st.monthly_profit ?? 0
        byShop[key].achievement_rate = st.achievement_rate
      }
    }
    for (const c of configList) {
      const key = `${(c.platform_code || '').toLowerCase()}|${c.shop_id}`
      if (byShop[key]) {
        byShop[key].allocatable_profit_rate = Number(c.allocatable_profit_rate) ?? 0
      }
    }
    for (const a of items) {
      const key = `${(a.platform_code || '').toLowerCase()}|${a.shop_id}`
      if (!byShop[key]) {
        byShop[key] = {
          platform_code: (a.platform_code || '').toLowerCase(),
          shop_id: a.shop_id,
          shop_name: a.shop_name || a.shop_id,
          allocatable_profit_rate: 0,
          assignments: [],
          saving: false,
          monthly_sales: 0,
          monthly_profit: 0,
          achievement_rate: null,
        }
      }
      const p = {
        id: a.id,
        employee_code: a.employee_code,
        employee_name: a.employee_name,
        role: a.role === 'supervisor' ? 'supervisor' : 'operator',
        commission_ratio: a.commission_ratio ?? 0,
      }
      byShop[key].assignments.push(p)
    }
    shopRows.value = Object.values(byShop).sort((a, b) => (a.platform_code + a.shop_id).localeCompare(b.platform_code + b.shop_id))
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
    shopRows.value = []
  } finally {
    configLoading.value = false
  }
}

async function loadStatsData() {
  if (!statsMonth.value) return
  statsLoading.value = true
  try {
    const res = await api.getHrShopProfitStatistics({ month: statsMonth.value })
    const data = res?.data ?? res ?? []
    const items = Array.isArray(data) ? data : (data?.data ?? data ?? [])
    statsRows.value = items
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
    statsRows.value = []
  } finally {
    statsLoading.value = false
  }
}

async function loadAnnualData() {
  const year = annualYear.value ? Number(annualYear.value) : new Date().getFullYear()
  if (!year) return
  annualLoading.value = true
  try {
    const res = await api.getHrAnnualProfitStatistics({ year })
    const raw = res?.data ?? res ?? {}
    const data = raw?.data ?? raw ?? {}
    annualData.value = {
      year: data.year ?? year,
      by_employee: data.by_employee ?? [],
      by_shop: data.by_shop ?? [],
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载年度统计失败')
    annualData.value = { year: null, by_employee: [], by_shop: [] }
  } finally {
    annualLoading.value = false
  }
}

function openAdd() {
  resetForm()
  isEdit.value = false
  dialogVisible.value = true
}

function openAddForShop(shop) {
  resetForm()
  isEdit.value = false
  addForShopRow.value = shop
  form.value.platform_code = shop.platform_code
  form.value.shop_id = shop.shop_id
  form.value.role = 'operator'
  form.value.commission_ratio = 0.05
  dialogVisible.value = true
}

async function submitForm() {
  if (!form.value.employee_code) {
    ElMessage.warning('请选择员工')
    return
  }
  const shop = addForShopRow.value
  if (shop) {
    const emp = employeesActive.value.find((e) => e.employee_code === form.value.employee_code)
    const p = {
      employee_code: form.value.employee_code,
      employee_name: emp?.name,
      role: form.value.role || 'operator',
      commission_ratio: form.value.commission_ratio ?? 0,
    }
    if ((shop.assignments || []).some((x) => x.employee_code === p.employee_code && x.role === p.role)) {
      ElMessage.warning('该人员已添加')
      return
    }
    shop.assignments = [...(shop.assignments || []), p]
    ElMessage.success('已添加，请点击保存提交')
    dialogVisible.value = false
  } else {
    submitLoading.value = true
    try {
      await api.createHrEmployeeShopAssignment({
        year_month: configMonth.value,
        employee_code: form.value.employee_code,
        platform_code: form.value.platform_code,
        shop_id: form.value.shop_id,
        commission_ratio: form.value.commission_ratio ?? 0,
        role: form.value.role || 'operator',
      })
      ElMessage.success('已新增')
      dialogVisible.value = false
      await loadConfigData()
      if (activeTab.value === 'stats') await loadStatsData()
    } catch (e) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '操作失败')
    } finally {
      submitLoading.value = false
    }
  }
}

watch(activeTab, (tab) => {
  if (tab === 'config') loadConfigData()
  else if (tab === 'stats') loadStatsData()
  else if (tab === 'annual') loadAnnualData()
})

onMounted(async () => {
  await Promise.all([loadEmployees(), loadShops()])
  await loadConfigData()
})
</script>

<style scoped>
.shop-assignment-page {
  padding: 20px;
}
.person-list {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
}
.allocatable-rate-wrap {
  display: inline-flex;
  align-items: center;
  width: 100%;
}
.allocatable-rate-wrap .allocatable-rate-input { flex: 1; min-width: 0; }
.allocatable-rate-wrap .allocatable-rate-suffix { margin-left: 4px; color: #909399; }
.person-cell {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
