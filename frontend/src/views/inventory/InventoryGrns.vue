<template>
  <div class="inventory-domain-page">
    <h1 class="page-title">入库单管理</h1>
    <el-card class="filters">
      <el-form :inline="true">
        <el-form-item label="平台"><el-input v-model="postContext.platform_code" clearable /></el-form-item>
        <el-form-item label="店铺"><el-input v-model="postContext.shop_id" clearable /></el-form-item>
        <el-form-item><el-button type="primary" @click="loadGrns">刷新</el-button></el-form-item>
      </el-form>
    </el-card>
    <el-card>
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="grn_id" label="GRN号" min-width="180" />
        <el-table-column prop="po_id" label="PO号" width="160" />
        <el-table-column prop="receipt_date" label="收货日期" width="120" />
        <el-table-column prop="warehouse" label="仓库" width="120" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" :disabled="row.status === 'completed'" @click="post(row)">过账</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import inventoryDomainApi from '@/api/inventoryDomain'

const loading = ref(false)
const rows = ref([])
const postContext = reactive({ platform_code: '', shop_id: '' })

const loadGrns = async () => {
  loading.value = true
  try {
    rows.value = await inventoryDomainApi.getGrns()
  } catch (error) {
    ElMessage.error('加载GRN失败')
  } finally {
    loading.value = false
  }
}

const post = async (row) => {
  try {
    await inventoryDomainApi.postGrn(row.grn_id, {
      platform_code: postContext.platform_code,
      shop_id: postContext.shop_id
    })
    ElMessage.success('GRN已过账')
    await loadGrns()
  } catch (error) {
    ElMessage.error('GRN过账失败')
  }
}

onMounted(loadGrns)
</script>

<style scoped>
.inventory-domain-page { padding: 20px; }
.page-title { margin-bottom: 20px; font-size: 24px; font-weight: 700; }
.filters { margin-bottom: 20px; }
</style>
