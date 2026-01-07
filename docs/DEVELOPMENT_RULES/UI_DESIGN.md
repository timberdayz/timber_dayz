# UI设计规范

**版本**: v4.19.0  
**更新**: 2026-01-03  
**适用范围**: Vue.js 3 + Element Plus前端开发

---

## 核心原则

### 设计目标
- ✅ **专业化**: 符合企业级ERP系统的视觉标准
- ✅ **一致性**: 统一的设计语言和交互模式
- ✅ **易用性**: 符合用户认知习惯，减少学习成本
- ✅ **响应式**: 适配不同屏幕尺寸和设备

### 技术栈
- **核心框架**: Vue.js 3 + Composition API
- **UI组件库**: Element Plus（企业级组件库）
- **布局方案**: 原生CSS（Flexbox + Grid）
- **图表库**: ECharts + Chart.js
- **状态管理**: Pinia
- **构建工具**: Vite

---

## 布局开发规范

### 布局策略
- ✅ **原生CSS优先**: 使用Flexbox和CSS Grid实现布局
- ✅ **组件化**: Element Plus仅用于表单、表格、弹窗等交互组件
- ❌ **避免过度依赖**: 不使用复杂的Element Plus容器组件（如el-container）

### 响应式布局
```css
/* 优先使用CSS Grid实现响应式布局 */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

/* 使用媒体查询适配不同屏幕 */
@media (max-width: 768px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}
```

### 布局示例
```vue
<template>
  <!-- 使用原生CSS布局 -->
  <div class="page-container">
    <div class="page-header">
      <h1>数据看板</h1>
    </div>
    
    <div class="content-grid">
      <!-- Element Plus仅用于数据展示组件 -->
      <el-card class="stats-card">
        <template #header>销售统计</template>
        <div class="stats-content">...</div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px;
}

.content-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
}
</style>
```

---

## 视觉设计规范

### 配色方案
```css
/* 主色调（参考Element Plus默认主题） */
--primary-color: #409EFF;      /* 主要按钮、链接 */
--success-color: #67C23A;      /* 成功状态 */
--warning-color: #E6A23C;      /* 警告状态 */
--danger-color: #F56C6C;       /* 危险操作 */
--info-color: #909399;         /* 信息提示 */

/* 中性色 */
--text-primary: #303133;       /* 主要文字 */
--text-regular: #606266;       /* 常规文字 */
--text-secondary: #909399;     /* 次要文字 */
--text-placeholder: #C0C4CC;   /* 占位文字 */

/* 边框和背景 */
--border-color: #DCDFE6;       /* 边框颜色 */
--bg-color: #F2F6FC;           /* 背景色 */
--bg-white: #FFFFFF;           /* 白色背景 */
```

### 专业级视觉效果
```css
/* 渐变色标题 */
.gradient-title {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  font-size: 28px;
  font-weight: bold;
}

/* 卡片阴影 */
.card-shadow {
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  transition: box-shadow 0.3s;
}

.card-shadow:hover {
  box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.15);
}
```

### 字体规范
```css
/* 标题字体 */
h1 { font-size: 28px; font-weight: 600; }
h2 { font-size: 24px; font-weight: 600; }
h3 { font-size: 20px; font-weight: 500; }
h4 { font-size: 16px; font-weight: 500; }

/* 正文字体 */
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
  line-height: 1.6;
}
```

---

## 组件开发规范

### 单文件组件结构
```vue
<template>
  <!-- 模板部分 -->
</template>

<script setup>
// Composition API（推荐）
import { ref, computed, onMounted } from 'vue'

// 状态定义
const data = ref([])

// 计算属性
const filteredData = computed(() => {
  return data.value.filter(item => item.status === 'active')
})

// 生命周期
onMounted(() => {
  loadData()
})
</script>

<style scoped>
/* 组件作用域样式 */
</style>
```

### 组件命名规范
- **文件名**: PascalCase（如`DataDashboard.vue`）
- **组件名**: PascalCase（如`<DataDashboard />`）
- **Props**: camelCase（如`userName`）
- **事件**: kebab-case（如`@update-data`）

### Props验证
```javascript
// 使用defineProps定义Props
const props = defineProps({
  title: {
    type: String,
    required: true
  },
  data: {
    type: Array,
    default: () => []
  },
  pageSize: {
    type: Number,
    default: 20,
    validator: (value) => value > 0 && value <= 100
  }
})
```

---

## 数据可视化规范

### ECharts图表配置
```javascript
// 标准图表配置
const chartOption = {
  title: {
    text: '销售趋势',
    left: 'center',
    textStyle: {
      fontSize: 18,
      fontWeight: 'bold'
    }
  },
  tooltip: {
    trigger: 'axis',
    axisPointer: {
      type: 'shadow'
    }
  },
  legend: {
    data: ['销售额', '订单数'],
    bottom: 0
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '10%',
    containLabel: true
  },
  xAxis: {
    type: 'category',
    data: dates
  },
  yAxis: {
    type: 'value'
  },
  series: [
    {
      name: '销售额',
      type: 'line',
      smooth: true,
      data: salesData
    }
  ]
}
```

