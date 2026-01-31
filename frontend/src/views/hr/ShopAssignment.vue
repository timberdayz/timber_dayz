<template>
  <div class="shop-assignment-page erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">人员店铺归属和提成比</h1>
    <p style="color: #909399; margin-bottom: 20px;">配置员工负责的店铺及提成比例，用于后续提成计算。本模块仅管理员可见。</p>

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
    </el-tabs>

    <!-- 配置子页：以店铺为行，表格化平铺 -->
    <div v-if="activeTab === 'config'">
      <div class="action-bar" style="margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
        <el-button type="primary" size="small" @click="openAdd">新增归属</el-button>
        <el-button size="small" @click="loadConfigData">刷新</el-button>
      </div>
      <el-card>
        <el-table :data="shopRows" stripe v-loading="configLoading" class="erp-table" border>
          <el-table-column prop="platform_code" label="平台" width="100" fixed="left" />
          <el-table-column prop="shop_name" label="店铺" width="180" fixed="left" show-overflow-tooltip />
          <el-table-column label="可分配利润率" width="140" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.allocatable_profit_rate"
                :min="0"
                :max="1"
                :step="0.01"
                :precision="2"
                :controls="false"
                placeholder="0-1"
                size="small"
                style="width: 100%"
              />
            </template>
          </el-table-column>
          <el-table-column label="主管" min-width="200">
            <template #default="{ row }">
              <div class="person-list">
                <el-tag v-for="p in row.supervisors" :key="p.employee_code" size="small" closable @close="removePerson(row, p, 'supervisor')">
                  {{ p.employee_name || p.employee_code }} {{ ((p.commission_ratio ?? 0) * 100).toFixed(0) }}%
                </el-tag>
                <el-button size="small" link type="primary" @click="openAddForShop(row, 'supervisor')">+ 添加</el-button>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作员" min-width="200">
            <template #default="{ row }">
              <div class="person-list">
                <el-tag v-for="p in row.operators" :key="p.employee_code" size="small" closable @close="removePerson(row, p, 'operator')">
                  {{ p.employee_name || p.employee_code }} {{ ((p.commission_ratio ?? 0) * 100).toFixed(0) }}%
                </el-tag>
                <el-button size="small" link type="primary" @click="openAddForShop(row, 'operator')">+ 添加</el-button>
              </div>
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
            <template #default="{ row }">{{ row.achievement_rate != null ? (row.achievement_rate * 100).toFixed(1) + '%' : '—' }}</template>
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

    <!-- 新增/编辑归属弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑归属' : '新增归属'" width="500px" @close="resetForm">
      <el-form :model="form" label-width="100px">
        <el-form-item label="员工" required>
          <el-select v-model="form.employee_code" placeholder="选择员工" filterable style="width: 100%;" :disabled="isEdit">
            <el-option v-for="e in employeesActive" :key="e.employee_code" :label="`${e.name} (${e.employee_code})`" :value="e.employee_code" />
          </el-select>
        </el-form-item>
        <el-form-item label="平台" required>
          <el-select v-model="form.platform_code" placeholder="选择平台" style="width: 100%;" :disabled="isEdit" @change="onPlatformChange">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="妙手" value="miaoshou" />
          </el-select>
        </el-form-item>
        <el-form-item label="店铺" required>
          <el-select v-model="form.shop_id" placeholder="选择店铺" filterable style="width: 100%;" :disabled="isEdit">
            <el-option v-for="s in shopsFiltered" :key="`${s.platform_code}-${s.shop_id}`" :label="s.shop_name || s.shop_id" :value="s.shop_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="form.role" placeholder="选择角色" style="width: 100%;">
            <el-option label="主管" value="supervisor" />
            <el-option label="操作员" value="operator" />
          </el-select>
        </el-form-item>
        <el-form-item label="提成比例" required>
          <el-input-number v-model="form.commission_ratio" :min="0" :max="1" :step="0.01" :precision="2" placeholder="0-1" style="width: 100%;" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitForm">{{ isEdit ? '保存' : '新增' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Setting, DataAnalysis } from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const activeTab = ref('config')
const statsMonth = ref(new Date().toISOString().slice(0, 7))  // YYYY-MM

const shopRows = ref([])
const configLoading = ref(false)
const statsRows = ref([])
const statsLoading = ref(false)

const employees = ref([])
const employeesActive = computed(() => employees.value.filter((e) => e.status === 'active'))
const shops = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
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

