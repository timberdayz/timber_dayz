<!--
核心字段选择器组件（DeduplicationFieldsSelector）
v4.14.0新增：用于模板保存时选择核心字段
-->
<template>
  <div class="deduplication-fields-selector">
    <el-card class="selector-card" style="margin-bottom: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>🔑 核心字段选择（必填）</span>
          <el-tooltip content="核心字段用于数据去重，请选择能够唯一标识每行数据的字段" placement="top">
            <el-icon style="cursor: help;"><QuestionFilled /></el-icon>
          </el-tooltip>
        </div>
      </template>
      
      <!-- 提示文本 -->
      <div class="selector-hint" style="margin-bottom: 15px; color: #606266; font-size: 14px;">
        <el-icon><InfoFilled /></el-icon>
        <span>核心字段用于数据去重，请选择能够唯一标识每行数据的字段（如：订单号、产品SKU等）</span>
      </div>
      
      <!-- 推荐字段显示（不自动勾选） -->
      <div v-if="recommendedFields.length > 0" class="recommended-fields" style="margin-bottom: 15px; padding: 10px; background: #f0f9ff; border-radius: 4px;">
        <div style="font-weight: bold; margin-bottom: 5px; color: #409EFF;">
          <el-icon><Star /></el-icon>
          推荐字段（根据数据域）：
        </div>
        <div style="color: #606266; font-size: 13px;">
          {{ recommendedFields.join('、') }}
        </div>
        <div style="margin-top: 5px; color: #909399; font-size: 12px;">
          {{ recommendationReason }}
        </div>
      </div>
      
      <!-- 字段选择器 -->
      <el-checkbox-group v-model="selectedFields" @change="handleFieldChange">
        <div class="fields-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px;">
          <el-checkbox
            v-for="field in availableFields"
            :key="field"
            :label="field"
            :value="field"
            style="margin-right: 0;"
          >
            {{ field }}
          </el-checkbox>
        </div>
      </el-checkbox-group>
      
      <!-- 验证提示 -->
      <div v-if="validationWarning" class="validation-warning" style="margin-top: 15px; padding: 10px; background: #fef0f0; border-left: 4px solid #f56c6c; border-radius: 4px;">
        <el-icon style="color: #f56c6c;"><WarningFilled /></el-icon>
        <span style="color: #f56c6c; margin-left: 5px;">{{ validationWarning }}</span>
      </div>
      
      <!-- 已选择字段显示 -->
      <div v-if="selectedFields.length > 0" class="selected-fields" style="margin-top: 15px; padding: 10px; background: #f0f9ff; border-radius: 4px;">
        <div style="font-weight: bold; margin-bottom: 5px; color: #409EFF;">
          已选择 {{ selectedFields.length }} 个核心字段：
        </div>
        <el-tag
          v-for="field in selectedFields"
          :key="field"
          type="primary"
          style="margin-right: 5px; margin-bottom: 5px;"
        >
          {{ field }}
        </el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled, InfoFilled, Star, WarningFilled } from '@element-plus/icons-vue'
import api from '@/api'

const props = defineProps({
  // 可用的字段列表（从表头字段中选择）
  availableFields: {
    type: Array,
    required: true,
    default: () => []
  },
  // 数据域（用于获取推荐字段）
  dataDomain: {
    type: String,
    default: null
  },
  // 子类型（用于获取推荐字段）
  subDomain: {
    type: String,
    default: null
  },
  // 初始选中的字段（用于编辑现有模板）
  initialFields: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:selectedFields', 'validation-change'])

// 选中的字段
const selectedFields = ref([])

// 推荐的字段
const recommendedFields = ref([])
const recommendationReason = ref('')

// 验证警告
const validationWarning = ref('')

// 加载推荐字段
const loadRecommendedFields = async () => {
  if (!props.dataDomain) {
    return
  }
  
  try {
    const result = await api.getDefaultDeduplicationFields({
      dataDomain: props.dataDomain,
      subDomain: props.subDomain
    })
    
    if (result && result.success && result.data) {
      recommendedFields.value = result.data.fields || []
      recommendationReason.value = result.data.reason || ''
    }
  } catch (error) {
    console.warn('获取推荐字段失败:', error)
    // 失败不影响使用，只是没有推荐
  }
}

// 验证字段选择
const validateFields = () => {
  validationWarning.value = ''
  
  if (selectedFields.value.length === 0) {
    validationWarning.value = '请至少选择1个核心字段'
    emit('validation-change', false)
    return false
  }
  
  // 验证选择的字段是否在可用字段中
  const missingFields = selectedFields.value.filter(
    field => !props.availableFields.some(
      af => af === field || af.toLowerCase() === field.toLowerCase()
    )
  )
  
  if (missingFields.length > 0) {
    validationWarning.value = `以下字段不在表头中：${missingFields.join('、')}，可能导致去重失败`
    // 警告但不阻止保存
  }
  
  emit('validation-change', selectedFields.value.length > 0)
  return selectedFields.value.length > 0
}

// 字段选择变化处理
const handleFieldChange = () => {
  validateFields()
  emit('update:selectedFields', selectedFields.value)
}

// 监听可用字段变化，重新验证
watch(() => props.availableFields, () => {
  validateFields()
}, { deep: true })

// 监听初始字段变化（用于编辑现有模板）
watch(() => props.initialFields, (newFields) => {
  if (newFields && newFields.length > 0 && selectedFields.value.length === 0) {
    selectedFields.value = [...newFields]
    validateFields()
  }
}, { immediate: true })

// 组件挂载时加载推荐字段
onMounted(() => {
  loadRecommendedFields()
  
  // 如果有初始字段，设置选中
  if (props.initialFields && props.initialFields.length > 0) {
    selectedFields.value = [...props.initialFields]
    validateFields()
  }
})

// 暴露方法供父组件调用
defineExpose({
  getSelectedFields: () => selectedFields.value,
  validate: validateFields,
  clear: () => {
    selectedFields.value = []
    validateFields()
  }
})
</script>

<style scoped>
.deduplication-fields-selector {
  width: 100%;
}

.selector-card {
  border: 1px solid #e4e7ed;
}

.selector-hint {
  display: flex;
  align-items: center;
  gap: 5px;
}

.fields-grid {
  max-height: 300px;
  overflow-y: auto;
  padding: 10px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.validation-warning {
  display: flex;
  align-items: center;
}

.selected-fields {
  display: flex;
  flex-direction: column;
}
</style>

