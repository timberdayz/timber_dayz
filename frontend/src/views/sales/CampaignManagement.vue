<template>
  <div class="campaign-management erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">销售战役管理</h1>
    
    <!-- 操作栏 -->
    <div class="action-bar" style="margin-bottom: 20px;">
      <el-button type="primary" :icon="Plus" @click="handleCreate" v-if="hasPermission('campaign:create')">
        创建战役
      </el-button>
      <el-button :icon="Refresh" @click="loadCampaigns">刷新</el-button>
      <div style="flex: 1;"></div>
      <el-select v-model="filters.status" placeholder="战役状态" clearable size="small" style="width: 150px;" @change="loadCampaigns">
        <el-option label="全部状态" value="" />
        <el-option label="进行中" value="active" />
        <el-option label="已结束" value="completed" />
        <el-option label="待开始" value="pending" />
      </el-select>
      <el-select v-model="filters.campaignType" placeholder="战役类型" clearable size="small" style="width: 150px; margin-left: 10px;" @change="loadCampaigns">
        <el-option label="全部类型" value="" />
        <el-option label="节假日" value="holiday" />
        <el-option label="新品上市" value="new_product" />
        <el-option label="特殊促销" value="special_event" />
      </el-select>
    </div>
    
    <!-- 战役列表 -->
    <el-card>
      <el-table :data="campaigns.data" stripe v-loading="campaigns.loading" class="erp-table">
        <el-table-column prop="campaign_name" label="战役名称" width="200" fixed="left" show-overflow-tooltip />
        <el-table-column prop="campaign_type" label="战役类型" width="120">
          <template #default="{ row }">
            <el-tag :type="getCampaignTypeTagType(row.campaign_type)" size="small">
              {{ getCampaignTypeLabel(row.campaign_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="start_date" label="开始时间" width="120" />
        <el-table-column prop="end_date" label="结束时间" width="120" />
        <el-table-column prop="target_amount" label="目标销售额" width="150" align="right" sortable>
          <template #default="{ row }">
            ¥{{ row.target_amount.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="actual_amount" label="实际销售额" width="150" align="right" sortable>
          <template #default="{ row }">
            ¥{{ row.actual_amount.toFixed(2) }}
          </template>
        </el-table-column>
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
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handleView(row)">查看</el-button>
            <el-button size="small" type="primary" @click="handleEdit(row)" v-if="hasPermission('campaign:update')">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)" v-if="hasPermission('campaign:delete')">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <el-pagination
        v-model:current-page="campaigns.page"
        v-model:page-size="campaigns.pageSize"
        :total="campaigns.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px; justify-content: flex-end;"
        @size-change="loadCampaigns"
        @current-change="loadCampaigns"
      />
    </el-card>
    
    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="800px"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="战役名称" prop="campaign_name">
          <el-input v-model="form.campaign_name" placeholder="请输入战役名称" />
        </el-form-item>
        <el-form-item label="战役类型" prop="campaign_type">
          <el-select v-model="form.campaign_type" placeholder="请选择战役类型" style="width: 100%;">
            <el-option label="节假日" value="holiday" />
            <el-option label="新品上市" value="new_product" />
            <el-option label="特殊促销" value="special_event" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围" prop="dateRange">
          <el-date-picker
            v-model="form.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 100%;"
          />
        </el-form-item>
        <el-form-item label="目标销售额" prop="target_amount">
          <el-input-number v-model="form.target_amount" :min="0.01" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="参与店铺" prop="participating_shops">
          <el-select
            v-model="form.participating_shops"
            multiple
            placeholder="请选择参与店铺"
            style="width: 100%;"
          >
            <el-option
              v-for="shop in availableShops"
              :key="shop.id"
              :label="shop.name"
              :value="shop.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
    
    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      title="战役详情"
      width="1000px"
    >
      <div v-if="campaignDetail.data" v-loading="campaignDetail.loading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="战役名称">{{ campaignDetail.data.campaign_name }}</el-descriptions-item>
          <el-descriptions-item label="战役类型">
            <el-tag :type="getCampaignTypeTagType(campaignDetail.data.campaign_type)" size="small">
              {{ getCampaignTypeLabel(campaignDetail.data.campaign_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ campaignDetail.data.start_date }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ campaignDetail.data.end_date }}</el-descriptions-item>
          <el-descriptions-item label="目标销售额">¥{{ campaignDetail.data.target_amount.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="实际销售额">¥{{ campaignDetail.data.actual_amount.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="达成率">
            <el-tag :type="campaignDetail.data.achievement_rate >= 90 ? 'success' : campaignDetail.data.achievement_rate >= 80 ? 'warning' : 'danger'" size="small">
              {{ campaignDetail.data.achievement_rate.toFixed(1) }}%
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusTagType(campaignDetail.data.status)" size="small">
              {{ getStatusLabel(campaignDetail.data.status) }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
        
        <!-- 店铺排名 -->
        <el-card style="margin-top: 20px;">
          <template #header>
            <span>店铺排名</span>
          </template>
          <el-table :data="campaignDetail.data.shop_ranking" stripe>
            <el-table-column prop="rank" label="排名" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.rank === 1 ? 'success' : row.rank === 2 ? 'warning' : row.rank === 3 ? 'info' : ''" size="small">
                  {{ row.rank }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="shop_name" label="店铺名称" />
            <el-table-column prop="sales_amount" label="销售额" width="150" align="right">
              <template #default="{ row }">
                ¥{{ row.sales_amount.toFixed(2) }}
              </template>
            </el-table-column>
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
import { Plus, Refresh } from '@element-plus/icons-vue'
import { useSalesStore } from '@/stores/sales'
import { useUserStore } from '@/stores/user'

const salesStore = useSalesStore()
const userStore = useUserStore()

// 权限检查
const hasPermission = (permission) => {
  const user = userStore.userInfo
  if (!user) return false
  if (user.role === 'admin') return true
  if (user.role === 'manager') {
    return ['campaign:create', 'campaign:update', 'campaign:read'].includes(permission)
  }
  return permission === 'campaign:read'
}

// 战役列表数据
const campaigns = reactive({
  data: [],
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false
})

const filters = reactive({
  status: '',
  campaignType: ''
})

// 战役详情
const campaignDetail = reactive({
  data: null,
  loading: false
})

// 对话框状态
const dialogVisible = ref(false)
const detailVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)

// 表单数据
const form = reactive({
  id: null,
  campaign_name: '',
  campaign_type: '',
  dateRange: [],
  target_amount: 0,
  participating_shops: []
})

// Mock店铺列表
const availableShops = ref([
  { id: 'shopee_sg_001', name: 'Shopee新加坡旗舰店' },
  { id: 'lazada_sg_001', name: 'Lazada新加坡店' },
  { id: 'shopee_my_001', name: 'Shopee马来旗舰店' },
  { id: 'lazada_my_001', name: 'Lazada马来店' },
  { id: 'shopee_th_001', name: 'Shopee泰国旗舰店' }
])

// 表单验证规则
const formRules = {
  campaign_name: [
    { required: true, message: '战役名称不能为空', trigger: 'blur' },
    { min: 2, max: 100, message: '战役名称长度2-100字符', trigger: 'blur' }
  ],
  campaign_type: [
    { required: true, message: '请选择战役类型', trigger: 'change' }
  ],
  dateRange: [
    { required: true, message: '请选择时间范围', trigger: 'change' },
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
    { required: true, message: '目标销售额不能为空', trigger: 'blur' },
    { type: 'number', min: 0.01, message: '目标销售额必须大于0', trigger: 'blur' }
  ],
  participating_shops: [
    { required: true, message: '请选择参与店铺', trigger: 'change' },
    { type: 'array', min: 1, message: '至少选择一个店铺', trigger: 'change' }
  ]
}

// 计算属性
const dialogTitle = computed(() => {
  return form.id ? '编辑战役' : '创建战役'
})

// 加载战役列表
const loadCampaigns = async () => {
  campaigns.loading = true
  try {
    const response = await salesStore.getCampaigns({
      status: filters.status || undefined,
      campaignType: filters.campaignType || undefined,
      page: campaigns.page,
      pageSize: campaigns.pageSize
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      campaigns.data = response.data || response || []
      campaigns.total = response.total || 0
    } else {
      ElMessage.error(response.error || '加载战役列表失败')
    }
  } catch (error) {
    ElMessage.error('加载战役列表失败')
  } finally {
    campaigns.loading = false
  }
}

// 查看详情
const handleView = async (row) => {
  detailVisible.value = true
  campaignDetail.loading = true
  try {
    const response = await salesStore.getCampaignDetail(row.id)
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      campaignDetail.data = response
    } else {
      ElMessage.error(response.error || '加载战役详情失败')
    }
  } catch (error) {
    ElMessage.error('加载战役详情失败')
  } finally {
    campaignDetail.loading = false
  }
}

// 创建战役
const handleCreate = () => {
  form.id = null
  form.campaign_name = ''
  form.campaign_type = ''
  form.dateRange = []
  form.target_amount = 0
  form.participating_shops = []
  dialogVisible.value = true
}

// 编辑战役
const handleEdit = (row) => {
  form.id = row.id
  form.campaign_name = row.campaign_name
  form.campaign_type = row.campaign_type
  form.dateRange = [new Date(row.start_date), new Date(row.end_date)]
  form.target_amount = row.target_amount
  form.participating_shops = row.participating_shops.map(shop => shop.shop_id || shop)
  dialogVisible.value = true
}

// 删除战役
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除战役"${row.campaign_name}"吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    // Mock删除
    ElMessage.success('删除成功')
    loadCampaigns()
  } catch (error) {
    // 用户取消
  }
}

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true
      try {
        const data = {
          campaign_name: form.campaign_name,
          campaign_type: form.campaign_type,
          start_date: form.dateRange[0].toISOString().split('T')[0],
          end_date: form.dateRange[1].toISOString().split('T')[0],
          target_amount: form.target_amount,
          participating_shops: form.participating_shops
        }
        
        let response
        if (form.id) {
          response = await salesStore.updateCampaign(form.id, data)
        } else {
          response = await salesStore.createCampaign(data)
        }
        
        // 响应拦截器已提取data字段，直接使用
        if (response) {
          ElMessage.success(form.id ? '更新成功' : '创建成功')
          dialogVisible.value = false
          loadCampaigns()
        } else {
          ElMessage.error(response.error || '操作失败')
        }
      } catch (error) {
        ElMessage.error('操作失败')
      } finally {
        submitting.value = false
      }
    }
  })
}

// 关闭对话框
const handleDialogClose = () => {
  formRef.value?.resetFields()
}

// 辅助函数
const getCampaignTypeLabel = (type) => {
  const map = {
    holiday: '节假日',
    new_product: '新品上市',
    special_event: '特殊促销'
  }
  return map[type] || type
}

const getCampaignTypeTagType = (type) => {
  const map = {
    holiday: 'success',
    new_product: 'warning',
    special_event: 'info'
  }
  return map[type] || ''
}

const getStatusLabel = (status) => {
  const map = {
    active: '进行中',
    completed: '已结束',
    pending: '待开始'
  }
  return map[status] || status
}

const getStatusTagType = (status) => {
  const map = {
    active: 'success',
    completed: 'info',
    pending: 'warning'
  }
  return map[status] || ''
}

onMounted(() => {
  loadCampaigns()
})
</script>

<style scoped>
.campaign-management {
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

