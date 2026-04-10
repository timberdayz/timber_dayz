<template>
  <div class="inventory-age-page">
    <h1 class="page-title">库存库龄</h1>

    <el-card class="filters-card">
      <el-form :inline="true">
        <el-form-item label="平台">
          <el-input
            v-model="filters.platform"
            clearable
            placeholder="如 miaoshou"
          />
        </el-form-item>
        <el-form-item label="SKU">
          <el-input
            v-model="filters.platform_sku"
            clearable
            placeholder="输入 SKU 或 SKU Key"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="reload">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="20" class="summary-row">
      <el-col :span="8">
        <el-card>
          <el-statistic title="有库存 SKU 数" :value="summary.total_sku_count" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <el-statistic title="总库存数量" :value="summary.total_quantity" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <el-statistic
            title="总库存金额"
            :value="summary.total_value"
            prefix="¥"
            :precision="2"
          />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="7">
        <el-card>
          <template #header>库龄分布</template>
          <el-table :data="summary.buckets" size="small" stripe>
            <el-table-column prop="bucket" label="区间" width="100" />
            <el-table-column prop="sku_count" label="SKU 数" width="90" />
            <el-table-column prop="quantity" label="数量" width="90" />
            <el-table-column prop="inventory_value" label="金额" min-width="120">
              <template #default="{ row }">
                ¥{{ Number(row.inventory_value || 0).toFixed(2) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="17">
        <el-card>
          <template #header>SKU 连续库龄明细</template>
          <el-table :data="rows" v-loading="loading" stripe>
            <el-table-column prop="platform_code" label="平台" width="110" />
            <el-table-column label="SKU" min-width="190">
              <template #default="{ row }">
                <div class="sku-cell">
                  <div class="sku-primary">{{ row.platform_sku || row.sku_key }}</div>
                  <div v-if="row.product_sku && row.product_sku !== row.platform_sku" class="sku-secondary">
                    {{ row.product_sku }}
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="product_name" label="商品名称" min-width="240" show-overflow-tooltip />
            <el-table-column prop="current_qty" label="当前库存" width="100" />
            <el-table-column prop="age_days" label="库龄天数" width="100" />
            <el-table-column label="起算日期" width="120">
              <template #default="{ row }">
                {{ formatDate(row.age_anchor_date) }}
              </template>
            </el-table-column>
            <el-table-column label="重置原因" width="140">
              <template #default="{ row }">
                <el-tag size="small" :type="tagType(row.reset_reason)">
                  {{ resetReasonLabel(row.reset_reason) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="bucket" label="区间" width="90" />
            <el-table-column label="快照日期" width="120">
              <template #default="{ row }">
                {{ formatDate(row.snapshot_date) }}
              </template>
            </el-table-column>
            <el-table-column prop="inventory_value" label="库存金额" min-width="120">
              <template #default="{ row }">
                ¥{{ Number(row.inventory_value || 0).toFixed(2) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import inventoryDomainApi from '@/api/inventoryDomain'

const loading = ref(false)
const rows = ref([])
const summary = reactive({
  rows: [],
  buckets: [],
  total_sku_count: 0,
  total_quantity: 0,
  total_value: 0
})
const filters = reactive({
  platform: '',
  platform_sku: ''
})

const resetReasonLabel = (reason) => {
  switch (reason) {
    case 'first_positive':
      return '首次有库存'
    case 'reappeared_after_zero':
      return '归零后恢复'
    case 'stock_increase':
      return '库存增加重置'
    case 'continued':
      return '延续上次库龄'
    default:
      return reason || '未知'
  }
}

const tagType = (reason) => {
  switch (reason) {
    case 'stock_increase':
    case 'first_positive':
    case 'reappeared_after_zero':
      return 'success'
    case 'continued':
      return 'warning'
    default:
      return 'info'
  }
}

const formatDate = (value) => {
  if (!value) return '-'
  return String(value).slice(0, 10)
}

const reload = async () => {
  loading.value = true
  try {
    const params = {
      platform: filters.platform || undefined,
      platform_sku: filters.platform_sku || undefined
    }
    rows.value = await inventoryDomainApi.getAging(params)
    const response = await inventoryDomainApi.getAgingBuckets(params)
    Object.assign(summary, response)
  } catch (error) {
    ElMessage.error('加载库存库龄失败')
  } finally {
    loading.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.inventory-age-page {
  padding: 20px;
}

.page-title {
  margin-bottom: 20px;
  font-size: 24px;
  font-weight: 700;
}

.filters-card,
.summary-row {
  margin-bottom: 20px;
}

.sku-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sku-primary {
  font-weight: 600;
  color: #1f2937;
}

.sku-secondary {
  color: #6b7280;
  font-size: 12px;
}
</style>
