<template>
  <div class="account-alignment">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>🏪 妙手账号对齐</h1>
      <p>店铺别名管理 • 账号级数据归并 • 智能建议</p>
    </div>

    <!-- 对齐统计看板 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card>
          <el-statistic title="总订单数" :value="stats.total_orders" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="已对齐" :value="stats.aligned">
            <template #suffix>
              <el-tag type="success">{{ stats.coverage_rate }}%</el-tag>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="未对齐" :value="stats.unaligned">
            <template #suffix>
              <el-tag type="warning">{{ (100 - stats.coverage_rate).toFixed(1) }}%</el-tag>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="待配置店铺" :value="stats.unique_raw_labels" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 操作按钮 -->
    <div class="action-buttons">
      <el-button type="primary" size="large" @click="loadData" :loading="loading">
        <el-icon><Refresh /></el-icon>
        刷新数据
      </el-button>
      
      <el-button type="success" size="large" @click="showSuggestions" :loading="loading">
        <el-icon><MagicStick /></el-icon>
        查看智能建议
      </el-button>
      
      <el-button type="warning" size="large" @click="executeBackfill" :loading="backfilling">
        <el-icon><Connection /></el-icon>
        执行对齐回填
      </el-button>
      
      <el-button size="large" @click="showImportDialog">
        <el-icon><Upload /></el-icon>
        批量导入
      </el-button>
      
      <el-button size="large" @click="exportYaml">
        <el-icon><Download /></el-icon>
        导出YAML
      </el-button>
    </div>

    <!-- 未对齐店铺列表 -->
    <el-card class="unaligned-stores">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>⚠️ 未对齐店铺 ({{ unalignedStores.length }})</span>
          <el-button size="small" type="primary" @click="batchAddFromUnaligned">
            批量配置选中项
          </el-button>
        </div>
      </template>

      <el-table
        :data="unalignedStores"
        @selection-change="handleSelectionChange"
        stripe
        border
        max-height="400"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="store_label_raw" label="原始店铺名" min-width="150" />
        <el-table-column prop="account" label="账号" min-width="180" show-overflow-tooltip />
        <el-table-column prop="site" label="站点" width="100" />
        <el-table-column prop="order_count" label="订单数" width="100" sortable />
        <el-table-column prop="total_gmv" label="GMV" width="120" sortable>
          <template #default="scope">
            ¥{{ scope.row.total_gmv.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="建议ID" min-width="150">
          <template #default="scope">
            <el-tag type="info">{{ scope.row.suggested_target_id }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" @click="quickAdd(scope.row)">
              快速配置
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 已配置别名列表 -->
    <el-card class="configured-aliases">
      <template #header>
        <span>✅ 已配置别名 ({{ configuredAliases.length }})</span>
      </template>

      <el-table
        :data="configuredAliases"
        stripe
        border
        max-height="400"
      >
        <el-table-column prop="store_label_raw" label="原始店铺名" min-width="150" />
        <el-table-column prop="account" label="账号" min-width="180" show-overflow-tooltip />
        <el-table-column prop="site" label="站点" width="100" />
        <el-table-column prop="target_id" label="标准账号ID" min-width="150">
          <template #default="scope">
            <el-tag type="success">{{ scope.row.target_id }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="notes" label="备注" min-width="150" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建时间" width="160" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="editAlias(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteAlias(scope.row.id)">停用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 快速配置对话框 -->
    <el-dialog v-model="quickAddDialogVisible" title="快速配置别名" width="600px">
      <el-form :model="quickAddForm" label-width="120px">
        <el-form-item label="原始店铺名">
          <el-input v-model="quickAddForm.store_label_raw" disabled />
        </el-form-item>
        <el-form-item label="账号">
          <el-input v-model="quickAddForm.account" disabled />
        </el-form-item>
        <el-form-item label="站点">
          <el-input v-model="quickAddForm.site" disabled />
        </el-form-item>
        <el-form-item label="标准账号ID" required>
          <el-input 
            v-model="quickAddForm.target_id" 
            placeholder="如: shopee_ph_1"
          >
            <template #append>
              <el-button @click="quickAddForm.target_id = quickAddForm.suggested_target_id">
                采纳建议
              </el-button>
            </template>
          </el-input>
          <el-text size="small" type="info" style="margin-top: 4px;">
            系统建议: {{ quickAddForm.suggested_target_id }}
          </el-text>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="quickAddForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="quickAddDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmQuickAdd" :loading="saving">确认添加</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入对话框 -->
    <el-dialog v-model="importDialogVisible" title="批量导入别名" width="700px">
      <el-tabs v-model="importTab">
        <el-tab-pane label="YAML导入" name="yaml">
          <el-upload
            drag
            :auto-upload="false"
            :on-change="handleYamlUpload"
            :limit="1"
            accept=".yaml,.yml"
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">
              拖拽YAML文件到此或 <em>点击选择</em>
            </div>
          </el-upload>
        </el-tab-pane>
        
        <el-tab-pane label="CSV导入" name="csv">
          <el-upload
            drag
            :auto-upload="false"
            :on-change="handleCsvUpload"
            :limit="1"
            accept=".csv"
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">
              拖拽CSV文件到此或 <em>点击选择</em>
            </div>
          </el-upload>
          <el-text size="small" type="info" style="margin-top: 8px;">
            CSV格式：account,site,store_label_raw,target_id,notes
          </el-text>
        </el-tab-pane>
      </el-tabs>
      
      <template #footer>
        <el-button @click="importDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 智能建议对话框 -->
    <el-dialog v-model="suggestionsDialogVisible" title="智能建议" width="800px">
      <el-alert
        title="基于订单数量和GMV的智能建议"
        type="info"
        :closable="false"
        style="margin-bottom: 16px"
      />
      
      <el-table :data="suggestions" stripe border max-height="500">
        <el-table-column prop="store_label_raw" label="店铺名" min-width="120" />
        <el-table-column prop="order_count" label="订单数" width="100" sortable />
        <el-table-column prop="suggested_target_id" label="建议ID" min-width="150">
          <template #default="scope">
            <el-tag>{{ scope.row.suggested_target_id }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="scope">
            <el-button size="small" type="success" @click="adoptSuggestion(scope.row)">
              采纳
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <template #footer>
        <el-button @click="suggestionsDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="adoptAllSuggestions">一键采纳全部</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, MagicStick, Connection, Upload, Download, UploadFilled } from '@element-plus/icons-vue'
import api from '../api'

// 状态
const loading = ref(false)
const backfilling = ref(false)
const saving = ref(false)

const stats = ref({
  total_orders: 0,
  aligned: 0,
  unaligned: 0,
  coverage_rate: 0,
  unique_raw_labels: 0
})

const unalignedStores = ref([])
const configuredAliases = ref([])
const selectedStores = ref([])
const suggestions = ref([])

// 对话框
const quickAddDialogVisible = ref(false)
const importDialogVisible = ref(false)
const suggestionsDialogVisible = ref(false)
const importTab = ref('yaml')

const quickAddForm = ref({
  account: '',
  site: '',
  store_label_raw: '',
  target_id: '',
  suggested_target_id: '',
  notes: ''
})

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    await Promise.all([
      loadStats(),
      loadUnalignedStores(),
      loadConfiguredAliases()
    ])
    ElMessage.success('数据加载完成')
  } catch (error) {
    ElMessage.error('加载数据失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  const response = await api._get('/account-alignment/stats')
  // 响应拦截器已提取data字段，直接使用
  if (response) {
    stats.value = response.stats || response
  }
}

const loadUnalignedStores = async () => {
  const response = await api._get('/account-alignment/distinct-raw-stores')
  // 响应拦截器已提取data字段，直接使用
  if (response) {
    unalignedStores.value = response.stores || response || []
  }
}

const loadConfiguredAliases = async () => {
  const response = await api._get('/account-alignment/list-aliases')
  // 响应拦截器已提取data字段，直接使用
  if (response) {
    configuredAliases.value = response.aliases || response || []
  }
}

// 快速配置
const quickAdd = (store) => {
  quickAddForm.value = {
    account: store.account,
    site: store.site,
    store_label_raw: store.store_label_raw,
    target_id: store.suggested_target_id,
    suggested_target_id: store.suggested_target_id,
    notes: `订单数: ${store.order_count}, GMV: ¥${store.total_gmv.toFixed(2)}`
  }
  quickAddDialogVisible.value = true
}

const confirmQuickAdd = async () => {
  if (!quickAddForm.value.target_id) {
    ElMessage.warning('请输入标准账号ID')
    return
  }
  
  saving.value = true
  try {
    const response = await api._post('/account-alignment/add-alias', quickAddForm.value)
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success('别名添加成功')
      quickAddDialogVisible.value = false
      await loadData()
    }
  } catch (error) {
    ElMessage.error('添加失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

// 批量配置
const handleSelectionChange = (selection) => {
  selectedStores.value = selection
}

const batchAddFromUnaligned = async () => {
  if (selectedStores.value.length === 0) {
    ElMessage.warning('请先选择店铺')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确定批量配置 ${selectedStores.value.length} 个店铺吗？将使用系统建议的账号ID。`,
      '批量配置',
      { type: 'warning' }
    )
    
    const mappings = selectedStores.value.map(store => ({
      account: store.account,
      site: store.site,
      store_label_raw: store.store_label_raw,
      target_id: store.suggested_target_id,
      notes: `批量配置: 订单${store.order_count}个`
    }))
    
    saving.value = true
    const response = await api._post('/account-alignment/batch-add-aliases', { mappings })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success(response.message || '批量添加成功')
      await loadData()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量配置失败')
    }
  } finally {
    saving.value = false
  }
}

// 执行回填
const executeBackfill = async () => {
  try {
    await ElMessageBox.confirm(
      '确定执行对齐回填吗？这将根据别名表更新所有未对齐订单的账号ID。',
      '确认回填',
      { type: 'warning' }
    )
    
    backfilling.value = true
    const response = await api._post('/account-alignment/backfill')
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success(response.message || '回填成功')
      await loadData()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('回填失败')
    }
  } finally {
    backfilling.value = false
  }
}

// 智能建议
const showSuggestions = async () => {
  loading.value = true
  try {
    const response = await api._get('/account-alignment/suggestions', { min_orders: 5 })
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      suggestions.value = response.suggestions || response || []
      suggestionsDialogVisible.value = true
    }
  } catch (error) {
    ElMessage.error('获取建议失败')
  } finally {
    loading.value = false
  }
}

const adoptSuggestion = (suggestion) => {
  quickAdd(suggestion)
}

const adoptAllSuggestions = async () => {
  try {
    await ElMessageBox.confirm(
      `确定采纳全部 ${suggestions.value.length} 个建议吗？`,
      '批量采纳',
      { type: 'warning' }
    )
    
    const mappings = suggestions.value.map(s => ({
      account: s.account,
      site: s.site,
      store_label_raw: s.store_label_raw,
      target_id: s.suggested_target_id,
      notes: `智能建议: 订单${s.order_count}个`
    }))
    
    saving.value = true
    const response = await api._post('/account-alignment/batch-add-aliases', { mappings })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success(response.message || '批量添加成功')
      suggestionsDialogVisible.value = false
      await loadData()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量采纳失败')
    }
  } finally {
    saving.value = false
  }
}

// 编辑/删除
const editAlias = (alias) => {
  ElMessageBox.prompt('请输入新的标准账号ID', '编辑别名', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputValue: alias.target_id,
    inputPattern: /^[a-z0-9_]{3,64}$/,
    inputErrorMessage: '格式错误（仅小写字母数字下划线，3-64位）'
  }).then(async ({ value }) => {
    try {
      const response = await api._put(`/account-alignment/update-alias/${alias.id}`, {
        target_id: value
      })
      // 响应拦截器已提取data字段，直接使用
      if (response) {
        ElMessage.success('更新成功')
        await loadData()
      }
    } catch (error) {
      ElMessage.error('更新失败')
    }
  }).catch(() => {})
}

const deleteAlias = async (aliasId) => {
  try {
    await ElMessageBox.confirm('确定停用此别名吗？', '确认停用', { type: 'warning' })
    
    const response = await api._delete(`/account-alignment/delete-alias/${aliasId}`)
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success('已停用')
      await loadData()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('停用失败')
    }
  }
}

// 导入/导出
const showImportDialog = () => {
  importDialogVisible.value = true
}

const handleYamlUpload = async (file) => {
  const formData = new FormData()
  formData.append('file', file.raw)
  
  try {
    const response = await fetch('/api/account-alignment/import-yaml', {
      method: 'POST',
      body: formData
    })
    const result = await response.json()
    
    if (result.success) {
      ElMessage.success(result.message)
      importDialogVisible.value = false
      await loadData()
    } else {
      ElMessage.error(result.message || '导入失败')
    }
  } catch (error) {
    ElMessage.error('YAML导入失败')
  }
}

const handleCsvUpload = async (file) => {
  const formData = new FormData()
  formData.append('file', file.raw)
  
  try {
    const response = await fetch('/api/account-alignment/import-csv', {
      method: 'POST',
      body: formData
    })
    const result = await response.json()
    
    if (result.success) {
      ElMessage.success(result.message)
      importDialogVisible.value = false
      await loadData()
    } else {
      ElMessage.error(result.message || '导入失败')
    }
  } catch (error) {
    ElMessage.error('CSV导入失败')
  }
}

const exportYaml = async () => {
  try {
    window.open('/api/account-alignment/export-yaml?platform=miaoshou', '_blank')
    ElMessage.success('导出已开始')
  } catch (error) {
    ElMessage.error('导出失败')
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.account-alignment {
  padding: var(--content-padding);
}

.page-header {
  text-align: center;
  margin-bottom: var(--spacing-2xl);
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: var(--spacing-2xl);
  border-radius: var(--border-radius-lg);
}

.page-header h1 {
  margin: 0 0 var(--spacing-base) 0;
  font-size: var(--font-size-4xl);
}

.stats-row {
  margin-bottom: var(--spacing-xl);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-base);
  margin-bottom: var(--spacing-xl);
  justify-content: center;
}

.unaligned-stores,
.configured-aliases {
  margin-bottom: var(--spacing-xl);
}
</style>

