<template>
  <div class="sales-target-management">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <h3>销售目标管理</h3>
          <el-button type="primary" @click="showCreateDialog">
            <el-icon><Plus /></el-icon> 新增目标
          </el-button>
        </div>
      </template>

      <!-- 筛选条件 -->
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="店铺">
          <el-select v-model="filters.shop_id" placeholder="全部店铺" clearable>
            <el-option label="全部" value="" />
            <el-option
              v-for="shop in shops"
              :key="shop.id"
              :label="shop.name"
              :value="shop.id"
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
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadTargets">
            <el-icon><Search /></el-icon> 查询
          </el-button>
          <el-button @click="resetFilters">
            <el-icon><Refresh /></el-icon> 重置
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 数据表格 -->
      <el-table
        :data="targets"
        v-loading="loading"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="shop_id" label="店铺ID" width="120" />
        <el-table-column prop="year_month" label="目标月份" width="120" />
        <el-table-column
          prop="target_sales_amount"
          label="目标销售额"
          width="150"
          align="right"
        >
          <template #default="{ row }">
            ¥{{ formatNumber(row.target_sales_amount) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="target_order_count"
          label="目标订单数"
          width="120"
          align="right"
        />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建人" width="100" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="showEditDialog(row)"
            >
              编辑
            </el-button>
            <el-button
              type="danger"
              size="small"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      :title="dialogMode === 'create' ? '新增销售目标' : '编辑销售目标'"
      v-model="dialogVisible"
      width="500px"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="店铺" prop="shop_id">
          <el-select
            v-model="formData.shop_id"
            placeholder="请选择店铺"
            :disabled="dialogMode === 'edit'"
            style="width: 100%"
          >
            <el-option
              v-for="shop in shops"
              :key="shop.id"
              :label="shop.name"
              :value="shop.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="目标月份" prop="year_month">
          <el-date-picker
            v-model="formData.year_month"
            type="month"
            placeholder="选择月份"
            format="YYYY-MM"
            value-format="YYYY-MM"
            :disabled="dialogMode === 'edit'"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="目标销售额" prop="target_sales_amount">
          <el-input-number
            v-model="formData.target_sales_amount"
            :min="0"
            :precision="2"
            :step="1000"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="目标订单数" prop="target_order_count">
          <el-input-number
            v-model="formData.target_order_count"
            :min="0"
            :step="10"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Refresh } from '@element-plus/icons-vue'
import axios from 'axios'

// 状态管理
const loading = ref(false)
const submitting = ref(false)
const targets = ref([])
const shops = ref([])
const dialogVisible = ref(false)
const dialogMode = ref('create')
const formRef = ref(null)

// 筛选条件
const filters = reactive({
  shop_id: '',
  year_month: ''
})

// 表单数据
const formData = reactive({
  shop_id: '',
  year_month: '',
  target_sales_amount: 0,
  target_order_count: 0
})

// 当前编辑的ID
const currentEditId = ref(null)

// 表单验证规则
const formRules = {
  shop_id: [{ required: true, message: '请选择店铺', trigger: 'change' }],
  year_month: [{ required: true, message: '请选择月份', trigger: 'change' }],
  target_sales_amount: [
    { required: true, message: '请输入目标销售额', trigger: 'blur' }
  ],
  target_order_count: [
    { required: true, message: '请输入目标订单数', trigger: 'blur' }
  ]
}

// 加载店铺列表
const loadShops = async () => {
  try {
    const response = await axios.get('/api/shops')
    shops.value = response.data.data || []
  } catch (error) {
    console.error('加载店铺列表失败:', error)
    // 使用模拟数据
    shops.value = [
      { id: 'shop1', name: '店铺1' },
      { id: 'shop2', name: '店铺2' }
    ]
  }
}

// 加载销售目标
const loadTargets = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.shop_id) params.shop_id = filters.shop_id
    if (filters.year_month) params.year_month = filters.year_month

    const response = await axios.get('/api/config/sales-targets', { params })
    targets.value = response.data.data || response.data || []
    
    ElMessage.success('加载成功')
  } catch (error) {
    console.error('加载销售目标失败:', error)
    ElMessage.error('加载失败：' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 重置筛选
const resetFilters = () => {
  filters.shop_id = ''
  filters.year_month = ''
  loadTargets()
}

// 显示创建对话框
const showCreateDialog = () => {
  dialogMode.value = 'create'
  resetFormData()
  dialogVisible.value = true
}

// 显示编辑对话框
const showEditDialog = (row) => {
  dialogMode.value = 'edit'
  currentEditId.value = row.id
  Object.assign(formData, {
    shop_id: row.shop_id,
    year_month: row.year_month,
    target_sales_amount: row.target_sales_amount,
    target_order_count: row.target_order_count
  })
  dialogVisible.value = true
}

// 重置表单
const resetFormData = () => {
  Object.assign(formData, {
    shop_id: '',
    year_month: '',
    target_sales_amount: 0,
    target_order_count: 0
  })
  formRef.value?.clearValidate()
}

// 提交表单
const handleSubmit = async () => {
  try {
    await formRef.value.validate()
    
    submitting.value = true
    
    if (dialogMode.value === 'create') {
      await axios.post('/api/config/sales-targets', formData)
      ElMessage.success('创建成功')
    } else {
      await axios.put(`/api/config/sales-targets/${currentEditId.value}`, {
        target_sales_amount: formData.target_sales_amount,
        target_order_count: formData.target_order_count
      })
      ElMessage.success('更新成功')
    }
    
    dialogVisible.value = false
    loadTargets()
  } catch (error) {
    if (error.response) {
      ElMessage.error('操作失败：' + (error.response.data?.detail || error.message))
    } else if (error !== undefined) {
      console.error('表单验证失败:', error)
    }
  } finally {
    submitting.value = false
  }
}

// 删除目标
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除店铺 ${row.shop_id} 在 ${row.year_month} 的销售目标吗？`,
      '确认删除',
      {
        type: 'warning'
      }
    )
    
    await axios.delete(`/api/config/sales-targets/${row.id}`)
    ElMessage.success('删除成功')
    loadTargets()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败：' + (error.response?.data?.detail || error.message))
    }
  }
}

// 格式化数字
const formatNumber = (num) => {
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(num)
}

// 格式化日期时间
const formatDateTime = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

// 生命周期
onMounted(() => {
  loadShops()
  loadTargets()
})
</script>

<style scoped>
.sales-target-management {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.filter-form {
  margin-bottom: 20px;
}
</style>

