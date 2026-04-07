<template>
  <div class="data-consistency">
    <el-page-header>
      <template #content>
        <div class="page-header-content">
          <h2>数据一致性验证</h2>
          <p class="page-subtitle">验证跨平台数据一致性、计算数据准确性、检测异常数据</p>
        </div>
      </template>
    </el-page-header>

    <!-- 功能选择卡片 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="function-card" @click="activeTab = 'cross-platform'">
          <div class="card-content">
            <el-icon :size="40" color="#409eff"><Connection /></el-icon>
            <h3>跨平台一致性检查</h3>
            <p>检查同一店铺在不同平台的数据一致性</p>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="function-card" @click="activeTab = 'calculated-vs-source'">
          <div class="card-content">
            <el-icon :size="40" color="#67c23a"><DocumentChecked /></el-icon>
            <h3>计算数据验证</h3>
            <p>验证C类计算数据与B类源数据的一致性</p>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="function-card" @click="activeTab = 'anomaly-detection'">
          <div class="card-content">
            <el-icon :size="40" color="#e6a23c"><Warning /></el-icon>
            <h3>异常数据检测</h3>
            <p>使用统计方法检测异常数据点</p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 标签页内容 -->
    <el-tabs v-model="activeTab" style="margin-top: 24px;">
      <!-- 跨平台一致性检查 -->
      <el-tab-pane label="跨平台一致性检查" name="cross-platform">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>跨平台一致性检查</span>
              <el-button type="primary" @click="checkCrossPlatform" :loading="loadingCrossPlatform">
                <el-icon><Search /></el-icon>
                开始检查
              </el-button>
            </div>
          </template>

          <el-form :model="crossPlatformForm" label-width="120px" style="margin-bottom: 20px;">
            <el-row :gutter="20">
              <el-col :span="8">
                <el-form-item label="店铺ID">
                  <el-input v-model="crossPlatformForm.shop_id" placeholder="请输入店铺ID" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="平台列表">
                  <el-select v-model="crossPlatformForm.platforms" multiple placeholder="选择平台" style="width: 100%;">
                    <el-option label="Shopee" value="shopee" />
                    <el-option label="TikTok" value="tiktok" />
                    <el-option label="Amazon" value="amazon" />
                    <el-option label="妙手ERP" value="miaoshou" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="日期范围">
                  <el-date-picker
                    v-model="crossPlatformForm.dateRange"
                    type="daterange"
                    range-separator="至"
                    start-placeholder="开始日期"
                    end-placeholder="结束日期"
                    style="width: 100%;"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>

          <el-divider />

          <div v-if="crossPlatformResult" style="margin-top: 20px;">
            <el-descriptions title="检查结果" :column="2" border>
              <el-descriptions-item label="一致性评分">
                <el-tag :type="crossPlatformResult.summary.consistency_score >= 90 ? 'success' : crossPlatformResult.summary.consistency_score >= 70 ? 'warning' : 'danger'">
                  {{ crossPlatformResult.summary.consistency_score }}%
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="检查的平台数">
                {{ crossPlatformResult.summary.platform_count }}
              </el-descriptions-item>
              <el-descriptions-item label="不一致指标数">
                <el-text type="danger">{{ crossPlatformResult.summary.inconsistent_metrics }}</el-text>
              </el-descriptions-item>
              <el-descriptions-item label="检查日期范围">
                {{ crossPlatformResult.summary.date_range }}
              </el-descriptions-item>
            </el-descriptions>

            <el-table :data="crossPlatformResult.details" style="margin-top: 20px;" border>
              <el-table-column prop="platform" label="平台" width="120" />
              <el-table-column prop="metric" label="指标" width="150" />
              <el-table-column prop="value" label="数值" width="120" align="right" />
              <el-table-column prop="deviation" label="偏差" width="120" align="right">
                <template #default="{ row }">
                  <el-text :type="Math.abs(row.deviation) > 10 ? 'danger' : Math.abs(row.deviation) > 5 ? 'warning' : 'success'">
                    {{ row.deviation > 0 ? '+' : '' }}{{ row.deviation.toFixed(2) }}%
                  </el-text>
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'consistent' ? 'success' : 'danger'">
                    {{ row.status === 'consistent' ? '一致' : '不一致' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <el-empty v-if="!loadingCrossPlatform && !crossPlatformResult" description="请填写参数后点击开始检查" />
        </el-card>
      </el-tab-pane>

      <!-- 计算数据验证 -->
      <el-tab-pane label="计算数据验证" name="calculated-vs-source">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>计算数据验证</span>
              <el-button type="primary" @click="checkCalculatedVsSource" :loading="loadingCalculatedVsSource">
                <el-icon><Search /></el-icon>
                开始验证
              </el-button>
            </div>
          </template>

          <el-form :model="calculatedVsSourceForm" label-width="120px" style="margin-bottom: 20px;">
            <el-row :gutter="20">
              <el-col :span="8">
                <el-form-item label="平台代码">
                  <el-select v-model="calculatedVsSourceForm.platform_code" placeholder="选择平台" style="width: 100%;">
                    <el-option label="Shopee" value="shopee" />
                    <el-option label="TikTok" value="tiktok" />
                    <el-option label="Amazon" value="amazon" />
                    <el-option label="妙手ERP" value="miaoshou" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="店铺ID">
                  <el-input v-model="calculatedVsSourceForm.shop_id" placeholder="请输入店铺ID" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="指标日期">
                  <el-date-picker
                    v-model="calculatedVsSourceForm.metric_date"
                    type="date"
                    placeholder="选择日期"
                    style="width: 100%;"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>

          <el-divider />

          <div v-if="calculatedVsSourceResult" style="margin-top: 20px;">
            <el-descriptions title="验证结果" :column="2" border>
              <el-descriptions-item label="验证状态">
                <el-tag :type="calculatedVsSourceResult.summary.is_consistent ? 'success' : 'danger'">
                  {{ calculatedVsSourceResult.summary.is_consistent ? '一致' : '不一致' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="验证指标数">
                {{ calculatedVsSourceResult.summary.metric_count }}
              </el-descriptions-item>
              <el-descriptions-item label="一致指标数">
                <el-text type="success">{{ calculatedVsSourceResult.summary.consistent_count }}</el-text>
              </el-descriptions-item>
              <el-descriptions-item label="不一致指标数">
                <el-text type="danger">{{ calculatedVsSourceResult.summary.inconsistent_count }}</el-text>
              </el-descriptions-item>
            </el-descriptions>

            <el-table :data="calculatedVsSourceResult.details" style="margin-top: 20px;" border>
              <el-table-column prop="metric" label="指标" width="200" />
              <el-table-column prop="calculated_value" label="计算值(C类)" width="150" align="right" />
              <el-table-column prop="source_value" label="源值(B类)" width="150" align="right" />
              <el-table-column prop="difference" label="差异" width="120" align="right">
                <template #default="{ row }">
                  <el-text :type="Math.abs(row.difference) > 0.01 ? 'danger' : 'success'">
                    {{ row.difference > 0 ? '+' : '' }}{{ row.difference.toFixed(4) }}
                  </el-text>
                </template>
              </el-table-column>
              <el-table-column prop="difference_percent" label="差异百分比" width="120" align="right">
                <template #default="{ row }">
                  <el-text :type="Math.abs(row.difference_percent) > 1 ? 'danger' : 'success'">
                    {{ row.difference_percent > 0 ? '+' : '' }}{{ row.difference_percent.toFixed(2) }}%
                  </el-text>
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'consistent' ? 'success' : 'danger'">
                    {{ row.status === 'consistent' ? '一致' : '不一致' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <el-empty v-if="!loadingCalculatedVsSource && !calculatedVsSourceResult" description="请填写参数后点击开始验证" />
        </el-card>
      </el-tab-pane>

      <!-- 异常数据检测 -->
      <el-tab-pane label="异常数据检测" name="anomaly-detection">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>异常数据检测</span>
              <el-button type="primary" @click="detectAnomalies" :loading="loadingAnomalyDetection">
                <el-icon><Search /></el-icon>
                开始检测
              </el-button>
            </div>
          </template>

          <el-form :model="anomalyDetectionForm" label-width="120px" style="margin-bottom: 20px;">
            <el-row :gutter="20">
              <el-col :span="8">
                <el-form-item label="平台代码">
                  <el-select v-model="anomalyDetectionForm.platform_code" placeholder="选择平台" style="width: 100%;">
                    <el-option label="Shopee" value="shopee" />
                    <el-option label="TikTok" value="tiktok" />
                    <el-option label="Amazon" value="amazon" />
                    <el-option label="妙手ERP" value="miaoshou" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="店铺ID">
                  <el-input v-model="anomalyDetectionForm.shop_id" placeholder="请输入店铺ID" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="日期范围">
                  <el-date-picker
                    v-model="anomalyDetectionForm.dateRange"
                    type="daterange"
                    range-separator="至"
                    start-placeholder="开始日期"
                    end-placeholder="结束日期"
                    style="width: 100%;"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="8">
                <el-form-item label="检测指标">
                  <el-select v-model="anomalyDetectionForm.metric" placeholder="选择指标" style="width: 100%;">
                    <el-option label="GMV" value="gmv" />
                    <el-option label="订单数" value="orders" />
                    <el-option label="客单价" value="aov" />
                    <el-option label="转化率" value="conversion_rate" />
                    <el-option label="连带率" value="attach_rate" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="阈值(Z-score)">
                  <el-input-number v-model="anomalyDetectionForm.threshold" :min="1" :max="5" :step="0.5" style="width: 100%;" />
                  <div style="font-size: 12px; color: #909399; margin-top: 4px;">默认3.0，值越大检测越严格</div>
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>

          <el-divider />

          <div v-if="anomalyDetectionResult" style="margin-top: 20px;">
            <el-descriptions title="检测结果" :column="2" border>
              <el-descriptions-item label="异常点数量">
                <el-text type="danger" style="font-size: 18px; font-weight: bold;">
                  {{ anomalyDetectionResult.summary.anomaly_count }}
                </el-text>
              </el-descriptions-item>
              <el-descriptions-item label="总数据点数">
                {{ anomalyDetectionResult.summary.total_points }}
              </el-descriptions-item>
              <el-descriptions-item label="异常率">
                <el-text :type="anomalyDetectionResult.summary.anomaly_rate > 0.1 ? 'danger' : 'success'">
                  {{ (anomalyDetectionResult.summary.anomaly_rate * 100).toFixed(2) }}%
                </el-text>
              </el-descriptions-item>
              <el-descriptions-item label="使用的阈值">
                {{ anomalyDetectionResult.summary.threshold }}
              </el-descriptions-item>
            </el-descriptions>

            <el-table :data="anomalyDetectionResult.anomalies" style="margin-top: 20px;" border>
              <el-table-column prop="date" label="日期" width="120" />
              <el-table-column prop="value" label="数值" width="150" align="right" />
              <el-table-column prop="z_score" label="Z-score" width="120" align="right">
                <template #default="{ row }">
                  <el-text :type="Math.abs(row.z_score) > 3 ? 'danger' : 'warning'">
                    {{ row.z_score.toFixed(2) }}
                  </el-text>
                </template>
              </el-table-column>
              <el-table-column prop="mean" label="平均值" width="120" align="right" />
              <el-table-column prop="std_dev" label="标准差" width="120" align="right" />
              <el-table-column prop="severity" label="严重程度" width="120">
                <template #default="{ row }">
                  <el-tag :type="row.severity === 'high' ? 'danger' : row.severity === 'medium' ? 'warning' : 'info'">
                    {{ row.severity === 'high' ? '高' : row.severity === 'medium' ? '中' : '低' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <el-empty v-if="!loadingAnomalyDetection && !anomalyDetectionResult" description="请填写参数后点击开始检测" />
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, DocumentChecked, Warning, Search } from '@element-plus/icons-vue'
import api from '../api'

// 标签页
const activeTab = ref('cross-platform')

// 跨平台一致性检查
const loadingCrossPlatform = ref(false)
const crossPlatformForm = ref({
  shop_id: '',
  platforms: [],
  dateRange: []
})
const crossPlatformResult = ref(null)

const checkCrossPlatform = async () => {
  if (!crossPlatformForm.value.shop_id) {
    ElMessage.warning('请输入店铺ID')
    return
  }
  if (!crossPlatformForm.value.platforms || crossPlatformForm.value.platforms.length === 0) {
    ElMessage.warning('请选择至少一个平台')
    return
  }
  if (!crossPlatformForm.value.dateRange || crossPlatformForm.value.dateRange.length !== 2) {
    ElMessage.warning('请选择日期范围')
    return
  }

  loadingCrossPlatform.value = true
  try {
    const [startDate, endDate] = crossPlatformForm.value.dateRange
    const response = await api.checkCrossPlatformConsistency(
      crossPlatformForm.value.shop_id,
      crossPlatformForm.value.platforms,
      startDate.toISOString().split('T')[0],
      endDate.toISOString().split('T')[0]
    )
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      crossPlatformResult.value = response
      ElMessage.success('检查完成')
    } else {
      ElMessage.error(response.error || '检查失败')
    }
  } catch (error) {
    console.error('跨平台一致性检查失败:', error)
    ElMessage.error('检查失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loadingCrossPlatform.value = false
  }
}

// 计算数据验证
const loadingCalculatedVsSource = ref(false)
const calculatedVsSourceForm = ref({
  platform_code: '',
  shop_id: '',
  metric_date: null
})
const calculatedVsSourceResult = ref(null)

const checkCalculatedVsSource = async () => {
  if (!calculatedVsSourceForm.value.platform_code) {
    ElMessage.warning('请选择平台')
    return
  }
  if (!calculatedVsSourceForm.value.shop_id) {
    ElMessage.warning('请输入店铺ID')
    return
  }
  if (!calculatedVsSourceForm.value.metric_date) {
    ElMessage.warning('请选择指标日期')
    return
  }

  loadingCalculatedVsSource.value = true
  try {
    const response = await api.checkCalculatedVsSourceConsistency(
      calculatedVsSourceForm.value.platform_code,
      calculatedVsSourceForm.value.shop_id,
      calculatedVsSourceForm.value.metric_date.toISOString().split('T')[0]
    )
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      calculatedVsSourceResult.value = response
      ElMessage.success('验证完成')
    } else {
      ElMessage.error(response.error || '验证失败')
    }
  } catch (error) {
    console.error('计算数据验证失败:', error)
    ElMessage.error('验证失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loadingCalculatedVsSource.value = false
  }
}

// 异常数据检测
const loadingAnomalyDetection = ref(false)
const anomalyDetectionForm = ref({
  platform_code: '',
  shop_id: '',
  dateRange: [],
  metric: 'gmv',
  threshold: 3.0
})
const anomalyDetectionResult = ref(null)

const detectAnomalies = async () => {
  if (!anomalyDetectionForm.value.platform_code) {
    ElMessage.warning('请选择平台')
    return
  }
  if (!anomalyDetectionForm.value.shop_id) {
    ElMessage.warning('请输入店铺ID')
    return
  }
  if (!anomalyDetectionForm.value.dateRange || anomalyDetectionForm.value.dateRange.length !== 2) {
    ElMessage.warning('请选择日期范围')
    return
  }

  loadingAnomalyDetection.value = true
  try {
    const [startDate, endDate] = anomalyDetectionForm.value.dateRange
    const response = await api.detectDataAnomalies(
      anomalyDetectionForm.value.platform_code,
      anomalyDetectionForm.value.shop_id,
      startDate.toISOString().split('T')[0],
      endDate.toISOString().split('T')[0],
      anomalyDetectionForm.value.metric,
      anomalyDetectionForm.value.threshold
    )
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      anomalyDetectionResult.value = response
      ElMessage.success('检测完成')
    } else {
      ElMessage.error(response.error || '检测失败')
    }
  } catch (error) {
    console.error('异常数据检测失败:', error)
    ElMessage.error('检测失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loadingAnomalyDetection.value = false
  }
}
</script>

<style scoped>
.data-consistency {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.page-header-content h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.page-subtitle {
  margin: 8px 0 0 0;
  color: #909399;
  font-size: 14px;
}

.function-card {
  cursor: pointer;
  transition: all 0.3s;
  height: 180px;
}

.function-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
}

.card-content {
  text-align: center;
  padding: 20px;
}

.card-content h3 {
  margin: 16px 0 8px 0;
  font-size: 18px;
  font-weight: 600;
}

.card-content p {
  margin: 0;
  color: #909399;
  font-size: 14px;
}
</style>