function formatNumber(v) {
  if (v == null || v === '') return '0.00'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onPlatformChange() {
  form.value.shop_id = ''
}

function resetForm() {
  form.value = { employee_code: '', platform_code: '', shop_id: '', commission_ratio: 0.05, role: 'supervisor' }
  editId.value = null
  isEdit.value = false
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
  configLoading.value = true
  try {
    const [assignmentsRes, shopsRes] = await Promise.all([
      api.getHrEmployeeShopAssignments({ page: 1, page_size: 1000 }),
      api.getTargetShops(),
    ])
    const shopData = shopsRes?.data ?? shopsRes ?? []
    const shopList = Array.isArray(shopData) ? shopData : (shopData?.data ?? shopData ?? [])
    const assData = assignmentsRes?.data ?? assignmentsRes ?? {}
    const items = (assData?.items ?? (Array.isArray(assData) ? assData : [])).filter(Boolean)

    const byShop = {}
    for (const s of shopList) {
      const key = `${(s.platform_code || '').toLowerCase()}|${s.shop_id}`
      byShop[key] = {
        platform_code: (s.platform_code || '').toLowerCase(),
        shop_id: s.shop_id,
        shop_name: s.shop_name || s.shop_id,
        allocatable_profit_rate: 0,
        supervisors: [],
        operators: [],
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
          supervisors: [],
          operators: [],
        }
      }
      const p = { ...a, commission_ratio: a.commission_ratio ?? 0 }
      if (a.role === 'supervisor') byShop[key].supervisors.push(p)
      else if (a.role === 'operator') byShop[key].operators.push(p)
      else byShop[key].operators.push(p)
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
  statsLoading.value = true
  try {
    // 占位：统计 API 未实现时，用配置数据模拟店铺结构，数值为 0
    const [assignmentsRes, shopsRes] = await Promise.all([
      api.getHrEmployeeShopAssignments({ page: 1, page_size: 1000 }),
      api.getTargetShops(),
    ])
    const shopData = shopsRes?.data ?? shopsRes ?? []
    const shopList = Array.isArray(shopData) ? shopData : (shopData?.data ?? shopData ?? [])
    const assData = assignmentsRes?.data ?? assignmentsRes ?? {}
    const items = (assData?.items ?? (Array.isArray(assData) ? assData : [])).filter(Boolean)

    const byShop = {}
    for (const s of shopList) {
      const key = `${(s.platform_code || '').toLowerCase()}|${s.shop_id}`
      byShop[key] = {
        platform_code: (s.platform_code || '').toLowerCase(),
        shop_id: s.shop_id,
        shop_name: s.shop_name || s.shop_id,
        monthly_sales: 0,
        monthly_profit: 0,
        achievement_rate: null,
        supervisor_profit: 0,
        operator_profit: 0,
      }
    }
    for (const a of items) {
      const key = `${(a.platform_code || '').toLowerCase()}|${a.shop_id}`
      if (!byShop[key]) {
        byShop[key] = {
          platform_code: (a.platform_code || '').toLowerCase(),
          shop_id: a.shop_id,
          shop_name: a.shop_name || a.shop_id,
          monthly_sales: 0,
          monthly_profit: 0,
          achievement_rate: null,
          supervisor_profit: 0,
          operator_profit: 0,
        }
      }
    }
    statsRows.value = Object.values(byShop).sort((a, b) => (a.platform_code + a.shop_id).localeCompare(b.platform_code + b.shop_id))
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
    statsRows.value = []
  } finally {
    statsLoading.value = false
  }
}

function openAdd() {
  resetForm()
  isEdit.value = false
  dialogVisible.value = true
}

function openAddForShop(row, role) {
  resetForm()
  isEdit.value = false
  addForShop.value = { platform_code: row.platform_code, shop_id: row.shop_id, shop_name: row.shop_name, role }
  form.value.platform_code = row.platform_code
  form.value.shop_id = row.shop_id
  form.value.role = role
  form.value.commission_ratio = 0.05
  dialogVisible.value = true
}

async function removePerson(row, p, role) {
  try {
    await ElMessageBox.confirm(`确定移除 ${p.employee_name || p.employee_code}？`, '确认')
    await api.deleteHrEmployeeShopAssignment(p.id)
    ElMessage.success('已移除')
    await loadConfigData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.response?.data?.detail || e?.message || '移除失败')
  }
}

async function submitForm() {
  if (!form.value.employee_code || !form.value.platform_code || !form.value.shop_id) {
    ElMessage.warning('请选择员工、平台和店铺')
    return
  }
  submitLoading.value = true
  try {
    await api.createHrEmployeeShopAssignment({
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

watch(activeTab, (tab) => {
  if (tab === 'config') loadConfigData()
  else if (tab === 'stats') loadStatsData()
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
</style>
