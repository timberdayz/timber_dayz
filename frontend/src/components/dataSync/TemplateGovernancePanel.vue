<template>
  <el-card class="governance-card" style="margin-bottom: 20px;">
    <template #header>
      <div class="governance-card__header">
        <span>📊 模板数据治理看板</span>
        <el-button size="small" :loading="loading" @click="$emit('refresh')">
          <el-icon><Refresh /></el-icon>
          刷新统计
        </el-button>
      </div>
    </template>

    <div class="governance-stats">
      <div class="stat-item">
        <div class="stat-icon" style="background: #409EFF;">
          <el-icon><Document /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">模板覆盖度</div>
          <div class="stat-value">{{ summary.coverage_percentage || 0 }}%</div>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-icon" style="background: #67C23A;">
          <el-icon><Check /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">已覆盖</div>
          <div class="stat-value">{{ summary.covered_count || 0 }}</div>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-icon" style="background: #F56C6C;">
          <el-icon><Warning /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">缺少模板</div>
          <div class="stat-value">{{ summary.missing_count || 0 }}</div>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-icon" style="background: #E6A23C;">
          <el-icon><Refresh /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">需要更新</div>
          <div class="stat-value">{{ summary.needs_update_count || 0 }}</div>
        </div>
      </div>
    </div>

    <el-tabs :model-value="activeTab" style="margin-top: 20px;" @update:model-value="$emit('update:active-tab', $event)">
      <el-tab-pane label="已覆盖模板" name="covered">
        <el-table :data="detailedCoverage.covered || []" stripe border max-height="400">
          <el-table-column prop="platform" label="平台" width="100">
            <template #default="{ row }">
              {{ getPlatformLabel(row.platform) }}
            </template>
          </el-table-column>
          <el-table-column prop="domain" label="数据域" width="100" />
          <el-table-column prop="sub_domain" label="子类型" width="120" />
          <el-table-column prop="granularity" label="粒度" width="100" />
          <el-table-column prop="template_name" label="模板名称" min-width="200" />
          <el-table-column prop="template_version" label="版本" width="80" />
          <el-table-column prop="file_count" label="文件数" width="100" align="center" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.needs_update" type="warning" size="small">
                <el-icon><Refresh /></el-icon>
                需要更新
              </el-tag>
              <el-tag v-else type="success" size="small">
                <el-icon><Check /></el-icon>
                正常
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="update_reason" label="更新原因" min-width="200" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="缺少模板" name="missing">
        <el-table :data="detailedCoverage.missing || []" stripe border max-height="400">
          <el-table-column prop="platform" label="平台" width="100">
            <template #default="{ row }">
              {{ getPlatformLabel(row.platform) }}
            </template>
          </el-table-column>
          <el-table-column prop="domain" label="数据域" width="100" />
          <el-table-column prop="sub_domain" label="子类型" width="120" />
          <el-table-column prop="granularity" label="粒度" width="100" />
          <el-table-column prop="file_count" label="待同步文件数" width="120" align="center" />
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="$emit('create-missing', row)">
                <el-icon><Plus /></el-icon>
                创建模板
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="需要更新" name="needs_update">
        <TemplateNeedsUpdateTable
          :rows="detailedCoverage.needs_update || []"
          :get-platform-label="getPlatformLabel"
          @update-template="$emit('update-template', $event)"
        />
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { Check, Document, Plus, Refresh, Warning } from '@element-plus/icons-vue'

import TemplateNeedsUpdateTable from './TemplateNeedsUpdateTable.vue'

const props = defineProps({
  detailedCoverage: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  activeTab: {
    type: String,
    default: 'covered',
  },
  getPlatformLabel: {
    type: Function,
    default: value => value ?? '',
  },
})

defineEmits(['refresh', 'create-missing', 'update-template', 'update:active-tab'])

const summary = computed(() => props.detailedCoverage?.summary ?? {})
</script>

<style scoped>
.governance-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.governance-stats {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 15px;
  background: #f5f7fa;
  border-radius: 8px;
  flex: 1;
  min-width: 200px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 24px;
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 14px;
  color: #666;
  margin-bottom: 5px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}
</style>
