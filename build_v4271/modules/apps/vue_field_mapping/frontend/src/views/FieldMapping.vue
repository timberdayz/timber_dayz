<template>
  <div class="field-mapping-container">
    <!-- 状态栏 -->
    <el-alert 
      v-if="statusMessage" 
      :title="statusMessage" 
      :type="statusType" 
      :closable="false" 
      show-icon 
      style="margin-bottom: 20px"
    />

    <!-- 顶部操作栏 -->
    <el-card class="action-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <h3>🎯 智能字段映射审核系统</h3>
          <div class="header-actions">
            <el-button 
              type="primary" 
              :loading="dataStore.loading.scan"
              @click="handleScanFiles"
            >
              <el-icon><Search /></el-icon>
              {{ dataStore.loading.scan ? '扫描中...' : '扫描采集文件' }}
            </el-button>
            <el-button 
              type="info" 
              :loading="dataStore.loading.cleanup"
              @click="handleCleanup"
            >
              <el-icon><Delete /></el-icon>
              清理无效文件
            </el-button>
          </div>
        </div>
      </template>

      <!-- 错误提示 -->
      <el-alert 
        v-if="dataStore.error" 
        :title="dataStore.error" 
        type="error" 
        show-icon 
        closable 
        @close="dataStore.error = null"
      />

      <!-- 文件选择器 -->
      <div v-if="dataStore.fileGroups" class="file-selectors">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-select
              v-model="selectedPlatform"
              placeholder="选择平台"
              filterable
              @change="handlePlatformChange"
              style="width: 100%"
            >
              <el-option
                v-for="platform in dataStore.platforms"
                :key="platform"
                :label="platform.toUpperCase()"
                :value="platform"
              />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-select
              v-model="selectedDomain"
              placeholder="选择数据域"
              filterable
              @change="handleDomainChange"
              :disabled="!selectedPlatform"
              style="width: 100%"
            >
              <el-option
                v-for="domain in Object.keys(dataStore.domains)"
                :key="domain"
                :label="domain"
                :value="domain"
              />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-date-picker
              v-model="selectedDate"
              type="date"
              placeholder="选择日期"
              style="width: 100%"
            />
          </el-col>
          <el-col :span="6">
            <el-select
              v-model="selectedFileName"
              placeholder="选择文件"
              filterable
              @change="handleFileChange"
              :disabled="!selectedDomain"
              style="width: 100%"
            >
              <el-option
                v-for="file in currentFiles"
                :key="file"
                :label="getFileName(file)"
                :value="file"
              />
            </el-select>
          </el-col>
          <el-col :span="2">
            <el-button 
              type="primary" 
              @click="generateAutoMapping" 
              :loading="autoMappingLoading"
              :disabled="!selectedFileName"
              style="width: 100%"
            >
              🤖 智能映射
            </el-button>
          </el-col>
        </el-row>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!dataStore.loading.scan" class="empty-state">
        <el-empty description="请点击上方按钮扫描采集文件" />
      </div>
    </el-card>

    <!-- 文件预览 -->
    <el-card v-if="dataStore.filePreview" class="preview-card" shadow="hover">
      <template #header>
        <div style="display:flex;align-items:center;gap:12px;">
          <h4 style="margin:0;">📊 文件预览</h4>
          <el-input-number v-model="headerRow" :min="0" :max="50" :step="1" controls-position="right" style="width:140px;" />
          <span>表头行</span>
          <el-select v-if="selectedDomain==='product_metrics'" v-model="granularity" placeholder="粒度" style="width:140px;">
            <el-option label="hour" value="hour" />
            <el-option label="day" value="day" />
            <el-option label="week" value="week" />
            <el-option label="month" value="month" />
          </el-select>
          <el-button size="small" @click="applyTemplate">套用模板</el-button>
          <el-button size="small" type="warning" @click="saveTemplate">保存为模板</el-button>
        </div>
      </template>
      
      <el-skeleton :loading="dataStore.loading.preview" animated :rows="5">
        <template #default>
          <el-table 
            :data="dataStore.filePreview.data" 
            style="width: 100%" 
            border 
            max-height="300"
            v-loading="dataStore.loading.preview"
          >
            <el-table-column
              v-for="col in dataStore.filePreview.columns"
              :key="col"
              :prop="col"
              :label="col"
              show-overflow-tooltip
              width="150"
            />
          </el-table>
        </template>
      </el-skeleton>
    </el-card>

    <!-- 字段映射 -->
    <el-card v-if="mappingResults" class="mapping-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <h4>🔗 智能字段映射</h4>
          <div class="mapping-stats">
            <el-tag type="success">总映射: {{ Object.keys(mappingResults.mappings).length }}</el-tag>
            <el-tag type="warning">高置信度: {{ highConfidenceCount }}</el-tag>
            <el-tag type="info" v-if="hasForeignKeys">外键: {{ Object.keys(mappingResults.foreign_keys).length }}</el-tag>
          </div>
        </div>
      </template>
      
      <el-table :data="mappingTableData" style="width: 100%" border>
        <el-table-column prop="original" label="原始字段" width="200" />
        <el-table-column prop="standard" label="标准字段" width="200" />
        <el-table-column prop="confidence" label="置信度" width="120">
          <template #default="{ row }">
            <el-tag :type="getConfidenceType(row.confidence)">
              {{ row.confidence }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag v-if="isForeignKey(row.original)" type="info" size="small">外键</el-tag>
            <el-tag v-else type="success" size="small">字段</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- 外键审核区域 -->
      <div v-if="hasForeignKeys" class="foreign-key-section" style="margin-top: 20px;">
        <h5>🔗 外键关系审核</h5>
        <el-card v-for="(fkInfo, column) in mappingResults.foreign_keys" :key="column" class="fk-card" style="margin-bottom: 10px;">
          <div class="fk-info">
            <span class="fk-label">{{ column }}</span>
            <span class="fk-arrow">→</span>
            <span class="fk-target">{{ fkInfo.target_table }}.{{ fkInfo.target_field }}</span>
          </div>
          <div class="fk-actions">
            <el-button size="small" type="success" @click="confirmForeignKey(column)">确认</el-button>
            <el-button size="small" @click="editForeignKey(column)">编辑</el-button>
          </div>
        </el-card>
      </div>
    </el-card>

    <!-- 数据验证结果 -->
    <el-card v-if="validationResult" class="validation-card" shadow="hover">
      <template #header>
        <h4>✅ 数据验证结果</h4>
      </template>
      
      <div class="validation-summary">
        <el-row :gutter="20">
          <el-col :span="6">
            <div class="summary-item" :class="{ 'error': !validationResult.is_valid }">
              <span class="summary-label">验证状态:</span>
              <span class="summary-value">
                {{ validationResult.is_valid ? '通过' : '失败' }}
              </span>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="summary-item">
              <span class="summary-label">错误数:</span>
              <span class="summary-value error">{{ validationResult.errors.length }}</span>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="summary-item">
              <span class="summary-label">警告数:</span>
              <span class="summary-value warning">{{ validationResult.warnings.length }}</span>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="summary-item">
              <span class="summary-label">错误率:</span>
              <span class="summary-value">{{ (validationResult.statistics.error_rate * 100).toFixed(1) }}%</span>
            </div>
          </el-col>
        </el-row>
      </div>
      
      <!-- 错误详情 -->
      <div v-if="validationResult.errors.length > 0" class="error-details" style="margin-top: 20px;">
        <h5>错误详情</h5>
        <el-table :data="validationResult.errors.slice(0, 10)" border>
          <el-table-column prop="row_index" label="行号" width="80" />
          <el-table-column prop="column_name" label="列名" width="120" />
          <el-table-column prop="error_type" label="错误类型" width="120" />
          <el-table-column prop="error_message" label="错误信息" />
          <el-table-column prop="current_value" label="当前值" width="100" />
          <el-table-column prop="suggestion" label="建议" />
        </el-table>
      </div>
      
      <!-- 修复建议 -->
      <div v-if="validationResult.recommendations.length > 0" class="recommendations" style="margin-top: 20px;">
        <h5>修复建议</h5>
        <ul>
          <li v-for="rec in validationResult.recommendations" :key="rec">{{ rec }}</li>
        </ul>
      </div>
    </el-card>

    <!-- 操作按钮 -->
    <el-card v-if="dataStore.filePreview" class="action-card" shadow="hover">
      <template #header>
        <h4>⚡ 操作</h4>
      </template>
      
      <el-row :gutter="20">
        <el-col :span="6">
          <el-button
            type="info"
            size="large"
            @click="validateData"
            :loading="validationLoading"
            :disabled="!hasMappings"
            style="width: 100%"
          >
            🔍 验证数据
          </el-button>
        </el-col>
        <el-col :span="6">
          <el-button
            type="success"
            size="large"
            :loading="ingestionLoading"
            @click="ingestData"
            :disabled="!validationResult || !validationResult.is_valid"
            style="width: 100%"
          >
            📥 数据入库
          </el-button>
        </el-col>
        <el-col :span="6">
          <el-button 
            type="warning" 
            size="large" 
            @click="generateAutoMapping"
            :loading="autoMappingLoading"
            style="width: 100%"
          >
            🤖 重新映射
          </el-button>
        </el-col>
        <el-col :span="6">
          <el-button 
            type="info" 
            size="large" 
            @click="resetMapping"
            style="width: 100%"
          >
            🔄 重置映射
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 入库结果对话框 -->
    <el-dialog
      v-model="ingestResultVisible"
      title="🎉 入库结果"
      width="400px"
      center
    >
      <div v-if="ingestResult">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="待处理">{{ ingestResult.stats?.picked || 0 }}</el-descriptions-item>
          <el-descriptions-item label="成功">{{ ingestResult.stats?.succeeded || 0 }}</el-descriptions-item>
          <el-descriptions-item label="失败">{{ ingestResult.stats?.failed || 0 }}</el-descriptions-item>
        </el-descriptions>
        
        <div style="margin-top: 15px">
          <el-alert 
            v-if="ingestResult.success" 
            title="文件入库成功！" 
            type="success" 
            show-icon 
          />
          <el-alert 
            v-else 
            title="文件入库失败，请查看日志" 
            type="error" 
            show-icon 
          />
        </div>
      </div>
      
      <template #footer>
        <el-button type="primary" @click="ingestResultVisible = false">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useDataStore } from '../stores/data'
