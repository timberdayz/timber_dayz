<template>
  <div class="target-person-management erp-page-container erp-page--admin">
    <PageHeader
      title="个人目标管理"
      subtitle="按月份批量维护员工规划目标，不直接写入个人绩效结果。"
      family="admin"
    />

    <section class="toolbar">
      <el-date-picker
        v-model="filters.month"
        type="month"
        value-format="YYYY-MM"
        format="YYYY-MM"
        placeholder="选择月份"
        class="month-picker"
        @change="loadPageData"
      />
      <el-input
        v-model="filters.keyword"
        clearable
        placeholder="搜索员工"
        class="keyword-input"
        @input="applyEmployeeFilter"
      />
      <el-button @click="goToPerformancePerson">人员绩效输入</el-button>
      <el-button :icon="Refresh" @click="loadPageData" :loading="loading">刷新</el-button>
      <el-button type="primary" :icon="Check" @click="saveBatchTargets" :loading="saving">
        批量保存
      </el-button>
    </section>

    <el-table
      :data="visibleRows"
      v-loading="loading"
      border
      stripe
      class="erp-table person-target-table"
    >
      <el-table-column prop="employee_code" label="员工编号" width="130" />
      <el-table-column prop="name" label="姓名" width="150" />
      <el-table-column label="销售目标" width="180" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.sales.target_value"
            :min="0"
            :precision="2"
            :step="1000"
            controls-position="right"
            class="cell-number"
          />
        </template>
      </el-table-column>
      <el-table-column label="订单目标" width="160" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.orders.target_value"
            :min="0"
            :precision="0"
            :step="10"
            controls-position="right"
            class="cell-number"
          />
        </template>
      </el-table-column>
      <el-table-column label="客户目标" width="160" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.customers.target_value"
            :min="0"
            :precision="0"
            :step="1"
            controls-position="right"
            class="cell-number"
          />
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="140">
        <template #default="{ row }">
          <el-tag size="small" :type="row.hasExistingTarget ? 'success' : 'info'">
            {{ row.hasExistingTarget ? '已配置' : '未配置' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="visibleRows.length === 0 && !loading" class="empty-state">
      当前筛选条件下暂无员工。
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import api from '@/api'

const router = useRouter()
const targetTypes = ['sales', 'orders', 'customers']

const loading = ref(false)
const saving = ref(false)
const rows = ref([])

const filters = reactive({
  month: new Date().toISOString().slice(0, 7),
  keyword: ''
})

const visibleRows = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase()
  if (!keyword) return rows.value
  return rows.value.filter((row) => {
    return [row.employee_code, row.name].some((value) =>
      String(value || '').toLowerCase().includes(keyword)
    )
  })
})

function createTargetCell(existingTarget = null) {
  return {
    id: existingTarget?.id || null,
    target_value: Number(existingTarget?.target_value || 0)
  }
}

function normalizeList(response) {
  if (Array.isArray(response)) return response
  return response?.items || response?.data?.items || response?.data || []
}

async function loadEmployees() {
  const response = await api.getHrEmployees({ page: 1, page_size: 500, status: 'active' })
  return normalizeList(response)
}

async function loadTargets() {
  const response = await api.getHrEmployeeTargets({
    year_month: filters.month,
    page: 1,
    page_size: 500
  })
  return normalizeList(response)
}

function buildRows(employees, targets) {
  const targetMap = new Map()
  targets.forEach((target) => {
    targetMap.set(`${target.employee_code}::${target.target_type}`, target)
  })

  rows.value = employees.map((employee) => {
    const row = {
      employee_code: employee.employee_code,
      name: employee.name || employee.employee_code,
      sales: createTargetCell(targetMap.get(`${employee.employee_code}::sales`)),
      orders: createTargetCell(targetMap.get(`${employee.employee_code}::orders`)),
      customers: createTargetCell(targetMap.get(`${employee.employee_code}::customers`))
    }
    row.hasExistingTarget = targetTypes.some((type) => row[type].id)
    return row
  })
}

async function loadPageData() {
  loading.value = true
  try {
    const [employees, targets] = await Promise.all([loadEmployees(), loadTargets()])
    buildRows(Array.isArray(employees) ? employees : [], Array.isArray(targets) ? targets : [])
  } catch (error) {
    rows.value = []
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载个人目标失败')
  } finally {
    loading.value = false
  }
}

function applyEmployeeFilter() {
  // computed visibleRows handles filtering; this function keeps the input event explicit.
}

async function saveTargetCell(row, targetType) {
  const cell = row[targetType]
  const payload = {
    employee_code: row.employee_code,
    year_month: filters.month,
    target_type: targetType,
    target_value: Number(cell.target_value || 0)
  }
  if (cell.id) {
    await api.updateHrEmployeeTarget(cell.id, { target_value: payload.target_value })
    return
  }
  if (payload.target_value > 0) {
    await api.createHrEmployeeTarget(payload)
  }
}

async function saveBatchTargets() {
  saving.value = true
  try {
    for (const row of rows.value) {
      for (const targetType of targetTypes) {
        await saveTargetCell(row, targetType)
      }
    }
    ElMessage.success('个人目标已保存')
    await loadPageData()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '保存个人目标失败')
  } finally {
    saving.value = false
  }
}

function goToPerformancePerson() {
  router.push('/hr-performance-management/person')
}

onMounted(loadPageData)
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}

.month-picker {
  width: 160px;
}

.keyword-input {
  width: 220px;
}

.person-target-table {
  width: 100%;
}

.cell-number {
  width: 100%;
}

.empty-state {
  padding: 28px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
