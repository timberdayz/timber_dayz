<template>
  <div class="target-person-management erp-page-container erp-page--admin">
    <PageHeader
      title="个人目标管理"
      subtitle="按店铺销售/毛利目标与员工目标分配比例汇总，仅作目标展示，不写入绩效和工资计算。"
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
      />
      <el-button @click="goToPerformancePerson">人员绩效输入</el-button>
      <el-button :icon="Refresh" @click="loadPageData" :loading="loading">刷新</el-button>
    </section>

    <el-alert
      v-if="hasAllocationRisk"
      title="存在店铺目标分配比例合计不等于 100% 的配置风险；该提示不阻断店铺绩效计算。"
      type="warning"
      :closable="false"
      show-icon
      class="risk-alert"
    />

    <el-table
      :data="visibleRows"
      v-loading="loading"
      border
      stripe
      class="erp-table person-target-table"
    >
      <el-table-column type="expand" width="52">
        <template #default="{ row }">
          <el-table :data="row.shop_summaries" size="small" border class="shop-source-table">
            <el-table-column prop="shop_name" label="来源店铺" min-width="160" />
            <el-table-column label="分配比例" width="110" align="right">
              <template #default="{ row: shop }">{{ formatPercent(shop.target_allocation_ratio) }}</template>
            </el-table-column>
            <el-table-column label="销售目标 / 实际 / 达成" min-width="220" align="right">
              <template #default="{ row: shop }">
                {{ formatNumber(shop.sales_target) }} / {{ formatNumber(shop.sales_actual) }} / {{ formatPercent(shop.sales_achievement_rate) }}
              </template>
            </el-table-column>
            <el-table-column label="毛利目标 / 实际 / 达成" min-width="220" align="right">
              <template #default="{ row: shop }">
                {{ formatNumber(shop.gross_profit_target) }} / {{ formatNumber(shop.gross_profit_actual) }} / {{ formatPercent(shop.gross_profit_achievement_rate) }}
              </template>
            </el-table-column>
            <el-table-column label="配置" width="110" align="center">
              <template #default="{ row: shop }">
                <el-tag :type="shop.has_allocation_risk ? 'warning' : 'success'" size="small">
                  {{ shop.has_allocation_risk ? '比例风险' : '比例正常' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </el-table-column>
      <el-table-column prop="employee_code" label="员工编号" width="130" />
      <el-table-column prop="name" label="姓名" width="150" />
      <el-table-column label="销售目标" width="140" align="right">
        <template #default="{ row }">{{ formatNumber(row.sales_target) }}</template>
      </el-table-column>
      <el-table-column label="销售实际" width="140" align="right">
        <template #default="{ row }">{{ formatNumber(row.sales_actual) }}</template>
      </el-table-column>
      <el-table-column label="销售达成率" width="120" align="right">
        <template #default="{ row }">{{ formatPercent(row.sales_achievement_rate) }}</template>
      </el-table-column>
      <el-table-column label="毛利目标" width="140" align="right">
        <template #default="{ row }">{{ formatNumber(row.gross_profit_target) }}</template>
      </el-table-column>
      <el-table-column label="毛利实际" width="140" align="right">
        <template #default="{ row }">{{ formatNumber(row.gross_profit_actual) }}</template>
      </el-table-column>
      <el-table-column label="毛利达成率" width="120" align="right">
        <template #default="{ row }">{{ formatPercent(row.gross_profit_achievement_rate) }}</template>
      </el-table-column>
      <el-table-column label="配置状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="row.has_allocation_risk ? 'warning' : 'success'" size="small">
            {{ row.has_allocation_risk ? '比例风险' : '比例正常' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="visibleRows.length === 0 && !loading" class="empty-state">
      当前筛选条件下暂无已配置店铺归属的员工。
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import api from '@/api'
import { buildEmployeeTargetSummary, normalizeApiList } from './personTargetUtils'

const router = useRouter()
const loading = ref(false)
const rows = ref([])

const filters = reactive({
  month: new Date().toISOString().slice(0, 7),
  keyword: ''
})

const visibleRows = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase()
  if (!keyword) return rows.value
  return rows.value.filter((row) => [row.employee_code, row.name].some((value) =>
    String(value || '').toLowerCase().includes(keyword)
  ))
})

const hasAllocationRisk = computed(() => rows.value.some((row) => row.has_allocation_risk))

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`
}

async function loadPageData() {
  loading.value = true
  try {
    const response = await api.getHrEmployeeTargetSummary({ year_month: filters.month })
    rows.value = normalizeApiList(response).map((summary) => {
      const totals = buildEmployeeTargetSummary({
        valuesAlreadyAllocated: true,
        assignments: summary.shops || []
      })
      return {
        ...summary,
        ...totals,
        name: summary.employee_name || summary.employee_code,
        shop_summaries: summary.shops || []
      }
    })
  } catch (error) {
    rows.value = []
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载个人目标汇总失败')
  } finally {
    loading.value = false
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

.person-target-table,
.shop-source-table {
  width: 100%;
}

.risk-alert {
  margin-bottom: 14px;
}

.empty-state {
  padding: 28px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