import { ElMessage, ElMessageBox } from 'element-plus'

const dataStore = useDataStore()

// 响应式数据
const selectedPlatform = ref('')
const selectedDomain = ref('')
const selectedFileName = ref('')
const selectedDate = ref('')
const ingestResultVisible = ref(false)
const ingestResult = ref(null)
const headerRow = ref(0)
const granularity = ref('')

// 新增：智能映射相关
const autoMappingLoading = ref(false)
const validationLoading = ref(false)
const ingestionLoading = ref(false)
const mappingResults = ref(null)
const validationResult = ref(null)
const currentMappings = ref({})
const statusMessage = ref('')
const statusType = ref('info')

// 计算属性
const currentFiles = computed(() => {
  if (selectedPlatform.value && selectedDomain.value && dataStore.files[selectedPlatform.value]) {
    return dataStore.files[selectedPlatform.value][selectedDomain.value] || []
  }
  return []
})

const mappingTableData = computed(() => {
  if (mappingResults.value) {
    return Object.entries(mappingResults.value.mappings).map(([original, standard]) => ({
      original,
      standard,
      confidence: Math.round((mappingResults.value.confidence[original] || 0) * 100)
    }))
  }
  return []
})

// 新增：智能映射相关计算属性
const highConfidenceCount = computed(() => {
  if (!mappingResults.value) return 0
  return Object.values(mappingResults.value.confidence || {})
    .filter(conf => conf > 0.8).length
})