### 图表类型选择
- **趋势分析**: 折线图（Line Chart）
- **占比分析**: 饼图（Pie Chart）
- **对比分析**: 柱状图（Bar Chart）
- **关联分析**: 散点图（Scatter Chart）
- **地理分析**: 地图（Map Chart）

---

## 交互设计规范

### 表单交互
```vue
<template>
  <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
    <el-form-item label="用户名" prop="username">
      <el-input v-model="form.username" placeholder="请输入用户名" />
    </el-form-item>
    
    <el-form-item label="邮箱" prop="email">
      <el-input v-model="form.email" type="email" placeholder="请输入邮箱" />
    </el-form-item>
    
    <el-form-item>
      <el-button type="primary" @click="submitForm">提交</el-button>
      <el-button @click="resetForm">重置</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const formRef = ref(null)
const form = ref({
  username: '',
  email: ''
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '长度在3到20个字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' }
  ]
}

const submitForm = async () => {
  const valid = await formRef.value.validate()
  if (valid) {
    // 提交逻辑
    ElMessage.success('提交成功')
  }
}

const resetForm = () => {
  formRef.value.resetFields()
}
</script>
```

### 加载状态
```vue
<template>
  <div v-loading="loading" element-loading-text="加载中...">
    <!-- 内容 -->
  </div>
</template>

<script setup>
import { ref } from 'vue'

const loading = ref(false)

const loadData = async () => {
  loading.value = true
  try {
    // 加载数据
  } finally {
    loading.value = false
  }
}
</script>
```

---

## 前端异步架构设计规范（v4.19.0新增）⭐⭐⭐

### **核心原则：局部刷新，避免全局阻塞**

**设计宗旨**：
- ✅ **局部刷新优先**：只刷新需要更新的区域，不影响其他模块
- ✅ **后台刷新**：非关键数据在后台静默刷新，不显示loading
- ✅ **乐观更新**：立即更新UI，后台验证，失败时回滚
- ✅ **最小化感知延迟**：优先显示可用内容，渐进式加载
- ❌ **禁止全局刷新**：一个模块的工作不应导致整个页面刷新
- ❌ **禁止全屏loading**：避免使用全屏loading阻塞用户操作

### **加载状态设计规范（强制）**

#### ✅ **推荐做法**

1. **局部Loading（Inline Loading）**
   ```vue
   <!-- ✅ 正确：只在表格区域显示loading -->
   <el-table v-loading="loading" :data="files">
     <!-- 表格内容 -->
   </el-table>
   
   <!-- 其他区域（统计卡片、历史记录）不受影响 -->
   <div class="stats-container">
     <!-- 统计信息始终可见 -->
   </div>
   ```

2. **后台刷新（Background Refresh）**
   ```javascript
   // ✅ 正确：支持后台刷新参数
   const loadFiles = async (showLoading = true) => {
     if (showLoading) {
       loading.value = true;
     }
     try {
       const data = await api.getDataSyncFiles(params);
       files.value = data.files || [];
     } finally {
       if (showLoading) {
         loading.value = false;
       }
     }
   };
   
   // 后台刷新（不显示loading）
   await loadFiles(false);
   ```

3. **乐观更新（Optimistic Updates）**
   ```javascript
   // ✅ 正确：立即更新UI，后台验证
   const syncSingle = async (fileId) => {
     // 1. 立即更新UI
     const file = files.value.find(f => f.id === fileId);
     if (file) {
       file.status = 'syncing';
     }
     
     // 2. 后台提交任务
     try {
       const result = await api.startSingleAutoIngest(fileId);
       startProgressPolling(result.task_id);
     } catch (error) {
       // 3. 失败时回滚
       if (file) {
         file.status = 'pending';
       }
     }
   };
   ```

4. **状态标签（Status Badge）**
   ```vue
   <!-- ✅ 正确：使用状态标签代替loading -->
   <el-tag :type="getStatusType(row.status)">
     <el-icon v-if="row.status === 'syncing'" class="is-loading">
       <Loading />
     </el-icon>
     {{ getStatusText(row.status) }}
   </el-tag>
   ```

5. **进度指示器（Progress Indicator）**
   ```vue
   <!-- ✅ 正确：显示具体进度 -->
   <el-progress 
     :percentage="taskProgress.percentage"
     :status="taskProgress.status"
   />
   ```

#### ❌ **禁止做法**

