<template>
  <div class="target-management erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">目标管理</h1>
    
    <!-- 操作栏 -->
    <div class="action-bar" style="margin-bottom: 20px;">
      <el-button type="primary" :icon="Plus" @click="handleCreate" v-if="hasPermission('target:create')">
        创建目标
      </el-button>
      <el-button :icon="Refresh" @click="loadTargets">刷新</el-button>
      <el-button :icon="Download" @click="handleExport" v-if="hasPermission('target:export')">导出</el-button>
      <div style="flex: 1;"></div>
      <el-select v-model="filters.targetType" placeholder="目标类型" clearable size="small" style="width: 150px;" @change="loadTargets">
        <el-option label="全部类型" value="" />
        <el-option label="店铺目标" value="shop" />
        <el-option label="产品目标" value="product" />
        <el-option label="战役目标" value="campaign" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态" clearable size="small" style="width: 120px; margin-left: 10px;" @change="loadTargets">
        <el-option label="全部状态" value="" />
        <el-option label="进行中" value="active" />
        <el-option label="已完成" value="completed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
    </div>
    
    <!-- 目标列表 -->
    <el-card>
      <el-table :data="targets.data" stripe v-loading="targets.loading" class="erp-table">
        <el-table-column prop="target_name" label="目标名称" width="250" fixed="left" show-overflow-tooltip />
        <el-table-column prop="target_type" label="目标类型" width="120">
          <template #default="{ row }">
            <el-tag :type="getTargetTypeTagType(row.target_type)" size="small">
              {{ getTargetTypeLabel(row.target_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="period_start" label="开始时间" width="120" />
        <el-table-column prop="period_end" label="结束时间" width="120" />
        <el-table-column prop="target_amount" label="目标金额" width="150" align="right" sortable>
          <template #default="{ row }">
            ¥{{ row.target_amount.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="target_quantity" label="目标数量" width="120" align="right" sortable />
        <el-table-column prop="achieved_amount" label="达成金额" width="150" align="right" sortable>
          <template #default="{ row }">
            ¥{{ row.achieved_amount.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="achieved_quantity" label="达成数量" width="120" align="right" sortable />
        <el-table-column prop="achievement_rate" label="达成率" width="120" sortable>
          <template #default="{ row }">
            <el-tag :type="row.achievement_rate >= 90 ? 'success' : row.achievement_rate >= 80 ? 'warning' : 'danger'" size="small">
              {{ row.achievement_rate.toFixed(1) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handleView(row)">查看</el-button>
            <el-button size="small" type="primary" @click="handleEdit(row)" v-if="hasPermission('target:update')">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)" v-if="hasPermission('target:delete')">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <el-pagination
        v-model:current-page="targets.page"
        v-model:page-size="targets.pageSize"
        :total="targets.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px; justify-content: flex-end;"
        @size-change="loadTargets"
        @current-change="loadTargets"
      />
    </el-card>
    
    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="900px"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="目标名称" prop="target_name">
          <el-input v-model="form.target_name" placeholder="请输入目标名称" />
        </el-form-item>
        <el-form-item label="目标类型" prop="target_type">
          <el-select v-model="form.target_type" placeholder="请选择目标类型" style="width: 100%;" @change="handleTargetTypeChange">
            <el-option label="店铺目标" value="shop" />
            <el-option label="产品目标" value="product" />
            <el-option label="战役目标" value="campaign" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间周期" prop="dateRange">
          <el-date-picker
            v-model="form.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 100%;"
          />
        </el-form-item>
        <el-form-item label="目标金额" prop="target_amount">
          <el-input-number v-model="form.target_amount" :min="0.01" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="目标数量" prop="target_quantity">
          <el-input-number v-model="form.target_quantity" :min="1" :precision="0" style="width: 100%;" />
        </el-form-item>
        
        <!-- 目标拆分 -->
        <el-divider>目标拆分</el-divider>
        
        <el-tabs v-model="breakdownTab" type="border-card">
          <el-tab-pane label="按店铺拆分" name="shop">
            <div style="margin-bottom: 10px;">
              <el-button size="small" type="primary" @click="handleAddShopBreakdown">添加店铺</el-button>
              <el-button size="small" @click="handleAutoCalculateShop">自动计算</el-button>
            </div>
            <el-table :data="shopBreakdown" border>
              <el-table-column prop="shop_name" label="店铺名称" width="200">
                <template #default="{ row, $index }">
                  <el-select v-model="row.shop_id" placeholder="选择店铺" style="width: 100%;" @change="handleShopChange($index)">
                    <el-option
                      v-for="shop in availableShops"
                      :key="shop.id"
                      :label="shop.name"
                      :value="shop.id"
                    />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column prop="target_amount" label="目标金额" width="150">
                <template #default="{ row }">
                  <el-input-number v-model="row.target_amount" :min="0.01" :precision="2" style="width: 100%;" />
                </template>
              </el-table-column>
              <el-table-column prop="target_quantity" label="目标数量" width="150">
                <template #default="{ row }">
                  <el-input-number v-model="row.target_quantity" :min="1" :precision="0" style="width: 100%;" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100">
                <template #default="{ $index }">
                  <el-button size="small" type="danger" @click="handleRemoveShopBreakdown($index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div style="margin-top: 10px; color: #909399; font-size: 12px;">
              店铺拆分总和：金额 ¥{{ shopBreakdownTotalAmount.toFixed(2) }}，数量 {{ shopBreakdownTotalQuantity }}
              <el-tag :type="shopBreakdownTotalAmount === form.target_amount && shopBreakdownTotalQuantity === form.target_quantity ? 'success' : 'danger'" size="small" style="margin-left: 10px;">
                {{ shopBreakdownTotalAmount === form.target_amount && shopBreakdownTotalQuantity === form.target_quantity ? '拆分正确' : '拆分总和必须等于总目标' }}
              </el-tag>
            </div>
          </el-tab-pane>
          
          <el-tab-pane label="按时间拆分" name="time">
            <div style="margin-bottom: 10px;">
              <el-button size="small" type="primary" @click="handleAutoCalculateTime">自动计算</el-button>
            </div>
            <el-table :data="timeBreakdown" border>
              <el-table-column prop="period" label="时间周期" width="150" />
              <el-table-column prop="target_amount" label="目标金额" width="150">
                <template #default="{ row }">
                  <el-input-number v-model="row.target_amount" :min="0.01" :precision="2" style="width: 100%;" />
                </template>
              </el-table-column>
              <el-table-column prop="target_quantity" label="目标数量" width="150">
                <template #default="{ row }">
                  <el-input-number v-model="row.target_quantity" :min="1" :precision="0" style="width: 100%;" />
                </template>
              </el-table-column>
            </el-table>
            <div style="margin-top: 10px; color: #909399; font-size: 12px;">
              时间拆分总和：金额 ¥{{ timeBreakdownTotalAmount.toFixed(2) }}，数量 {{ timeBreakdownTotalQuantity }}
              <el-tag :type="timeBreakdownTotalAmount === form.target_amount && timeBreakdownTotalQuantity === form.target_quantity ? 'success' : 'danger'" size="small" style="margin-left: 10px;">
                {{ timeBreakdownTotalAmount === form.target_amount && timeBreakdownTotalQuantity === form.target_quantity ? '拆分正确' : '拆分总和必须等于总目标' }}
              </el-tag>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
    
    <!-- 目标详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      title="目标详情"
      width="1000px"
    >
      <div v-if="targetDetail.data" v-loading="targetDetail.loading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="目标名称" :span="2">{{ targetDetail.data.target_name }}</el-descriptions-item>
          <el-descriptions-item label="目标类型">
            <el-tag :type="getTargetTypeTagType(targetDetail.data.target_type)" size="small">
              {{ getTargetTypeLabel(targetDetail.data.target_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusTagType(targetDetail.data.status)" size="small">
              {{ getStatusLabel(targetDetail.data.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ targetDetail.data.period_start }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ targetDetail.data.period_end }}</el-descriptions-item>
          <el-descriptions-item label="目标金额">¥{{ targetDetail.data.target_amount.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="目标数量">{{ targetDetail.data.target_quantity }}</el-descriptions-item>
          <el-descriptions-item label="达成金额">¥{{ targetDetail.data.achieved_amount.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="达成数量">{{ targetDetail.data.achieved_quantity }}</el-descriptions-item>
          <el-descriptions-item label="达成率">
            <el-tag :type="targetDetail.data.achievement_rate >= 90 ? 'success' : targetDetail.data.achievement_rate >= 80 ? 'warning' : 'danger'" size="small">
              {{ targetDetail.data.achievement_rate.toFixed(1) }}%
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
        
        <!-- 目标分解 -->
        <el-card style="margin-top: 20px;" v-if="targetDetail.data.breakdown && targetDetail.data.breakdown.length > 0">
          <template #header>
            <span>目标分解（按店铺）</span>
          </template>
          <el-table :data="targetDetail.data.breakdown" stripe>
            <el-table-column prop="shop_name" label="店铺名称" />
            <el-table-column prop="target_amount" label="目标金额" width="150" align="right">
              <template #default="{ row }">
                ¥{{ row.target_amount.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column prop="target_quantity" label="目标数量" width="120" align="right" />
            <el-table-column prop="achieved_amount" label="达成金额" width="150" align="right">
              <template #default="{ row }">
                ¥{{ row.achieved_amount.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column prop="achieved_quantity" label="达成数量" width="120" align="right" />
            <el-table-column prop="achievement_rate" label="达成率" width="120">
              <template #default="{ row }">
                <el-tag :type="row.achievement_rate >= 90 ? 'success' : row.achievement_rate >= 80 ? 'warning' : 'danger'" size="small">
                  {{ row.achievement_rate.toFixed(1) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
        
        <!-- 时间分解 -->
        <el-card style="margin-top: 20px;" v-if="targetDetail.data.time_breakdown && targetDetail.data.time_breakdown.length > 0">
          <template #header>
            <span>目标分解（按时间）</span>
          </template>
          <el-table :data="targetDetail.data.time_breakdown" stripe>
            <el-table-column prop="week" label="周期" />
            <el-table-column prop="target_amount" label="目标金额" width="150" align="right">
              <template #default="{ row }">
                ¥{{ row.target_amount.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column prop="target_quantity" label="目标数量" width="120" align="right" />
            <el-table-column prop="achieved_amount" label="达成金额" width="150" align="right">
              <template #default="{ row }">
                ¥{{ row.achieved_amount.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column prop="achieved_quantity" label="达成数量" width="120" align="right" />
            <el-table-column prop="achievement_rate" label="达成率" width="120">
              <template #default="{ row }">
                <el-tag :type="row.achievement_rate >= 90 ? 'success' : row.achievement_rate >= 80 ? 'warning' : 'danger'" size="small">
                  {{ row.achievement_rate.toFixed(1) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Download } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import api from '@/api'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatNumber, formatPercent, formatInteger } from '@/utils/dataFormatter'

const userStore = useUserStore()

// 权限检查
const hasPermission = (permission) => {
  const user = userStore.userInfo
  if (!user) return false
  if (user.role === 'admin') return true
  if (user.role === 'manager') {
    return ['target:create', 'target:update', 'target:read', 'target:export'].includes(permission)
  }
  return permission === 'target:read'
}

// 目标列表数据
const targets = reactive({
  data: [],
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false
})

const filters = reactive({
  targetType: '',
  status: ''
})

// 目标详情
const targetDetail = reactive({
  data: null,
  loading: false
})

// 对话框状态
const dialogVisible = ref(false)
const detailVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const breakdownTab = ref('shop')

// 表单数据
const form = reactive({
  id: null,
  target_name: '',
  target_type: '',
  dateRange: [],
  target_amount: 0,
  target_quantity: 0
})

// 店铺拆分数据
const shopBreakdown = ref([])

// 时间拆分数据
const timeBreakdown = ref([])

// Mock店铺列表
const availableShops = ref([
  { id: 'shopee_sg_001', name: 'Shopee新加坡旗舰店' },
  { id: 'lazada_sg_001', name: 'Lazada新加坡店' },
  { id: 'shopee_my_001', name: 'Shopee马来旗舰店' },
  { id: 'lazada_my_001', name: 'Lazada马来店' },
  { id: 'shopee_th_001', name: 'Shopee泰国旗舰店' }
])

// 计算属性
const dialogTitle = computed(() => {
  return form.id ? '编辑目标' : '创建目标'
})

const shopBreakdownTotalAmount = computed(() => {
  return shopBreakdown.value.reduce((sum, item) => sum + (item.target_amount || 0), 0)
})

const shopBreakdownTotalQuantity = computed(() => {
  return shopBreakdown.value.reduce((sum, item) => sum + (item.target_quantity || 0), 0)
})

const timeBreakdownTotalAmount = computed(() => {
  return timeBreakdown.value.reduce((sum, item) => sum + (item.target_amount || 0), 0)
})

const timeBreakdownTotalQuantity = computed(() => {
  return timeBreakdown.value.reduce((sum, item) => sum + (item.target_quantity || 0), 0)
})

// 表单验证规则
const formRules = {
  target_name: [
    { required: true, message: '目标名称不能为空', trigger: 'blur' },
    { min: 2, max: 100, message: '目标名称长度2-100字符', trigger: 'blur' }
  ],
  target_type: [
    { required: true, message: '请选择目标类型', trigger: 'change' }
  ],
  dateRange: [
    { required: true, message: '请选择时间周期', trigger: 'change' },
    { validator: (rule, value, callback) => {
        if (!value || value.length !== 2) {
          callback(new Error('请选择开始和结束日期'))
        } else if (value[1] <= value[0]) {
          callback(new Error('结束时间必须大于开始时间'))
        } else {
          callback()
        }
      }, trigger: 'change' }
  ],
  target_amount: [
    { required: true, message: '目标金额不能为空', trigger: 'blur' },
    { type: 'number', min: 0.01, message: '目标金额必须大于0', trigger: 'blur' }
  ],
  target_quantity: [
    { required: true, message: '目标数量不能为空', trigger: 'blur' },
    { type: 'number', min: 1, message: '目标数量必须大于0', trigger: 'blur' }
  ]
}

// 加载目标列表
const loadTargets = async () => {
  targets.loading = true
  try {
    const response = await api.getTargets({
      target_type: filters.targetType || undefined,
      status: filters.status || undefined,
      page: targets.page,
      page_size: targets.pageSize
    })
    
    // 处理分页响应
    if (response && Array.isArray(response)) {
      targets.data = response
      targets.total = response.length
    } else {
      targets.data = response?.data || response || []
      targets.total = response?.total || 0
    }
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    targets.loading = false
  }
}

// 查看详情
const handleView = async (row) => {
  detailVisible.value = true
  targetDetail.loading = true
  try {
    const response = await api.getTargetDetail(row.id)
    targetDetail.data = response || {}
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    targetDetail.loading = false
  }
}

// 创建目标
const handleCreate = () => {
  form.id = null
  form.target_name = ''
  form.target_type = ''
  form.dateRange = []
  form.target_amount = 0
  form.target_quantity = 0
  shopBreakdown.value = []
  timeBreakdown.value = []
  breakdownTab.value = 'shop'
  dialogVisible.value = true
}

// 编辑目标
const handleEdit = async (row) => {
  form.id = row.id
  form.target_name = row.target_name
  form.target_type = row.target_type
  form.dateRange = [new Date(row.period_start), new Date(row.period_end)]
  form.target_amount = row.target_amount
  form.target_quantity = row.target_quantity
  
  // 加载目标详情以获取拆分数据
  const detailResponse = await api.getTargetDetail(row.id)
  shopBreakdown.value = detailResponse?.breakdown || []
  timeBreakdown.value = detailResponse?.time_breakdown || []
  
  breakdownTab.value = 'shop'
  dialogVisible.value = true
}

// 删除目标
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除目标"${row.target_name}"吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await api.deleteTarget(row.id)
    ElMessage.success('删除成功')
    loadTargets()
  } catch (error) {
    // 用户取消或删除失败
  }
}

// 目标类型变化
const handleTargetTypeChange = () => {
  shopBreakdown.value = []
  timeBreakdown.value = []
}

// 添加店铺拆分
const handleAddShopBreakdown = () => {
  shopBreakdown.value.push({
    shop_id: '',
    shop_name: '',
    target_amount: 0,
    target_quantity: 0
  })
}

// 删除店铺拆分
const handleRemoveShopBreakdown = (index) => {
  shopBreakdown.value.splice(index, 1)
}

// 店铺选择变化
const handleShopChange = (index) => {
  const shop = availableShops.value.find(s => s.id === shopBreakdown.value[index].shop_id)
  if (shop) {
    shopBreakdown.value[index].shop_name = shop.name
  }
}

// 自动计算店铺拆分
const handleAutoCalculateShop = () => {
  if (shopBreakdown.value.length === 0) {
    ElMessage.warning('请先添加店铺')
    return
  }
  
  const avgAmount = form.target_amount / shopBreakdown.value.length
  const avgQuantity = Math.floor(form.target_quantity / shopBreakdown.value.length)
  const remainderQuantity = form.target_quantity % shopBreakdown.value.length
  
  shopBreakdown.value.forEach((item, index) => {
    item.target_amount = avgAmount
    item.target_quantity = avgQuantity + (index < remainderQuantity ? 1 : 0)
  })
  
  ElMessage.success('自动计算完成')
}

// 自动计算时间拆分
const handleAutoCalculateTime = () => {
  if (!form.dateRange || form.dateRange.length !== 2) {
    ElMessage.warning('请先选择时间周期')
    return
  }
  
  const start = new Date(form.dateRange[0])
  const end = new Date(form.dateRange[1])
  const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24))
  const weeks = Math.ceil(days / 7)
  
  timeBreakdown.value = []
  let currentDate = new Date(start)
  
  for (let i = 0; i < weeks; i++) {
    const weekStart = new Date(currentDate)
    let weekEnd = new Date(currentDate)  // Fixed: changed from const to let
    weekEnd.setDate(weekEnd.getDate() + 6)
    if (weekEnd > end) weekEnd = new Date(end)
    
    const weekDays = Math.ceil((weekEnd - weekStart) / (1000 * 60 * 60 * 24)) + 1
    const weekAmount = (form.target_amount / days) * weekDays
    const weekQuantity = Math.floor((form.target_quantity / days) * weekDays)
    
    timeBreakdown.value.push({
      week: `第${i + 1}周`,
      period_start: weekStart.toISOString().split('T')[0],
      period_end: weekEnd.toISOString().split('T')[0],
      target_amount: weekAmount,
      target_quantity: weekQuantity
    })
    
    currentDate.setDate(currentDate.getDate() + 7)
  }
  
  ElMessage.success('自动计算完成')
}

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return
  
  // 验证拆分总和
  if (breakdownTab.value === 'shop') {
    if (shopBreakdownTotalAmount.value !== form.target_amount || shopBreakdownTotalQuantity.value !== form.target_quantity) {
      ElMessage.warning('店铺拆分总和必须等于总目标')
      return
    }
  } else {
    if (timeBreakdownTotalAmount.value !== form.target_amount || timeBreakdownTotalQuantity.value !== form.target_quantity) {
      ElMessage.warning('时间拆分总和必须等于总目标')
      return
    }
  }
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true
      try {
        const data = {
          target_name: form.target_name,
          target_type: form.target_type,
          period_start: form.dateRange[0].toISOString().split('T')[0],
          period_end: form.dateRange[1].toISOString().split('T')[0],
          target_amount: form.target_amount,
          target_quantity: form.target_quantity
        }
        
        let response
        if (form.id) {
          response = await api.updateTarget(form.id, data)
        } else {
          response = await api.createTarget(data)
        }
        
        // 创建目标分解
        if (breakdownTab.value === 'shop' && shopBreakdown.value.length > 0) {
          const targetId = response?.id || form.id
          if (targetId) {
            await api.createTargetBreakdown(targetId, shopBreakdown.value)
          }
        }
        
        ElMessage.success(form.id ? '更新成功' : '创建成功')
        dialogVisible.value = false
        loadTargets()
      } catch (error) {
        handleApiError(error, { showMessage: true, logError: true })
      } finally {
        submitting.value = false
      }
    }
  })
}

// 关闭对话框
const handleDialogClose = () => {
  formRef.value?.resetFields()
  shopBreakdown.value = []
  timeBreakdown.value = []
}

// 导出
const handleExport = () => {
  ElMessage.info('导出功能开发中（Mock阶段）')
  // TODO: 实现Excel导出功能
}

// 辅助函数
const getTargetTypeLabel = (type) => {
  const map = {
    shop: '店铺目标',
    product: '产品目标',
    campaign: '战役目标'
  }
  return map[type] || type
}

const getTargetTypeTagType = (type) => {
  const map = {
    shop: 'success',
    product: 'warning',
    campaign: 'info'
  }
  return map[type] || ''
}

const getStatusLabel = (status) => {
  const map = {
    active: '进行中',
    completed: '已完成',
    cancelled: '已取消'
  }
  return map[status] || status
}

const getStatusTagType = (status) => {
  const map = {
    active: 'success',
    completed: 'info',
    cancelled: 'danger'
  }
  return map[status] || ''
}

onMounted(() => {
  loadTargets()
})
</script>

<style scoped>
.target-management {
  padding: 20px;
}

.action-bar {
  display: flex;
  align-items: center;
}

/* 企业级表格样式 */
.erp-table :deep(.el-table__fixed-left) {
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table__fixed-right) {
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table .cell) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>