const hasForeignKeys = computed(() => {
  return mappingResults.value && 
         mappingResults.value.foreign_keys && 
         Object.keys(mappingResults.value.foreign_keys).length > 0
})

const hasMappings = computed(() => {
  return Object.keys(currentMappings.value).length > 0
})

const previewColumns = computed(() => {
  return dataStore.filePreview?.columns || []
})

const targetFields = computed(() => {
  const fieldMap = {
    'products': ['product_id', 'product_name', 'product_sku', 'product_price', 'shop_id', 'platform_code', 'currency', 'quantity', 'status'],
    'orders': ['order_id', 'order_amount', 'order_date', 'shop_id', 'customer_id', 'currency', 'status', 'payment_method'],
    'traffic': ['date', 'shop_id', 'visits', 'page_views', 'bounce_rate', 'avg_session_duration', 'platform_code'],
    'service': ['date', 'shop_id', 'service_type', 'service_count', 'resolution_time', 'platform_code', 'status']
  }
  return fieldMap[selectedDomain.value] || fieldMap['products']
})

// 方法
const handleScanFiles = async () => {
  try {
    await dataStore.scanFilesAction()
    // 自动选择第一个平台和数据域
    if (dataStore.platforms.length > 0) {
      selectedPlatform.value = dataStore.platforms[0]
      handlePlatformChange(selectedPlatform.value)
    }
  } catch (error) {
    console.error('扫描失败:', error)
  }
}

