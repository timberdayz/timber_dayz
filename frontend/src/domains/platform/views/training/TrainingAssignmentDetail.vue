<template>
  <div class="erp-page-container training-detail-page">
    <PageHeader
      title="培训详情"
      subtitle="查看培训要求、状态、结果、负责人和任务联动信息"
      family="admin"
    >
      <template #actions>
        <el-button plain @click="router.push('/my-training')">返回我的培训</el-button>
      </template>
    </PageHeader>

    <section class="detail-hero">
      <div>
        <p class="hero-label">{{ detail.program_name || '培训项目' }}</p>
        <h2>{{ detail.employee_name || '--' }}</h2>
        <p class="hero-subtitle">{{ detail.department || '--' }} / {{ detail.role_name || '--' }}</p>
      </div>
      <div class="hero-tags">
        <el-tag type="info">{{ detail.external_platform || '外部平台待配置' }}</el-tag>
        <el-tag :type="detail.current_status === '已通过' ? 'success' : detail.current_status === '已逾期' ? 'danger' : 'warning'">
          {{ detail.current_status || '待处理' }}
        </el-tag>
      </div>
    </section>

    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="hover" class="detail-card">
          <template #header>培训信息</template>
          <div class="detail-grid">
            <div class="detail-item"><span>培训分类</span><strong>{{ detail.category || '--' }}</strong></div>
            <div class="detail-item"><span>目标角色</span><strong>{{ detail.target_role || '--' }}</strong></div>
            <div class="detail-item"><span>学习状态</span><strong>{{ detail.learning_status || '--' }}</strong></div>
            <div class="detail-item"><span>截止日期</span><strong>{{ detail.due_date || '--' }}</strong></div>
            <div class="detail-item"><span>直属主管</span><strong>{{ detail.supervisor_name || '--' }}</strong></div>
            <div class="detail-item"><span>考试成绩</span><strong>{{ detail.exam_score ?? '--' }}</strong></div>
          </div>
        </el-card>

        <el-card shadow="hover" class="detail-card">
          <template #header>完成规则</template>
          <div class="detail-paragraph">{{ detail.completion_rule || '尚未配置完成规则' }}</div>
        </el-card>

        <el-card shadow="hover" class="detail-card">
          <template #header>备注</template>
          <div class="detail-paragraph">{{ detail.note || '暂无备注' }}</div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="hover" class="detail-card">
          <template #header>联动信息</template>
          <div class="side-item">
            <span>培训任务 ID</span>
            <strong>{{ detail.task_id || '未生成' }}</strong>
          </div>
          <div class="side-item">
            <span>当前状态</span>
            <strong>{{ detail.current_status || '--' }}</strong>
          </div>
          <div class="side-actions">
            <el-button
              v-if="detail.learning_url"
              type="primary"
              @click="openExternal(detail.learning_url)"
            >
              去学习
            </el-button>
            <el-button
              v-if="detail.exam_url"
              plain
              @click="openExternal(detail.exam_url)"
            >
              去考试
            </el-button>
            <el-button
              v-if="detail.materials_url"
              plain
              @click="openExternal(detail.materials_url)"
            >
              查看资料
            </el-button>
            <el-button type="primary" @click="router.push('/my-training')">查看我的培训</el-button>
            <el-button plain @click="router.push('/training/results')">查看培训结果</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import trainingApi from '@/api/training.js'

const route = useRoute()
const router = useRouter()
const detail = ref({})

const openExternal = (url) => {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

onMounted(async () => {
  detail.value = await trainingApi.getAssignmentDetail(route.params.assignmentId)
})
</script>

<style scoped>
.detail-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 24px;
  border-radius: 18px;
  background: linear-gradient(135deg, #1f4460, #2a7467);
  color: #fff;
}

.hero-label {
  margin: 0 0 8px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  opacity: 0.8;
}

.detail-hero h2 {
  margin: 0 0 8px;
  font-size: 30px;
}

.hero-subtitle {
  margin: 0;
  color: rgba(255, 255, 255, 0.82);
}

.hero-tags {
  display: flex;
  gap: 8px;
}

.detail-card + .detail-card {
  margin-top: 16px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-item,
.side-item {
  padding: 12px;
  border-radius: 12px;
  background: #f7f9fb;
}

.detail-item span,
.side-item span {
  display: block;
  font-size: 12px;
  color: #909399;
}

.detail-item strong,
.side-item strong {
  display: block;
  margin-top: 8px;
  color: #243241;
}

.detail-paragraph {
  line-height: 1.7;
  color: #4a5560;
}

.side-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
}
</style>
