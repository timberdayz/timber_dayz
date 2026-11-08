<template>
  <div class="semantic-coverage-panel">
    <div class="panel-toolbar">
      <el-select v-model="selectedDomain" style="width: 160px;" @change="loadCoverage">
        <el-option
          v-for="option in domainOptions"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
      </el-select>
      <el-input-number
        v-model="threshold"
        :min="0"
        :max="1"
        :step="0.05"
        :precision="2"
        controls-position="right"
        style="width: 150px;"
      />
      <span class="toolbar-hint">解析率告警阈值</span>
      <el-button type="primary" :loading="loading" @click="loadCoverage">
        <el-icon><Refresh /></el-icon>
        <span>刷新巡检</span>
      </el-button>
      <span v-if="generatedAt" class="toolbar-hint">巡检时间：{{ generatedAt }}</span>
    </div>

    <el-alert
      v-if="errorMessage"
      type="error"
      :title="errorMessage"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
    />

    <!-- 域级整体健康度 -->
    <el-row :gutter="16" style="margin-bottom: 16px;">
      <el-col v-for="report in reports" :key="report.domain" :xs="24" :sm="12" :md="8">
        <el-card shadow="hover" class="domain-card">
          <div class="domain-card-header">
            <span class="domain-name">{{ domainLabel(report.domain) }}</span>
            <el-tag :type="healthTagType(report.summary?.health)" size="small">
              {{ healthLabel(report.summary?.health) }}
            </el-tag>
          </div>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="平均解析率">
              {{ formatResolutionRate(report.summary?.average_resolution_rate) }}
            </el-descriptions-item>
            <el-descriptions-item label="平台数">
              {{ report.summary?.platform_count ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="解析率为 0">
              <el-text type="danger">{{ report.summary?.zero_rate_entry_count ?? 0 }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="低于阈值">
              <el-text type="warning">{{ report.summary?.below_threshold_entry_count ?? 0 }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="空壳行">
              {{ report.summary?.empty_shell_rows ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="告警数">
              {{ report.summary?.warning_count ?? 0 }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && !reports.length" description="暂无巡检数据" />

    <template v-for="report in reports" :key="`detail-${report.domain}`">
      <!-- 按平台的解析率 -->
      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="section-header">
            <span>{{ domainLabel(report.domain) }} · 按平台的解析率</span>
            <span class="section-hint">解析率最低的平台排最前</span>
          </div>
        </template>
        <el-table :data="platformRows(report)" border size="small" empty-text="无平台数据">
          <el-table-column prop="platform_code" label="平台" width="140" />
          <el-table-column label="平均解析率" width="140" align="right">
            <template #default="{ row }">
              <el-text :type="rateTextType(row.average_resolution_rate)">
                {{ formatResolutionRate(row.average_resolution_rate) }}
              </el-text>
            </template>
          </el-table-column>
          <el-table-column prop="field_count" label="字段数" width="100" align="right" />
          <el-table-column prop="zero_field_count" label="解析率为 0" width="120" align="right">
            <template #default="{ row }">
              <el-text :type="row.zero_field_count > 0 ? 'danger' : 'success'">
                {{ row.zero_field_count }}
              </el-text>
            </template>
          </el-table-column>
          <el-table-column label="全粒度都解析不出的字段" min-width="240">
            <template #default="{ row }">
              <span v-if="!row.always_zero_fields.length">-</span>
              <el-tag
                v-for="field in row.always_zero_fields"
                :key="field"
                type="danger"
                size="small"
                style="margin-right: 6px;"
              >
                {{ field }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 解析率为 0 的字段 + 源表真实列名候选 -->
      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="section-header">
            <span>{{ domainLabel(report.domain) }} · 解析率为 0 的字段</span>
            <span class="section-hint">候选列名 = 源表真实列名（尚未登记进字典）</span>
          </div>
        </template>
        <el-table :data="zeroRateRows(report)" border size="small" empty-text="没有解析率为 0 的字段">
          <el-table-column prop="platform_code" label="平台" width="120" />
          <el-table-column prop="granularity" label="粒度" width="100" />
          <el-table-column prop="standard_field" label="标准字段" width="180" />
          <el-table-column label="解析率" width="100" align="right">
            <template #default="{ row }">
              <el-text type="danger">{{ formatResolutionRate(row.resolution_rate) }}</el-text>
            </template>
          </el-table-column>
          <el-table-column label="源表真实列名候选" min-width="280">
            <template #default="{ row }">
              <span v-if="!row.column_candidates.length">-</span>
              <el-tag
                v-for="name in row.column_candidates"
                :key="name"
                type="warning"
                size="small"
                style="margin-right: 6px;"
              >
                {{ name }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- 告警列表 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span>告警列表</span>
          <span class="section-hint">解析率低于阈值的字段都会在这里被点名</span>
        </div>
      </template>
      <el-alert
        v-for="(warning, index) in warnings"
        :key="index"
        type="warning"
        :title="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 8px;"
      />
      <el-empty v-if="!warnings.length" description="没有告警" />
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { fetchSemanticCoverage } from '../utils/semanticCoverageApi.js'
import {
  SEMANTIC_COVERAGE_DOMAIN_OPTIONS,
  buildPlatformRows,
  buildZeroRateRows,
  formatResolutionRate,
  healthLabel,
  healthTagType
} from '../utils/semanticCoverage.js'

// ── 查询条件 ────────────────────────────────────────────────────────────
const selectedDomain = ref('all')
const threshold = ref(0.5)
const domainOptions = SEMANTIC_COVERAGE_DOMAIN_OPTIONS

// ── 巡检结果 ────────────────────────────────────────────────────────────
const loading = ref(false)
const reports = ref([])
const warnings = ref([])
const generatedAt = ref('')
const errorMessage = ref('')

/**
 * 拉取一次巡检结果。
 *
 * 失败时**只提示、不抛错**: 巡检面板是运维辅助视图, 拿不到数据不该让页面崩掉。
 */
const loadCoverage = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await fetchSemanticCoverage({
      domain: selectedDomain.value,
      threshold: threshold.value
    })
    if (!result.ok) {
      errorMessage.value = result.error || '巡检结果加载失败'
    }
    reports.value = result.data.reports || []
    warnings.value = result.data.warnings || []
    generatedAt.value = reports.value.length ? reports.value[0].generated_at || '' : ''
  } finally {
    loading.value = false
  }
}

/** 域名的中文展示。 */
const domainLabel = (domain) => {
  const found = domainOptions.find((option) => option.value === domain)
  return found ? found.label : domain || '-'
}

/** 解析率对应的文本颜色。 */
const rateTextType = (rate) => {
  const value = Number(rate)
  if (!Number.isFinite(value) || value <= 0) return 'danger'
  if (value < Number(threshold.value)) return 'warning'
  return 'success'
}

/** 平台维度汇总（按平台聚合 entries）。 */
const platformRows = (report) => buildPlatformRows(report)

/** 解析率为 0 的字段 + 真实列名候选。 */
const zeroRateRows = (report) => buildZeroRateRows(report)

// 首屏自动加载一次 —— 运维打开页面就能看到结论, 不用先点按钮。
loadCoverage()
</script>

<style scoped>
.semantic-coverage-panel {
  width: 100%;
}

.panel-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.toolbar-hint {
  color: #909399;
  font-size: 12px;
}

.domain-card {
  margin-bottom: 8px;
}

.domain-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.domain-name {
  font-size: 15px;
  font-weight: 600;
}

.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-hint {
  color: #909399;
  font-size: 12px;
}
</style>
