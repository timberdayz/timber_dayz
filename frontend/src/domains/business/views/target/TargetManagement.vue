<template>
  <div class="target-management-legacy erp-page-container erp-page--admin">
    <PageHeader
      title="目标管理（历史入口）"
      subtitle="原混合式目标大表单已下线，现已拆分为店铺目标、个人目标和运营目标三个独立入口。"
      family="admin"
    />

    <el-alert
      title="请不要继续使用旧的混合目标管理方式。新链路已按业务边界拆分。"
      type="warning"
      :closable="false"
      style="margin-bottom: 16px;"
    />

    <div class="entry-grid">
      <el-card shadow="never" class="entry-card">
        <template #header>店铺目标</template>
        <p class="entry-text">用于店铺销售、利润等规划层目标维护。</p>
        <el-button type="primary" @click="go('/target-management/shop')">进入店铺目标管理</el-button>
      </el-card>

      <el-card shadow="never" class="entry-card">
        <template #header>个人目标</template>
        <p class="entry-text">用于员工个人规划层目标维护，不直接参与个人绩效结果计算。</p>
        <el-button type="primary" @click="go('/target-management/person')">进入个人目标管理</el-button>
      </el-card>

      <el-card shadow="never" class="entry-card">
        <template #header>运营目标</template>
        <p class="entry-text">当前仅代表店铺运营目标，服务店铺绩效 `operation_score`。</p>
        <el-button type="primary" @click="go('/target-management/operation')">进入运营目标管理</el-button>
      </el-card>

      <el-card shadow="never" class="entry-card">
        <template #header>人员绩效输入项</template>
        <p class="entry-text">个人运营、考试、培训等真正参与个人绩效计算的内容，请到人员绩效页维护。</p>
        <el-button @click="go('/hr-performance-management/person')">进入个人绩效管理</el-button>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'

const router = useRouter()

function go(path) {
  router.push(path)
}
</script>

<style scoped>
.target-management-legacy {
  min-height: calc(100vh - var(--header-height));
}

.entry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}

.entry-card {
  min-height: 180px;
}

.entry-text {
  min-height: 52px;
  margin: 0 0 16px;
  color: #606266;
  line-height: 1.6;
}
</style>
