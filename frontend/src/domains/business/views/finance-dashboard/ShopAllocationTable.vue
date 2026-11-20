<template>
  <el-card class="section-card">
    <template #header>
      <div class="card-header">
        <span>店铺分布</span>
        <el-tag type="info" effect="plain">{{ rows.length }} 家</el-tag>
      </div>
    </template>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="下列金额与占比均由后端按统一口径下发，看板只做展示。"
      class="section-alert"
    />

    <el-table v-if="rows.length" :data="rows" stripe class="shop-table">
      <el-table-column label="平台" min-width="110">
        <template #default="{ row }">{{ row.platform_label }}</template>
      </el-table-column>
      <el-table-column label="店铺" min-width="160">
        <template #default="{ row }">
          <div class="shop-display-cell">
            <span class="shop-name">{{ row.shop_display_name }}</span>
            <div v-if="row.shop_secondary_name" class="shop-display-secondary">{{ row.shop_secondary_name }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="利润基数" min-width="140" align="right">
        <template #default="{ row }">
          <span :class="valueClass(row.profit_basis_amount)">{{ formatAmount(row.profit_basis_amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="绩效工资" min-width="140" align="right">
        <template #default="{ row }">
          <span :class="valueClass(row.performance_amount)">{{ formatAmount(row.performance_amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="提成" min-width="140" align="right">
        <template #default="{ row }">
          <span :class="valueClass(row.commission_amount)">{{ formatAmount(row.commission_amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="分配额" min-width="140" align="right">
        <template #default="{ row }">
          <span :class="valueClass(row.allocation_amount)">{{ formatAmount(row.allocation_amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="分配占比" min-width="120" align="right">
        <template #default="{ row }">{{ formatRatio(row.allocation_ratio) }}</template>
      </el-table-column>
      <el-table-column label="标记" min-width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.over_allocation_flag === true" type="danger" size="small">超额分配</el-tag>
          <span v-else class="cell-placeholder">—</span>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-else description="当前月份暂无店铺分配数据" />
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { formatPlatform } from '@/utils/format'
import { resolveShopDisplay } from '@/utils/shopDisplay'
import { formatDashboardAmount, formatDashboardRatio } from '@/stores/financeDashboard'

const props = defineProps({
  breakdown: { type: Array, default: () => [] },
  shopLookup: { type: Object, default: () => new Map() }
})

const formatAmount = (value) => formatDashboardAmount(value)
const formatRatio = (value) => formatDashboardRatio(value)

/** 负数显红：绝不截断为 0、绝不显示绝对值。 */
const valueClass = (value) => (Number(value) < 0 ? 'negative' : '')

/**
 * 店铺显示名走全站统一口径（``@/utils/shopDisplay``）。
 * ⚠️ 匹配不到时回退到店铺编号，不自行编造名称。
 */
const rows = computed(() =>
  (props.breakdown || []).map((row) => {
    const display = resolveShopDisplay(
      { platform_code: row?.platform_code, shop_id: row?.shop_id },
      props.shopLookup
    )
    return {
      ...row,
      platform_label: formatPlatform(row?.platform_code) || '—',
      shop_display_name: display.display_name || row?.shop_id || '—',
      shop_secondary_name: display.secondary_name || ''
    }
  })
)
</script>

<style scoped>
.section-card { margin-bottom: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-weight: 600; }
.section-alert { margin-bottom: 16px; }
.shop-table { width: 100%; }
.shop-display-cell { line-height: 1.4; }
.shop-display-secondary { font-size: 12px; color: #909399; }
.shop-name { font-weight: 600; color: #303133; }
.negative { color: #f56c6c; }
.cell-placeholder { color: #909399; }
</style>
