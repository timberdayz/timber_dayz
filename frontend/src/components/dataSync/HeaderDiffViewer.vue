<template>
  <el-card class="header-diff-viewer" shadow="never">
    <template #header>
      <div class="header-diff-viewer__header">
        <span>字段差异</span>
        <el-tag size="small" type="info">
          {{ currentHeaderColumns.length }} 个当前字段
        </el-tag>
      </div>
    </template>

    <div class="header-diff-viewer__groups">
      <section class="header-diff-viewer__group">
        <div class="header-diff-viewer__group-title">新增字段</div>
        <div class="header-diff-viewer__tags">
          <el-tag v-for="field in addedFields" :key="field" size="small" type="success">{{ field }}</el-tag>
          <span v-if="addedFields.length === 0" class="header-diff-viewer__muted">无</span>
        </div>
      </section>

      <section class="header-diff-viewer__group">
        <div class="header-diff-viewer__group-title">删除字段</div>
        <div class="header-diff-viewer__tags">
          <el-tag v-for="field in removedFields" :key="field" size="small" type="danger">{{ field }}</el-tag>
          <span v-if="removedFields.length === 0" class="header-diff-viewer__muted">无</span>
        </div>
      </section>

      <section class="header-diff-viewer__group">
        <div class="header-diff-viewer__group-title">模板字段</div>
        <div class="header-diff-viewer__tags">
          <el-tag v-for="field in templateHeaderColumns" :key="field" size="small">{{ field }}</el-tag>
        </div>
      </section>
    </div>
  </el-card>
</template>

<script setup>
defineProps({
  templateHeaderColumns: {
    type: Array,
    default: () => []
  },
  currentHeaderColumns: {
    type: Array,
    default: () => []
  },
  addedFields: {
    type: Array,
    default: () => []
  },
  removedFields: {
    type: Array,
    default: () => []
  }
})
</script>

<style scoped>
.header-diff-viewer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.header-diff-viewer__groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.header-diff-viewer__group {
  padding: 12px;
  border-radius: 10px;
  background: #f7f8fa;
}

.header-diff-viewer__group-title {
  margin-bottom: 8px;
  font-size: 12px;
  color: #606266;
}

.header-diff-viewer__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.header-diff-viewer__muted {
  color: #909399;
  font-size: 12px;
}
</style>