1. **全屏Loading**
   ```vue
   <!-- ❌ 错误：全屏loading阻塞整个页面 -->
   <div v-loading="globalLoading" class="full-page">
     <!-- 整个页面内容 -->
   </div>
   ```

2. **全局刷新**
   ```javascript
   // ❌ 错误：一个模块的工作导致整个页面刷新
   const syncSingle = async (fileId) => {
     await api.startSingleAutoIngest(fileId);
     // 刷新所有数据，包括不相关的模块
     await loadFiles();
     await loadGovernanceStats();
     await loadSyncHistory();
     await loadOtherModuleData(); // 不应该刷新
   };
   ```

3. **频繁刷新**
   ```javascript
   // ❌ 错误：任务进行中频繁刷新
   const pollTaskProgress = async (taskId) => {
     const progress = await api.getSyncTaskProgress(taskId);
     // 每次轮询都刷新，导致UI阻塞
     await loadFiles(); // 不应该
     await loadSyncHistory(); // 不应该
   };
   ```

4. **无超时机制**
   ```javascript
   // ❌ 错误：没有超时机制，可能导致长时间阻塞
   const loadFiles = async () => {
     loading.value = true;
     const data = await api.getDataSyncFiles(params); // 可能永远不返回
     loading.value = false;
   };
   ```

### **刷新策略规范（强制）**

#### **任务提交时**
- ✅ **立即更新UI**：使用乐观更新，立即显示"同步中"状态
- ✅ **启动轮询**：立即启动进度轮询
- ❌ **禁止刷新文件列表**：任务刚提交，文件状态不会立即改变

#### **任务进行中**
- ✅ **定期刷新同步历史**：每5-10次轮询刷新一次（后台刷新，不显示loading）
- ❌ **禁止刷新文件列表**：任务进行中，文件状态不会改变
- ❌ **禁止频繁刷新**：避免每2秒轮询都刷新数据

#### **任务完成时**
- ✅ **局部刷新**：只刷新相关的数据（文件列表、统计、历史记录）
- ✅ **后台刷新**：使用 `loadFiles(false)` 等后台刷新方式
- ✅ **延迟刷新**：延迟1-2秒，确保数据库已提交
- ❌ **禁止全屏loading**：刷新时不应阻塞其他区域

### **防阻塞检查清单（开发前必查）**

- [ ] 是否使用了全屏loading？
- [ ] 是否一个模块的工作导致全局刷新？
- [ ] 是否在任务进行中频繁刷新数据？
- [ ] 是否添加了超时机制？
- [ ] 是否支持后台刷新（不显示loading）？
- [ ] 是否使用了乐观更新？
- [ ] 是否使用了状态标签代替loading？

### **业界参考**
- **Gmail**：使用骨架屏和乐观更新
- **GitHub**：局部loading + 状态标签
- **Notion**：分块加载 + 后台刷新
- **Linear**：乐观更新 + 进度指示器

### **历史教训**
- ✗ 全屏loading导致整个页面阻塞 → 用户体验差
- ✗ 任务进行中频繁刷新文件列表 → API压力大，UI阻塞
- ✗ 无超时机制 → 长时间loading，用户无法操作
- ✗ 全局刷新 → 一个模块的工作影响其他模块

---

### 错误提示
```javascript
import { ElMessage, ElMessageBox } from 'element-plus'

// 成功提示
ElMessage.success('操作成功')

// 警告提示
ElMessage.warning('请注意')

// 错误提示
ElMessage.error('操作失败: ' + error.message)

// 确认对话框
ElMessageBox.confirm('确定要删除吗？', '警告', {
  confirmButtonText: '确定',
  cancelButtonText: '取消',
  type: 'warning'
}).then(() => {
  // 确认操作
}).catch(() => {
  // 取消操作
})
```

---

## 表格设计规范

### 标准表格
```vue
<template>
  <el-table :data="tableData" stripe border>
    <el-table-column type="selection" width="55" />
    <el-table-column prop="id" label="ID" width="80" />
    <el-table-column prop="name" label="名称" />
    <el-table-column prop="status" label="状态" width="100">
      <template #default="{ row }">
        <el-tag :type="getStatusType(row.status)">
          {{ getStatusText(row.status) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="180" fixed="right">
      <template #default="{ row }">
        <el-button size="small" @click="handleEdit(row)">编辑</el-button>
        <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
      </template>
    </el-table-column>
  </el-table>
  
  <!-- 分页 -->
  <el-pagination
    v-model:current-page="currentPage"
    v-model:page-size="pageSize"
    :total="total"
    :page-sizes="[10, 20, 50, 100]"
    layout="total, sizes, prev, pager, next, jumper"
    @size-change="handleSizeChange"
    @current-change="handleCurrentChange"
  />
</template>
```

