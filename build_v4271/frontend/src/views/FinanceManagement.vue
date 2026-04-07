<template>
  <div class="finance-management">
    <el-card class="header-card">
      <h2>财务管理中心</h2>
      <p class="subtitle">费用导入 · 成本分摊 · P&L月报</p>
    </el-card>

    <el-tabs v-model="activeTab" type="border-card">
      <!-- Tab 1: 费用导入 -->
      <el-tab-pane label="费用导入" name="expense">
        <div class="expense-upload">
          <el-card>
            <template #header>
              <div class="card-header">
                <span>月度费用上传</span>
                <el-button type="primary" size="small" @click="downloadTemplate">
                  下载模板
                </el-button>
              </div>
            </template>

            <el-form :model="expenseForm" label-width="120px">
              <el-form-item label="会计期间">
                <el-date-picker
                  v-model="expenseForm.period"
                  type="month"
                  placeholder="选择月份"
                  format="YYYY-MM"
                  value-format="YYYY-MM"
                />
              </el-form-item>

              <el-form-item label="上传文件">
                <el-upload
                  ref="uploadRef"
                  :auto-upload="false"
                  :on-change="handleFileSelect"
                  accept=".xlsx,.xls"
                  :limit="1"
                >
                  <el-button type="primary">选择文件</el-button>
                  <template #tip>
                    <div class="el-upload__tip">
                      支持.xlsx/.xls格式，请使用标准模板
                    </div>
                  </template>
                </el-upload>
              </el-form-item>

              <el-form-item>
                <el-button 
                  type="primary" 
                  @click="uploadExpenses" 
                  :loading="uploading"
                  :disabled="!selectedFile"
                >
                  上传并导入
                </el-button>
              </el-form-item>
            </el-form>

            <el-alert
              v-if="uploadResult"
              :title="uploadResult.message"
              :type="uploadResult.success ? 'success' : 'error'"
              :closable="false"
              show-icon
              style="margin-top: 20px"
            >
              <template v-if="uploadResult.success">
                <p>导入成功：{{ uploadResult.imported }} 条</p>
                <p v-if="uploadResult.quarantined > 0">
                  隔离区：{{ uploadResult.quarantined }} 条（需人工处理）
                </p>
              </template>
            </el-alert>
          </el-card>

          <!-- 费用分摊 -->
          <el-card style="margin-top: 20px">
            <template #header>
              <span>费用分摊</span>
            </template>

            <el-form :model="allocationForm" label-width="120px">
              <el-form-item label="会计期间">
                <el-date-picker
                  v-model="allocationForm.period"
                  type="month"
                  placeholder="选择月份"
                  format="YYYY-MM"
                  value-format="YYYY-MM"
                />
              </el-form-item>

              <el-form-item label="分摊方式">
                <el-select v-model="allocationForm.driver">
                  <el-option label="按收入比例" value="revenue_share" />
                  <el-option label="按订单量" value="orders_share" />
                  <el-option label="按销量" value="units_share" />
                </el-select>
              </el-form-item>

              <el-form-item>
                <el-button 
                  type="primary" 
                  @click="runAllocation" 
                  :loading="allocating"
                >
                  执行分摊
                </el-button>
              </el-form-item>
            </el-form>

            <el-alert
              v-if="allocationResult"
              :title="allocationResult.message"
              :type="allocationResult.success ? 'success' : 'error'"
              :closable="false"
              show-icon
              style="margin-top: 20px"
            >
              <template v-if="allocationResult.success">
                <p>分摊记录：{{ allocationResult.allocated_count }} 条</p>
                <p>分摊总额：¥{{ allocationResult.total_allocated_amt.toLocaleString() }}</p>
              </template>
            </el-alert>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- Tab 2: P&L月报 -->
      <el-tab-pane label="P&L月报" name="pnl">
        <div class="pnl-report">
          <el-card>
            <template #header>
              <span>店铺月度损益表</span>
            </template>

            <el-form :inline="true" :model="pnlQuery">
              <el-form-item label="平台">
                <el-select v-model="pnlQuery.platform" clearable>
                  <el-option label="全部" value="" />
                  <el-option label="Shopee" value="shopee" />
                  <el-option label="TikTok" value="tiktok" />
                </el-select>
              </el-form-item>

              <el-form-item label="店铺">
                <el-input v-model="pnlQuery.shop_id" clearable placeholder="输入店铺ID" />
              </el-form-item>

              <el-form-item label="期间">
                <el-date-picker
                  v-model="pnlQuery.period"
                  type="month"
                  placeholder="选择月份"
                  format="YYYY-MM"
                  value-format="YYYY-MM"
                />
              </el-form-item>

              <el-form-item>
                <el-button type="primary" @click="loadPnL" :loading="loadingPnL">
                  查询
                </el-button>
              </el-form-item>
            </el-form>

            <el-table :data="pnlData" border style="margin-top: 20px">
              <el-table-column prop="platform_code" label="平台" width="100" />
              <el-table-column prop="shop_id" label="店铺" width="150" />
              <el-table-column prop="period_month" label="期间" width="100" />
              <el-table-column prop="revenue" label="营业收入" width="120" align="right">
                <template #default="scope">
                  ¥{{ scope.row.revenue.toLocaleString() }}
                </template>
              </el-table-column>
              <el-table-column prop="cogs" label="销售成本" width="120" align="right">
                <template #default="scope">
                  ¥{{ scope.row.cogs.toLocaleString() }}
                </template>
              </el-table-column>
              <el-table-column prop="gross_profit" label="毛利" width="120" align="right">
                <template #default="scope">
                  <span :class="scope.row.gross_profit > 0 ? 'profit-positive' : 'profit-negative'">
                    ¥{{ scope.row.gross_profit.toLocaleString() }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="operating_expenses" label="运营费用" width="120" align="right">
                <template #default="scope">
                  ¥{{ scope.row.operating_expenses.toLocaleString() }}
                </template>
              </el-table-column>
              <el-table-column prop="contribution_profit" label="贡献利润" width="120" align="right">
                <template #default="scope">
                  <span :class="scope.row.contribution_profit > 0 ? 'profit-positive' : 'profit-negative'">
                    ¥{{ scope.row.contribution_profit.toLocaleString() }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="gross_margin_pct" label="毛利率" width="100" align="right">
                <template #default="scope">
                  {{ scope.row.gross_margin_pct.toFixed(2) }}%
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 汇率管理 -->
      <el-tab-pane label="汇率管理" name="fx">
        <div class="fx-management">
          <el-card>
            <template #header>
              <div class="card-header">
                <span>汇率维护（CNY基准）</span>
                <el-button type="primary" size="small" @click="showFxDialog = true">
                  新增汇率
                </el-button>
              </div>
            </template>

            <el-table :data="fxRates" border>
              <el-table-column prop="rate_date" label="日期" width="120" />
              <el-table-column prop="from_currency" label="源货币" width="100" />
              <el-table-column prop="to_currency" label="目标货币" width="100" />
              <el-table-column prop="rate" label="汇率" width="120" align="right">
                <template #default="scope">
                  {{ scope.row.rate.toFixed(6) }}
                </template>
              </el-table-column>
              <el-table-column prop="source" label="来源" width="100" />
              <el-table-column prop="version" label="版本" width="80" />
            </el-table>
          </el-card>

          <!-- 新增汇率对话框 -->
          <el-dialog v-model="showFxDialog" title="新增汇率" width="500px">
            <el-form :model="fxForm" label-width="100px">
              <el-form-item label="日期">
                <el-date-picker
                  v-model="fxForm.rate_date"
                  type="date"
                  placeholder="选择日期"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                />
              </el-form-item>

              <el-form-item label="源货币">
                <el-select v-model="fxForm.from_currency">
                  <el-option label="USD" value="USD" />
                  <el-option label="SGD" value="SGD" />
                  <el-option label="MYR" value="MYR" />
                  <el-option label="PHP" value="PHP" />
                  <el-option label="THB" value="THB" />
                  <el-option label="VND" value="VND" />
                  <el-option label="BRL" value="BRL" />
                </el-select>
              </el-form-item>

              <el-form-item label="汇率">
                <el-input-number v-model="fxForm.rate" :precision="6" :step="0.01" />
              </el-form-item>

              <el-form-item>
                <el-button type="primary" @click="saveFxRate">保存</el-button>
                <el-button @click="showFxDialog = false">取消</el-button>
              </el-form-item>
            </el-form>
          </el-dialog>
        </div>
      </el-tab-pane>

      <!-- Tab 4: 会计期间 -->
      <el-tab-pane label="会计期间" name="period">
        <div class="period-management">
          <el-card>
            <template #header>
              <span>会计期间管理</span>
            </template>

            <el-table :data="fiscalPeriods" border>
              <el-table-column prop="period_code" label="期间" width="100" />
              <el-table-column prop="start_date" label="开始日期" width="120" />
              <el-table-column prop="end_date" label="结束日期" width="120" />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="scope">
                  <el-tag :type="scope.row.status === 'open' ? 'success' : 'info'">
                    {{ scope.row.status === 'open' ? '开放' : '已关账' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="closed_by" label="关账人" width="120" />
              <el-table-column prop="closed_at" label="关账时间" width="180" />
              <el-table-column label="操作" width="150">
                <template #default="scope">
                  <el-button
                    v-if="scope.row.status === 'open'"
                    type="danger"
                    size="small"
                    @click="closePeriod(scope.row.period_code)"
                  >
                    关账
                  </el-button>
                  <span v-else class="disabled-text">已关账</span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const activeTab = ref('expense')

// 费用上传
const expenseForm = ref({
  period: new Date().toISOString().slice(0, 7)
})
const selectedFile = ref(null)
const uploading = ref(false)
const uploadResult = ref(null)

// 费用分摊
const allocationForm = ref({
  period: new Date().toISOString().slice(0, 7),
  driver: 'revenue_share'
})
const allocating = ref(false)
const allocationResult = ref(null)

// P&L查询
const pnlQuery = ref({
  platform: '',
  shop_id: '',
  period: new Date().toISOString().slice(0, 7)
})
const pnlData = ref([])
const loadingPnL = ref(false)

// 汇率管理
const fxRates = ref([])
const showFxDialog = ref(false)
const fxForm = ref({
  rate_date: new Date().toISOString().slice(0, 10),
  from_currency: 'USD',
  rate: 7.25
})

// 会计期间
const fiscalPeriods = ref([])

// 下载模板
const downloadTemplate = () => {
  const link = document.createElement('a')
  link.href = '/api/finance/expenses/template'
  link.download = `费用导入模板_${new Date().toISOString().slice(0, 10)}.xlsx`
  link.click()
  ElMessage.success('模板下载中...')
}

// 文件选择
const handleFileSelect = (file) => {
  selectedFile.value = file.raw
}

// 上传费用
const uploadExpenses = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }

  uploading.value = true
  uploadResult.value = null

  try {
    // TODO: 实现文件解析和上传逻辑
    // 这里需要先解析Excel，然后调用/api/finance/expenses/upload
    
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('period_month', expenseForm.value.period)

    const response = await api._post('/finance/expenses/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    uploadResult.value = response
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success('费用导入成功')
    }
  } catch (error) {
    uploadResult.value = {
      success: false,
      message: error.message || '上传失败'
    }
    ElMessage.error('上传失败：' + error.message)
  } finally {
    uploading.value = false
  }
}

// 执行分摊
const runAllocation = async () => {
  allocating.value = true
  allocationResult.value = null

  try {
    const response = await api._post('/finance/expenses/allocate', {
      period_month: allocationForm.value.period,
      driver: allocationForm.value.driver
    })

    allocationResult.value = response
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success('费用分摊完成')
    }
  } catch (error) {
    allocationResult.value = {
      success: false,
      message: error.message || '分摊失败'
    }
    ElMessage.error('分摊失败：' + error.message)
  } finally {
    allocating.value = false
  }
}

// 加载P&L
const loadPnL = async () => {
  loadingPnL.value = true

  try {
    const response = await api._get('/finance/pnl/shop', {
      params: {
        platform_code: pnlQuery.value.platform || undefined,
        shop_id: pnlQuery.value.shop_id || undefined,
        period_month: pnlQuery.value.period
      }
    })

    // 响应拦截器已提取data字段，直接使用
    if (response) {
      pnlData.value = response
    }
  } catch (error) {
    ElMessage.error('加载P&L失败：' + error.message)
  } finally {
    loadingPnL.value = false
  }
}

// 加载汇率
const loadFxRates = async () => {
  try {
    const response = await api._get('/finance/fx-rates')
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      fxRates.value = response
    }
  } catch (error) {
    ElMessage.error('加载汇率失败：' + error.message)
  }
}

