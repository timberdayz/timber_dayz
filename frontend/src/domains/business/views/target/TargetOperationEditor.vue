<template>
  <el-form ref="formRef" :model="modelValue" :rules="rules" label-width="120px">
    <el-form-item label="目标名称" prop="target_name">
      <el-input v-model="modelValue.target_name" placeholder="输入运营目标名称" />
    </el-form-item>
    <el-form-item label="运营指标" prop="metric_code">
      <el-select v-model="modelValue.metric_code" class="erp-w-full" @change="handleMetricChange">
        <el-option
          v-for="item in metricOptions"
          :key="item.code"
          :label="item.label"
          :value="item.code"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="指标方向">
      <el-input :model-value="selectedMetric?.direction || modelValue.metric_direction || '-'" readonly />
    </el-form-item>
    <el-form-item label="考核月份" prop="month">
      <el-date-picker
        v-model="modelValue.month"
        type="month"
        value-format="YYYY-MM"
        placeholder="选择月份"
        class="erp-w-full"
      />
    </el-form-item>
    <el-form-item label="目标值" prop="target_value">
      <el-input-number v-model="modelValue.target_value" :min="0" :precision="2" class="erp-w-full" />
    </el-form-item>
    <el-form-item label="实际值" prop="achieved_value">
      <el-input-number v-model="modelValue.achieved_value" :min="0" :precision="2" class="erp-w-full" />
    </el-form-item>
    <el-form-item label="满分" prop="max_score">
      <el-input-number v-model="modelValue.max_score" :min="0" :precision="2" class="erp-w-full" />
    </el-form-item>
    <el-form-item label="启用罚分">
      <el-switch v-model="modelValue.penalty_enabled" />
    </el-form-item>
    <template v-if="modelValue.penalty_enabled">
      <el-form-item label="罚分阈值">
        <el-input-number v-model="modelValue.penalty_threshold" :precision="2" class="erp-w-full" />
      </el-form-item>
      <el-form-item label="每单位罚分">
        <el-input-number v-model="modelValue.penalty_per_unit" :precision="2" class="erp-w-full" />
      </el-form-item>
      <el-form-item label="最大罚分">
        <el-input-number v-model="modelValue.penalty_max" :precision="2" class="erp-w-full" />
      </el-form-item>
    </template>
    <el-form-item label="人工评分">
      <el-switch v-model="modelValue.manual_score_enabled" />
    </el-form-item>
    <el-form-item v-if="modelValue.manual_score_enabled" label="人工打分值">
      <el-input-number v-model="modelValue.manual_score_value" :min="0" :precision="2" class="erp-w-full" />
    </el-form-item>
    <el-form-item label="说明">
      <el-input v-model="modelValue.description" type="textarea" :rows="3" placeholder="补充说明该运营目标的业务语义" />
    </el-form-item>
  </el-form>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  metricOptions: { type: Array, default: () => [] },
  rules: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['metric-change'])
const formRef = ref(null)

const selectedMetric = computed(() => {
  return props.metricOptions.find((item) => item.code === props.modelValue.metric_code) || null
})

function handleMetricChange() {
  emit('metric-change')
}

defineExpose({ formRef, selectedMetric })
</script>