const handlePlatformChange = (platform) => {
  selectedDomain.value = ''
  selectedFileName.value = ''
  if (dataStore.domains && Object.keys(dataStore.domains).length > 0) {
    selectedDomain.value = Object.keys(dataStore.domains)[0]
    handleDomainChange(selectedDomain.value)
  }
}

const handleDomainChange = (domain) => {
  selectedFileName.value = ''
  if (currentFiles.value.length > 0) {
    selectedFileName.value = currentFiles.value[0]
    handleFileChange(selectedFileName.value)
  }
}

const handleFileChange = async (fileName) => {
  if (fileName && selectedPlatform.value && selectedDomain.value) {
    try {
      await dataStore.selectFile(fileName, selectedPlatform.value, selectedDomain.value)
      // 自动生成智能映射
      if (dataStore.filePreview?.columns) {
        await generateAutoMapping()
      }
    } catch (error) {
      console.error('选择文件失败:', error)
    }
  }
}

// 新增：智能映射相关方法
const generateAutoMapping = async () => {
  if (!dataStore.filePreview?.columns || !selectedPlatform.value || !selectedDomain.value) {
    ElMessage.warning('请先选择文件')
    return
  }

  autoMappingLoading.value = true
  try {
    const response = await fetch('/api/field-mapping/generate-mapping', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        columns: dataStore.filePreview.columns,
        platform: selectedPlatform.value,
        domain: selectedDomain.value,
        granularity: granularity.value || null
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()
    mappingResults.value = result
    currentMappings.value = { ...result.mappings }
    
    // 显示状态消息
    statusMessage.value = `智能映射完成：生成了 ${Object.keys(result.mappings).length} 个映射，其中 ${highConfidenceCount.value} 个高置信度映射`
    statusType.value = 'success'
    
    ElMessage.success('智能映射生成成功！')
  } catch (error) {
    console.error('生成智能映射失败:', error)
    ElMessage.error('生成智能映射失败：' + error.message)
    statusMessage.value = '智能映射生成失败'
    statusType.value = 'error'
  } finally {
    autoMappingLoading.value = false
  }
}

// 模板应用/保存
const applyTemplate = async () => {
  if (!dataStore.filePreview?.columns) return
  try {
    const res = await fetch('/api/field-mapping/apply-template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        columns: dataStore.filePreview.columns,
        platform: selectedPlatform.value,
        domain: selectedDomain.value,
        granularity: granularity.value || null,
        sheet_name: null
      })
    })
    const result = await res.json()
    if (result.success) {
      mappingResults.value = { mappings: Object.fromEntries(Object.entries(result.mappings).map(([k,v]) => [k, v.standard || v])), confidence: {} }
      currentMappings.value = { ...mappingResults.value.mappings }
      ElMessage.success('模板已应用')
    }
  } catch (e) {
    ElMessage.error('应用模板失败')
  }
}

