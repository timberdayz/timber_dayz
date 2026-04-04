<template>
  <div class="inventory-domain-page">
    <h1 class="page-title">库存调整</h1>
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card>
          <template #header>新建调整单</template>
          <el-form label-position="top">
            <el-form-item label="调整日期"><el-date-picker v-model="form.adjustment_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
            <el-form-item label="原因"><el-input v-model="form.reason" /></el-form-item>
            <el-form-item label="平台"><el-input v-model="form.line.platform_code" /></el-form-item>
            <el-form-item label="店铺"><el-input v-model="form.line.shop_id" /></el-form-item>
            <el-form-item label="SKU"><el-input v-model="form.line.platform_sku" /></el-form-item>
            <el-form-item label="调整数量"><el-input-number v-model="form.line.qty_delta" /></el-form-item>
            <el-form-item label="单位成本"><el-input-number v-model="form.line.unit_cost" :precision="2" :step="0.1" /></el-form-item>
            <el-button type="primary" @click="submit">创建</el-button>
          </el-form>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card>
          <template #header>调整单列表</template>
          <el-table :data="rows" v-loading="loading" stripe>
            <el-table-column prop="adjustment_id" label="调整单号" min-width="180" />
            <el-table-column prop="adjustment_date" label="日期" width="120" />
            <el-table-column prop="reason" label="原因" width="120" />
            <el-table-column prop="status" label="状态" width="120" />
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button size="small" :disabled="row.status === 'posted'" @click="post(row)">过账</el-button>
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
const form = reactive({
  adjustment_date: '',
  reason: 'stock_count',
  line: {
    platform_code: '',
    shop_id: '',
    platform_sku: '',
    qty_delta: 0,
    unit_cost: 0
  }
})

const loadAdjustments = async () => {
  loading.value = true
  try {
    rows.value = await inventoryDomainApi.getAdjustments()
  } catch (error) {
    ElMessage.error('加载调整单失败')
  } finally {
    loading.value = false
  }
}

const submit = async () => {
  try {
    await inventoryDomainApi.createAdjustment({
      adjustment_date: form.adjustment_date,
      reason: form.reason,
      lines: [{ ...form.line }]
    })
    ElMessage.success('调整单已创建')
    await loadAdjustments()
  } catch (error) {
    ElMessage.error('创建调整单失败')
  }
}

const post = async (row) => {
  try {
    await inventoryDomainApi.postAdjustment(row.adjustment_id)
    ElMessage.success('调整单已过账')
    await loadAdjustments()
  } catch (error) {
    ElMessage.error('调整单过账失败')
  }
}

onMounted(loadAdjustments)
</script>

<style scoped>
.inventory-domain-page { padding: 20px; }
.page-title { margin-bottom: 20px; font-size: 24px; font-weight: 700; }
</style>
