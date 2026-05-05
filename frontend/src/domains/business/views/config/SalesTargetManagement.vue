<template>
  <div class="sales-target-management erp-page-container erp-page--admin">
    <PageHeader
      title="销售目标配置"
      subtitle="维护店铺月度销售目标。查询条件保留在页面本地，写操作通过统一 store 提交。"
      :icon="Histogram"
      family="admin"
    >
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          新增目标
        </el-button>
        <el-button @click="loadTargets">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </template>
    </PageHeader>

    <el-card class="erp-card" shadow="never">
      <el-form :inline="true" :model="filters" class="filter-form" @submit.prevent="loadTargets">
        <el-form-item label="店铺">
          <el-select v-model="filters.shop_id" placeholder="全部店铺" clearable class="filter-field">
            <el-option
              v-for="shop in store.shops"
              :key="`${shop.platform_code || 'unknown'}-${shop.shop_id}`"
              :label="shop.shop_name || shop.shop_id"
              :value="shop.shop_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="月份">
          <el-date-picker
            v-model="filters.year_month"
            type="month"
            placeholder="选择月份"
            format="YYYY-MM"
            value-format="YYYY-MM"
            clearable
            class="filter-field"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="store.isLoading">
            查询
          </el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table
        v-loading="store.isLoading"
        :data="store.targets"
        border
        stripe
        class="erp-table"
      >
        <el-table-column prop="shop_id" label="店铺ID" min-width="140" />
        <el-table-column prop="year_month" label="目标月份" width="120" />
        <el-table-column prop="target_sales_amount" label="目标销售额" width="160" align="right">
          <template #default="{ row }">
            ¥{{ formatAmount(row.target_sales_amount) }}
          </template>
        </el-table-column>
        <el-table-column prop="target_order_count" label="目标订单数" width="120" align="right" />
        <el-table-column prop="created_at" label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建人" width="120">
          <template #default="{ row }">
            {{ row.created_by || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="confirmDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增销售目标' : '编辑销售目标'"
      width="520px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="120px">
        <el-form-item label="店铺" prop="shop_id">
          <el-select
            v-model="form.shop_id"
            placeholder="请选择店铺"
            class="dialog-field"
            :disabled="dialogMode === 'edit'"
          >
            <el-option
              v-for="shop in store.shops"
              :key="`${shop.platform_code || 'unknown'}-${shop.shop_id}`"
              :label="shop.shop_name || shop.shop_id"
              :value="shop.shop_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="目标月份" prop="year_month">
          <el-date-picker
            v-model="form.year_month"
            type="month"
            placeholder="选择月份"
            format="YYYY-MM"
            value-format="YYYY-MM"
            class="dialog-field"
            :disabled="dialogMode === 'edit'"
          />
        </el-form-item>

        <el-form-item label="目标销售额" prop="target_sales_amount">
          <el-input-number
            v-model="form.target_sales_amount"
            :min="0"
            :precision="2"
            :step="1000"
            class="dialog-field"
          />
        </el-form-item>

        <el-form-item label="目标订单数" prop="target_order_count">
          <el-input-number
            v-model="form.target_order_count"
            :min="0"
            :step="10"
            class="dialog-field"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="store.isSubmitting" @click="submitForm">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Histogram, Plus, Refresh } from '@element-plus/icons-vue'

import PageHeader from '@/components/common/PageHeader.vue'
import { useSalesTargetsStore } from '@/stores/salesTargets.js'

const store = useSalesTargetsStore()
const formRef = ref(null)
const dialogVisible = ref(false)
const dialogMode = ref('create')
const currentEditId = ref(null)

const filters = reactive({
  shop_id: '',
  year_month: ''
})

const form = reactive({
  shop_id: '',
  year_month: '',
  target_sales_amount: 0,
  target_order_count: 0
})

const formRules = {
  shop_id: [{ required: true, message: '请选择店铺', trigger: 'change' }],
  year_month: [{ required: true, message: '请选择月份', trigger: 'change' }],
  target_sales_amount: [{ required: true, message: '请输入目标销售额', trigger: 'blur' }],
  target_order_count: [{ required: true, message: '请输入目标订单数', trigger: 'blur' }]
}

function buildQueryParams() {
  return {
    ...(filters.shop_id && { shop_id: filters.shop_id }),
    ...(filters.year_month && { year_month: filters.year_month })
  }
}

async function loadTargets(showLoading = true) {
  await store.fetchTargets(buildQueryParams(), showLoading)
}

function resetFilters() {
  filters.shop_id = ''
  filters.year_month = ''
  loadTargets()
}

function resetForm() {
  currentEditId.value = null
  dialogMode.value = 'create'
  form.shop_id = ''
  form.year_month = ''
  form.target_sales_amount = 0
  form.target_order_count = 0
  formRef.value?.clearValidate()
}

function openCreateDialog() {
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(row) {
  resetForm()
  dialogMode.value = 'edit'
  currentEditId.value = row.id
  form.shop_id = row.shop_id
  form.year_month = row.year_month
  form.target_sales_amount = Number(row.target_sales_amount) || 0
  form.target_order_count = Number(row.target_order_count) || 0
  dialogVisible.value = true
}

async function submitForm() {
  await formRef.value.validate()

  if (dialogMode.value === 'create') {
    await store.createTarget(form)
  } else {
    await store.updateTarget(currentEditId.value, form)
  }

  dialogVisible.value = false
  await loadTargets(false)
}

async function confirmDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除店铺 ${row.shop_id} 在 ${row.year_month} 的销售目标吗？`,
      '确认删除',
      { type: 'warning' }
    )
    await store.deleteTarget(row.id)
    await loadTargets(false)
  } catch (error) {
    if (error !== 'cancel') {
      throw error
    }
  }
}

function formatAmount(value) {
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(Number(value) || 0)
}

function formatDateTime(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

onMounted(async () => {
  await store.fetchShops()
  await loadTargets()
})
</script>

<style scoped>
.filter-form {
  margin-bottom: var(--spacing-lg);
}

.filter-field {
  width: 180px;
}

.dialog-field {
  width: 100%;
}
</style>