const saveTemplate = async () => {
  try {
    const res = await fetch('/api/field-mapping/save-template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mappings: Object.fromEntries(Object.entries(currentMappings.value).map(([k,v]) => [k, { standard: v, confidence: 1 }])),
        platform: selectedPlatform.value,
        domain: selectedDomain.value,
        granularity: granularity.value || null,
        sheet_name: null,
        header_row: headerRow.value
      })
    })
    const result = await res.json()
    if (result.success) ElMessage.success('模板已保存')
  } catch (e) {
    ElMessage.error('保存模板失败')
  }
}

const validateData = async () => {
  if (!currentMappings.value || Object.keys(currentMappings.value).length === 0) {
    ElMessage.warning('请先生成字段映射')
    return
  }

  validationLoading.value = true
  try {
    const response = await fetch('/api/validate-data', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_path: selectedFileName.value,
        platform: selectedPlatform.value,
        data_domain: selectedDomain.value,
        mappings: currentMappings.value
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()
    validationResult.value = result
    
    if (result.is_valid) {
      statusMessage.value = `数据验证通过：${result.statistics.total_rows} 行数据，错误率 ${(result.statistics.error_rate * 100).toFixed(1)}%`
      statusType.value = 'success'
      ElMessage.success('数据验证通过！')
    } else {
      statusMessage.value = `数据验证失败：发现 ${result.errors.length} 个错误，${result.warnings.length} 个警告`
      statusType.value = 'warning'
      ElMessage.warning(`数据验证失败：${result.errors.length} 个错误`)
    }
  } catch (error) {
    console.error('数据验证失败:', error)
    ElMessage.error('数据验证失败：' + error.message)
    statusMessage.value = '数据验证失败'
    statusType.value = 'error'
  } finally {
    validationLoading.value = false
  }
}

const ingestData = async () => {
  if (!validationResult.value || !validationResult.value.is_valid) {
    ElMessage.warning('请先通过数据验证')
    return
  }

  ingestionLoading.value = true
  try {
    const response = await fetch('/api/ingest', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_path: selectedFileName.value,
        platform: selectedPlatform.value,
        data_domain: selectedDomain.value,
        mappings: currentMappings.value
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()
    ingestResult.value = result
    ingestResultVisible.value = true
    
    if (result.success) {
      statusMessage.value = `数据入库成功：处理了 ${result.stats?.succeeded || 0} 行数据`
      statusType.value = 'success'
      ElMessage.success('数据入库成功！')
    } else {
      statusMessage.value = '数据入库失败'
      statusType.value = 'error'
      ElMessage.error('数据入库失败')
    }
  } catch (error) {
    console.error('数据入库失败:', error)
    ElMessage.error('数据入库失败：' + error.message)
    statusMessage.value = '数据入库失败'
    statusType.value = 'error'
  } finally {
    ingestionLoading.value = false
  }
}

const onMappingChange = (column, targetField) => {
  if (targetField) {
    currentMappings.value[column] = targetField
  } else {
    delete currentMappings.value[column]
  }
}

const getMappingConfidence = (column) => {
  return mappingResults.value?.confidence?.[column] || 0
}

const getRecommendedMapping = (column) => {
  return mappingResults.value?.mappings?.[column] || ''
}

const isForeignKey = (column) => {
  return mappingResults.value?.foreign_keys?.[column] !== undefined
}

const confirmForeignKey = (column) => {
  ElMessage.success(`已确认外键映射：${column}`)
}

const editForeignKey = (column) => {
  ElMessage.info(`编辑外键映射：${column}`)
}

const resetMapping = () => {
  currentMappings.value = {}
  mappingResults.value = null
  validationResult.value = null
  statusMessage.value = ''
  ElMessage.info('映射已重置')
}

const handleIngestFile = async () => {
  if (!selectedFileName.value || !selectedPlatform.value || !selectedDomain.value) {
    ElMessage.warning('请先选择文件、平台和数据域')
    return
  }
  
  try {
    const result = await dataStore.performIngestion(
      selectedFileName.value,
      selectedPlatform.value,
      selectedDomain.value,
      dataStore.mappingSuggestions
    )
    ingestResult.value = result
    ingestResultVisible.value = true
  } catch (error) {
    console.error('入库失败:', error)
  }
}

const handleCleanup = async () => {
  try {
    await ElMessageBox.confirm(
      '此操作将清理数据库中指向不存在的本地文件的记录，是否继续？',
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await dataStore.performCleanup()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('清理失败:', error)
    }
  }
}

const editMapping = (row) => {
  ElMessage.info(`编辑映射: ${row.original} -> ${row.standard}`)
}

const getConfidenceType = (confidence) => {
  if (confidence >= 90) return 'success'
  if (confidence >= 80) return 'warning'
  return 'danger'
}

const getFileName = (filePath) => {
  return filePath.split('/').pop().split('\\').pop()
}

// 生命周期
onMounted(() => {
  dataStore.loadInitialData()
})

// 监听器
watch(() => dataStore.fileGroups, (newVal) => {
  if (newVal && dataStore.platforms.length > 0 && !selectedPlatform.value) {
    selectedPlatform.value = dataStore.platforms[0]
    handlePlatformChange(selectedPlatform.value)
  }
}, { immediate: true })

watch(selectedFileName, (newVal) => {
  if (newVal) {
    handleFileChange(newVal)
  }
})
</script>

<style scoped>
.field-mapping-container {
  padding: 20px;
}

.action-card,
.preview-card,
.mapping-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
  color: #2c3e50;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.file-selectors {
  margin-top: 20px;
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.mapping-table {
  margin-top: 15px;
}

.mapping-stats {
  display: flex;
  gap: 10px;
  align-items: center;
}

.foreign-key-section {
  border-top: 1px solid #ebeef5;
  padding-top: 15px;
}

.fk-card {
  border: 1px solid #e4e7ed;
}

.fk-info {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.fk-label {
  font-weight: bold;
  color: #409eff;
}

.fk-arrow {
  color: #909399;
}

.fk-target {
  color: #67c23a;
  font-family: monospace;
}

.fk-actions {
  display: flex;
  gap: 10px;
}

.validation-summary {
  margin-bottom: 20px;
}

.summary-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  border-radius: 4px;
  background-color: #f8f9fa;
  margin-bottom: 10px;
}

.summary-item.error {
  background-color: #fef0f0;
  border-left: 4px solid #f56c6c;
}

.summary-label {
  font-weight: bold;
  color: #606266;
}

.summary-value {
  font-weight: bold;
  color: #67c23a;
}

.summary-value.error {
  color: #f56c6c;
}

.summary-value.warning {
  color: #e6a23c;
}

.error-details h5,
.recommendations h5 {
  color: #303133;
  margin-bottom: 10px;
}

.recommendations ul {
  margin: 0;
  padding-left: 20px;
}

.recommendations li {
  margin-bottom: 5px;
  color: #606266;
}
</style>