// 保存汇率
const saveFxRate = async () => {
  try {
    const response = await api._post('/finance/fx-rates', {
      rate_date: fxForm.value.rate_date,
      from_currency: fxForm.value.from_currency,
      to_currency: 'CNY',
      rate: fxForm.value.rate,
      source: 'manual'
    })

    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success('汇率保存成功')
      showFxDialog.value = false
      loadFxRates()
    }
  } catch (error) {
    ElMessage.error('保存失败：' + error.message)
  }
}

// 加载会计期间
const loadFiscalPeriods = async () => {
  try {
    const response = await api._get('/finance/periods/list', {
      params: {
        year: new Date().getFullYear()
      }
    })

    // 响应拦截器已提取data字段，直接使用
    if (response) {
      fiscalPeriods.value = response
    }
  } catch (error) {
    ElMessage.error('加载会计期间失败：' + error.message)
  }
}

// 关账
const closePeriod = async (periodCode) => {
  try {
    await ElMessageBox.confirm(
      `确认关闭期间 ${periodCode}？关账后不可修改数据。`,
      '关账确认',
      {
        confirmButtonText: '确认关账',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const response = await api._post(`/finance/periods/${periodCode}/close`, {
      closed_by: 'admin'  // TODO: 从用户上下文获取
    })

    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success('关账成功')
      loadFiscalPeriods()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('关账失败：' + error.message)
    }
  }
}

onMounted(() => {
  loadPnL()
  loadFxRates()
  loadFiscalPeriods()
})
</script>

<style scoped>
.finance-management {
  padding: 20px;
}

.header-card {
  margin-bottom: 20px;
}

.header-card h2 {
  margin: 0 0 10px 0;
  font-size: 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.subtitle {
  color: #666;
  margin: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.profit-positive {
  color: #67c23a;
  font-weight: bold;
}

.profit-negative {
  color: #f56c6c;
  font-weight: bold;
}

.disabled-text {
  color: #999;
}
</style>


