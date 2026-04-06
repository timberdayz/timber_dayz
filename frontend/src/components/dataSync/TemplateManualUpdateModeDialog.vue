<template>
  <el-dialog
    :model-value="visible"
    title="Manual Update"
    width="520px"
    @close="$emit('update:visible', false)"
  >
    <div class="template-manual-update-mode-dialog">
      <div class="template-manual-update-mode-dialog__meta">
        <div class="template-manual-update-mode-dialog__name">
          {{ template?.template_name || 'Unnamed Template' }}
        </div>
        <div class="template-manual-update-mode-dialog__detail">
          {{ template?.platform || '-' }} / {{ template?.data_domain || template?.domain || '-' }} /
          {{ template?.granularity || '-' }}
        </div>
      </div>

      <div class="template-manual-update-mode-dialog__options">
        <el-card shadow="never" class="template-manual-update-mode-dialog__card">
          <div class="template-manual-update-mode-dialog__title">Core Fields Only</div>
          <div class="template-manual-update-mode-dialog__desc">
            直接基于模板当前保存的字段池修改 deduplication_fields。
          </div>
          <el-button type="primary" @click="$emit('select', 'core-only')">
            Core Fields Only
          </el-button>
        </el-card>

        <el-card shadow="never" class="template-manual-update-mode-dialog__card">
          <div class="template-manual-update-mode-dialog__title">Reset From Sample File</div>
          <div class="template-manual-update-mode-dialog__desc">
            基于样本文件重新检查字段差异，并重新设定模板。
          </div>
          <el-button @click="$emit('select', 'with-sample')">
            Reset From Sample File
          </el-button>
        </el-card>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">Cancel</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  template: {
    type: Object,
    default: () => null,
  },
})

defineEmits(['update:visible', 'select'])
</script>

<style scoped>
.template-manual-update-mode-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.template-manual-update-mode-dialog__meta {
  padding: 12px;
  border-radius: 10px;
  background: #f5f7fa;
}

.template-manual-update-mode-dialog__name {
  font-weight: 600;
}

.template-manual-update-mode-dialog__detail {
  margin-top: 6px;
  color: #606266;
  font-size: 13px;
}

.template-manual-update-mode-dialog__options {
  display: grid;
  gap: 12px;
}

.template-manual-update-mode-dialog__card {
  border-radius: 12px;
}

.template-manual-update-mode-dialog__title {
  font-weight: 600;
  margin-bottom: 8px;
}

.template-manual-update-mode-dialog__desc {
  margin-bottom: 12px;
  color: #606266;
  font-size: 13px;
}
</style>
