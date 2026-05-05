<template>
  <div class="inventory-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>📦 库存看板</h1>
      <p class="subtitle">实时监控库存状态，预警低库存商品</p>
    </div>

    <!-- 库存概况卡片 -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总库存" :value="stats.totalStock">
            <template #suffix>件</template>
          </el-statistic>
          <div class="stat-trend positive">较上月 +5.2%</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card warning">
          <el-statistic 
            title="低库存预警" 
            :value="stats.lowStockCount"
            :value-style="{ color: '#e6a23c' }"
          >
            <template #suffix>个SKU</template>
          </el-statistic>
          <div class="stat-trend negative">需要补货</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card danger">
          <el-statistic 
            title="缺货商品" 
            :value="stats.outOfStock"
            :value-style="{ color: '#f56c6c' }"
          >
            <template #suffix>个SKU</template>
          </el-statistic>
          <div class="stat-trend negative">紧急补货</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic 
            title="库存价值" 
            :value="stats.totalValue"
            :precision="2"
          >
            <template #prefix>¥</template>
          </el-statistic>
          <div class="stat-trend positive">较上月 +8.7%</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 库存健康度 -->
    <el-card class="feature-card">
      <template #header>
        <span>🎯 库存健康度评分</span>
      </template>
      <el-row :gutter="20">
        <el-col :span="8">
          <div class="health-score">
            <el-progress 
              type="dashboard" 
              :percentage="healthScore" 
              :color="healthColor"
              :width="160"
            >
              <template #default="{ percentage }">
                <span class="percentage-value">{{ percentage }}</span>
                <span class="percentage-label">分</span>
              </template>
            </el-progress>
            <div class="health-status">{{ healthStatus }}</div>
          </div>
        </el-col>
        <el-col :span="16">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="库存周转率">
              <el-tag type="success">良好</el-tag> 15.2次/年
            </el-descriptions-item>
            <el-descriptions-item label="平均库龄">
              <el-tag type="success">健康</el-tag> 23.5天
            </el-descriptions-item>
            <el-descriptions-item label="呆滞库存">
              <el-tag type="warning">需关注</el-tag> ¥45,230
            </el-descriptions-item>
            <el-descriptions-item label="库存准确率">
              <el-tag type="success">优秀</el-tag> 98.7%
            </el-descriptions-item>
          </el-descriptions>
        </el-col>
      </el-row>
    </el-card>

    <!-- 平台库存分布 -->
    <el-card class="feature-card" style="margin-top: 20px;">
      <template #header>
        <span>📊 平台库存分布</span>
      </template>
      <el-table :data="platformStats" stripe>
        <el-table-column prop="platform" label="平台" width="120">
          <template #default="{ row }">
            <el-tag>{{ row.platform }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="skuCount" label="SKU数量" width="120" />
        <el-table-column prop="totalStock" label="总库存" width="120" />
        <el-table-column prop="lowStock" label="低库存" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.lowStock > 0" type="warning">{{ row.lowStock }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="value" label="库存价值">
          <template #default="{ row }">
            ¥{{ row.value.toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="占比" width="200">
          <template #default="{ row }">
            <el-progress 
              :percentage="row.percentage" 
              :color="getProgressColor(row.percentage)"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 功能说明 -->
    <el-card class="feature-card" style="margin-top: 20px;">
      <template #header>
        <span>📋 功能计划</span>
      </template>
      <el-timeline>
        <el-timeline-item timestamp="当前版本" type="success">
          ✅ 简化版本 - 提供库存概况和健康度评分
        </el-timeline-item>
        <el-timeline-item timestamp="v2.0计划" type="primary">
          🔨 增强版本 - 添加实时数据刷新、图表展示、预警提醒
        </el-timeline-item>
        <el-timeline-item timestamp="v3.0计划" type="info">
          🚀 完整版本 - 库存预测、智能补货建议、多仓库管理
        </el-timeline-item>
      </el-timeline>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, computed } from 'vue'

// 统计数据
const stats = reactive({
  totalStock: 125480,
  lowStockCount: 15,
  outOfStock: 3,
  totalValue: 2856790
})

// 库存健康度评分
const healthScore = computed(() => {
  // 基于低库存和缺货比例计算
  const lowStockPenalty = stats.lowStockCount * 2
  const outOfStockPenalty = stats.outOfStock * 10
  return Math.max(0, 100 - lowStockPenalty - outOfStockPenalty)
})

const healthColor = computed(() => {
  const score = healthScore.value
  if (score >= 90) return '#67c23a'
  if (score >= 70) return '#e6a23c'
  return '#f56c6c'
})

const healthStatus = computed(() => {
  const score = healthScore.value
  if (score >= 90) return '健康'
  if (score >= 70) return '一般'
  return '需关注'
})

// 平台库存分布
const platformStats = reactive([
  { platform: 'Shopee', skuCount: 1250, totalStock: 45680, lowStock: 8, value: 986543, percentage: 36 },
  { platform: 'Lazada', skuCount: 980, totalStock: 32450, lowStock: 4, value: 654321, percentage: 26 },
  { platform: 'TikTok', skuCount: 756, totalStock: 28940, lowStock: 2, value: 598765, percentage: 23 },
  { platform: 'Amazon', skuCount: 423, totalStock: 18410, lowStock: 1, value: 617161, percentage: 15 }
])

// 进度条颜色
const getProgressColor = (percentage) => {
  if (percentage >= 30) return '#409eff'
  if (percentage >= 20) return '#67c23a'
  return '#e6a23c'
}
</script>

<style scoped>
.inventory-page {
  padding: 24px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 28px;
  color: #303133;
  margin: 0 0 8px 0;
}

.subtitle {
  color: #909399;
  font-size: 14px;
  margin: 0;
}

.stat-card {
  text-align: center;
  border-left: 4px solid #409eff;
}

.stat-card.warning {
  border-left-color: #e6a23c;
}

.stat-card.danger {
  border-left-color: #f56c6c;
}

.stat-trend {
  margin-top: 8px;
  font-size: 12px;
}

.stat-trend.positive {
  color: #67c23a;
}

.stat-trend.negative {
  color: #f56c6c;
}

.feature-card {
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.feature-card :deep(.el-card__header) {
  font-weight: 600;
  font-size: 16px;
}

.health-score {
  text-align: center;
  padding: 20px 0;
}

.percentage-value {
  font-size: 32px;
  font-weight: bold;
}

.percentage-label {
  font-size: 14px;
  color: #909399;
  margin-left: 4px;
}

.health-status {
  margin-top: 12px;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
</style>
