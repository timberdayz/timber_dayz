<template>
  <div class="ultra-simple-page">
    <div class="page-header">
      <h1>🎉 西虹ERP系统</h1>
      <p>智能跨境电商管理平台</p>
    </div>
    
    <div class="content">
      <div class="welcome-card">
        <h2>欢迎使用西虹ERP系统！</h2>
        <p>系统已成功启动，所有功能正常运行。</p>
        
        <div class="features">
          <div class="feature-item">
            <span class="feature-icon">📊</span>
            <span>业务概览</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">📈</span>
            <span>销售分析</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">📦</span>
            <span>库存管理</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">👥</span>
            <span>人力管理</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">💰</span>
            <span>财务管理</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">🏪</span>
            <span>店铺管理</span>
          </div>
        </div>
        
        <div class="actions">
          <button class="btn btn-primary" @click="testClick">
            🧪 测试功能
          </button>
          <button class="btn btn-secondary" @click="refreshData">
            🔄 刷新数据
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const clickCount = ref(0)

const testClick = () => {
  clickCount.value++
  alert(`测试按钮被点击了 ${clickCount.value} 次！`)
}

const refreshData = () => {
  alert('数据刷新成功！')
}
</script>

<style scoped>
.ultra-simple-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.page-header {
  text-align: center;
  color: white;
  margin-bottom: 40px;
}

.page-header h1 {
  font-size: 36px;
  margin: 0 0 10px 0;
  font-weight: 700;
}

.page-header p {
  font-size: 18px;
  margin: 0;
  opacity: 0.9;
}

.content {
  max-width: 800px;
  margin: 0 auto;
}

.welcome-card {
  background: white;
  border-radius: 20px;
  padding: 40px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.welcome-card h2 {
  color: #2c3e50;
  font-size: 28px;
  margin: 0 0 20px 0;
  font-weight: 600;
}

.welcome-card p {
  color: #7f8c8d;
  font-size: 16px;
  margin: 0 0 30px 0;
}

.features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin: 30px 0;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 10px;
  font-weight: 500;
  color: #2c3e50;
}

.feature-icon {
  font-size: 24px;
}

.actions {
  display: flex;
  gap: 15px;
  justify-content: center;
  margin-top: 30px;
}

.btn {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(102, 126, 234, 0.3);
}

.btn-secondary {
  background: #f8f9fa;
  color: #2c3e50;
  border: 2px solid #e9ecef;
}

.btn-secondary:hover {
  background: #e9ecef;
  transform: translateY(-2px);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .ultra-simple-page {
    padding: 10px;
  }
  
  .page-header h1 {
    font-size: 28px;
  }
  
  .welcome-card {
    padding: 20px;
  }
  
  .welcome-card h2 {
    font-size: 24px;
  }
  
  .features {
    grid-template-columns: 1fr;
  }
  
  .actions {
    flex-direction: column;
  }
}
</style>
