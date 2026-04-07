<template>
  <div class="under-development">
    <div class="dev-banner">
      <div class="banner-icon">
        <el-icon :size="80">
          <component :is="icon" />
        </el-icon>
      </div>
      <h1 class="banner-title">{{ title }}</h1>
      <p class="banner-subtitle">{{ subtitle }}</p>
      <el-tag type="warning" size="large" class="dev-tag">
        功能开发中
      </el-tag>
    </div>
    
    <div class="dev-info">
      <el-card class="info-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon><InfoFilled /></el-icon>
            <span>模块说明</span>
          </div>
        </template>
        <div class="module-description">
          <p>{{ description }}</p>
          <el-divider />
          <div class="features">
            <h4>计划功能：</h4>
            <ul>
              <li v-for="(feature, index) in features" :key="index">
                {{ feature }}
              </li>
            </ul>
          </div>
          <el-divider />
          <div class="roadmap">
            <el-alert
              title="开发计划"
              type="info"
              :closable="false"
              show-icon
            >
              <template #default>
                <p><strong>预计完成时间：</strong>{{ timeline }}</p>
                <p><strong>当前进度：</strong>{{ progress }}</p>
              </template>
            </el-alert>
          </div>
        </div>
      </el-card>
      
      <el-card class="placeholder-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon><Picture /></el-icon>
            <span>界面预览</span>
          </div>
        </template>
        <div class="placeholder-content">
          <el-empty :image-size="200" description="界面设计中...">
            <template #image>
              <el-icon :size="200" color="#909399">
                <component :is="icon" />
              </el-icon>
            </template>
          </el-empty>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { InfoFilled, Picture } from '@element-plus/icons-vue'

// 定义props
const props = defineProps({
  title: {
    type: String,
    default: '功能模块'
  },
  subtitle: {
    type: String,
    default: '正在努力开发中，敬请期待'
  },
  icon: {
    type: Object,
    default: null
  },
  description: {
    type: String,
    default: '该模块正在开发中，我们正在努力为您打造最佳的用户体验。'
  },
  features: {
    type: Array,
    default: () => []
  },
  timeline: {
    type: String,
    default: '待定'
  },
  progress: {
    type: String,
    default: '设计阶段'
  }
})
</script>

<style scoped>
.under-development {
  padding: 20px;
}

.dev-banner {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  padding: 60px 40px;
  text-align: center;
  color: white;
  margin-bottom: 30px;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.banner-icon {
  margin-bottom: 20px;
  opacity: 0.9;
}

.banner-title {
  font-size: 36px;
  font-weight: 600;
  margin: 0 0 10px;
}

.banner-subtitle {
  font-size: 18px;
  margin: 0 0 20px;
  opacity: 0.9;
}

.dev-tag {
  font-size: 14px;
  padding: 8px 16px;
}

.dev-info {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.info-card,
.placeholder-card {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.module-description {
  font-size: 14px;
  line-height: 1.8;
}

.features h4 {
  margin-bottom: 10px;
  color: #303133;
}

.features ul {
  padding-left: 20px;
}

.features li {
  margin-bottom: 8px;
  color: #606266;
}

.roadmap {
  margin-top: 10px;
}

.placeholder-content {
  min-height: 300px;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 768px) {
  .dev-info {
    grid-template-columns: 1fr;
  }
}
</style>