### 表格优化建议
- ✅ **虚拟滚动**: 大数据量（>1000行）使用虚拟滚动
- ✅ **分页加载**: 服务端分页，避免一次性加载所有数据
- ✅ **固定列**: 重要列固定，操作列固定在右侧
- ✅ **排序筛选**: 提供排序和筛选功能

---

## 性能优化

### 组件懒加载
```javascript
// 路由懒加载
const routes = [
  {
    path: '/dashboard',
    component: () => import('@/views/Dashboard.vue')
  }
]
```

### 列表渲染优化
```vue
<template>
  <!-- 使用v-show替代v-if（频繁切换） -->
  <div v-show="isVisible">内容</div>
  
  <!-- 使用key优化列表渲染 -->
  <div v-for="item in items" :key="item.id">
    {{ item.name }}
  </div>
  
  <!-- 避免在v-for中使用v-if -->
  <div v-for="item in filteredItems" :key="item.id">
    {{ item.name }}
  </div>
</template>

<script setup>
import { computed } from 'vue'

// 使用计算属性过滤
const filteredItems = computed(() => {
  return items.value.filter(item => item.status === 'active')
})
</script>
```

### 图片优化
```vue
<template>
  <!-- 使用懒加载 -->
  <img v-lazy="imageUrl" alt="图片描述" />
  
  <!-- 使用WebP格式 -->
  <picture>
    <source :srcset="imageUrl + '.webp'" type="image/webp" />
    <img :src="imageUrl + '.jpg'" alt="图片描述" />
  </picture>
</template>
```

---

## 可访问性（Accessibility）

### 语义化HTML
```vue
<template>
  <!-- 使用语义化标签 -->
  <nav>导航栏</nav>
  <main>主要内容</main>
  <aside>侧边栏</aside>
  <footer>页脚</footer>
  
  <!-- 使用aria属性 -->
  <button aria-label="关闭对话框" @click="closeDialog">
    <span aria-hidden="true">&times;</span>
  </button>
</template>
```

### 键盘导航
```vue
<template>
  <!-- 支持键盘操作 -->
  <div
    tabindex="0"
    @keydown.enter="handleClick"
    @keydown.space.prevent="handleClick"
  >
    可点击元素
  </div>
</template>
```

---

## 国际化（i18n）

### 多语言支持
```javascript
// 使用vue-i18n
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      welcome: '欢迎',
      logout: '退出'
    },
    'en-US': {
      welcome: 'Welcome',
      logout: 'Logout'
    }
  }
})
```

```vue
<template>
  <h1>{{ $t('welcome') }}</h1>
  <el-button @click="logout">{{ $t('logout') }}</el-button>
</template>
```

---

## 样式管理

### CSS模块化
```vue
<style scoped>
/* 组件作用域样式 */
.container {
  padding: 20px;
}
</style>

<style>
/* 全局样式 */
:root {
  --primary-color: #409EFF;
}
</style>
```

### CSS变量
```css
/* 定义全局CSS变量 */
:root {
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
}

/* 使用CSS变量 */
.card {
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}
```

---

## 测试规范

### 单元测试
```javascript
import { mount } from '@vue/test-utils'
import DataTable from '@/components/DataTable.vue'

describe('DataTable', () => {
  it('renders table data correctly', () => {
    const wrapper = mount(DataTable, {
      props: {
        data: [{ id: 1, name: 'Test' }]
      }
    })
    
    expect(wrapper.find('.el-table').exists()).toBe(true)
    expect(wrapper.text()).toContain('Test')
  })
})
```

### E2E测试
```javascript
// 使用Cypress进行E2E测试
describe('Dashboard', () => {
  it('loads dashboard and displays data', () => {
    cy.visit('/dashboard')
    cy.get('.stats-card').should('be.visible')
    cy.get('.chart-container').should('exist')
  })
})
```

---

## 最佳实践总结

### DO（推荐）
- ✅ 使用Composition API开发组件
- ✅ 使用TypeScript增强类型安全（可选）
- ✅ 使用原生CSS实现布局
- ✅ 组件保持单一职责
- ✅ 使用Pinia管理全局状态
- ✅ 使用ECharts实现专业数据可视化
- ✅ 实现响应式设计
- ✅ 优化性能（懒加载、虚拟滚动）
- ✅ 提供加载状态和错误提示
- ✅ 编写单元测试

### DON'T（禁止）
- ❌ 过度依赖Element Plus容器组件
- ❌ 在组件中直接操作DOM
- ❌ 使用全局CSS污染样式
- ❌ 在模板中写复杂逻辑
- ❌ 忽略性能优化
- ❌ 缺少错误处理
- ❌ 硬编码文本（应使用i18n）
- ❌ 忽略可访问性

---

**最后更新**: 2026-01-03  
**维护**: Frontend Team  
**状态**: ✅ 企业级标准（v4.19.0新增前端异步架构设计规范）

