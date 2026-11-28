# 现代化UI设计规范 - 基于赛狐ERP设计理念

## 🎯 设计理念

基于赛狐ERP的专业级数据看板设计，打造现代化、高效的企业级跨境电商ERP系统界面。

## 🎨 视觉设计系统

### 色彩体系
```css
/* 主色调 - 专业蓝 */
--primary-color: #2c3e50;        /* 深蓝灰 */
--primary-light: #34495e;        /* 浅蓝灰 */
--primary-lighter: #7f8c8d;      /* 更浅蓝灰 */

/* 辅助色 - 活力蓝 */
--secondary-color: #3498db;      /* 蓝色 */
--secondary-light: #5dade2;      /* 浅蓝 */
--secondary-lighter: #85c1e9;    /* 更浅蓝 */

/* 功能色 */
--success-color: #27ae60;        /* 绿色 */
--warning-color: #f39c12;        /* 橙色 */
--error-color: #e74c3c;          /* 红色 */
--info-color: #17a2b8;           /* 信息蓝 */

/* 中性色 */
--text-primary: #2c3e50;         /* 主要文字 */
--text-secondary: #7f8c8d;       /* 次要文字 */
--text-disabled: #bdc3c7;        /* 禁用文字 */
--border-color: #e9ecef;         /* 边框色 */
--background-color: #f8f9fa;     /* 背景色 */
```

### 渐变色方案
```css
/* 主渐变色 */
--gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
--gradient-secondary: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
--gradient-success: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);

/* 卡片渐变色 */
--gradient-card: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
--gradient-header: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### 字体系统
```css
/* 字体族 */
--font-family-primary: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
--font-family-mono: 'Fira Code', 'Monaco', 'Consolas', monospace;

/* 字体大小 */
--font-size-xs: 12px;
--font-size-sm: 14px;
--font-size-base: 16px;
--font-size-lg: 18px;
--font-size-xl: 20px;
--font-size-2xl: 24px;
--font-size-3xl: 30px;
--font-size-4xl: 36px;

/* 字体权重 */
--font-weight-light: 300;
--font-weight-normal: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;
--font-weight-bold: 700;
```

### 间距系统
```css
/* 基础间距单位 */
--spacing-xs: 4px;
--spacing-sm: 8px;
--spacing-base: 16px;
--spacing-lg: 24px;
--spacing-xl: 32px;
--spacing-2xl: 48px;
--spacing-3xl: 64px;

/* 组件间距 */
--component-padding: var(--spacing-lg);
--card-padding: var(--spacing-xl);
--section-margin: var(--spacing-2xl);
```

## 🏗️ 布局设计

### 整体布局
```
┌─────────────────────────────────────────────────────────────┐
│                    顶部导航栏 (60px)                        │
├─────────────┬───────────────────────────────────────────────┤
│             │                                               │
│   侧边栏    │                主内容区域                     │
│   (250px)   │                                               │
│             │                                               │
│             │                                               │
└─────────────┴───────────────────────────────────────────────┘
```

### 响应式断点
```css
/* 移动端 */
@media (max-width: 768px) {
  --sidebar-width: 0px;        /* 隐藏侧边栏 */
  --main-content-width: 100%;  /* 全宽显示 */
}

/* 平板端 */
@media (min-width: 769px) and (max-width: 1024px) {
  --sidebar-width: 200px;      /* 缩小侧边栏 */
  --main-content-width: calc(100% - 200px);
}

/* 桌面端 */
@media (min-width: 1025px) {
  --sidebar-width: 250px;      /* 标准侧边栏 */
  --main-content-width: calc(100% - 250px);
}
```

## 🎯 组件设计规范

### 1. 侧边栏设计
```vue
<template>
  <el-aside width="250px" class="sidebar">
    <!-- Logo区域 -->
    <div class="sidebar-logo">
      <h3>🎯 智能ERP系统</h3>
    </div>
    
    <!-- 导航菜单 -->
    <el-menu
      :default-active="activeMenu"
      class="sidebar-menu"
      router
      background-color="#2c3e50"
      text-color="#ecf0f1"
      active-text-color="#3498db"
    >
      <el-menu-item index="/dashboard">
        <el-icon><DataBoard /></el-icon>
        <span>数据看板</span>
      </el-menu-item>
      <el-menu-item index="/collection">
        <el-icon><Collection /></el-icon>
        <span>数据采集</span>
      </el-menu-item>
      <el-menu-item index="/management">
        <el-icon><Setting /></el-icon>
        <span>数据管理</span>
      </el-menu-item>
    </el-menu>
  </el-aside>
</template>

<style scoped>
.sidebar {
  background-color: var(--primary-color);
  min-height: 100vh;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
}

.sidebar-logo {
  padding: var(--spacing-xl);
  text-align: center;
  color: #ecf0f1;
  border-bottom: 1px solid var(--primary-light);
}

.sidebar-logo h3 {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
}

.sidebar-menu {
  border: none;
}
</style>
```

### 2. 顶部导航栏设计
```vue
<template>
  <el-header class="header">
    <div class="header-content">
      <div class="header-title">
        <h2>{{ pageTitle }}</h2>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="refreshData">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
        <el-dropdown>
          <el-button type="text">
            <el-icon><User /></el-icon>
            用户菜单
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item>个人设置</el-dropdown-item>
              <el-dropdown-item>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
  </el-header>
</template>

<style scoped>
.header {
  background: var(--gradient-header);
  color: white;
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-xl);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.header-title h2 {
  margin: 0;
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-2xl);
}

.header-actions {
  display: flex;
  gap: var(--spacing-base);
  align-items: center;
}
</style>
```

### 3. 数据看板设计
```vue
<template>
  <div class="dashboard">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>📊 智能数据看板</h1>
      <p>实时监控 • 智能分析 • 决策支持</p>
    </div>

    <!-- KPI指标卡片 -->
    <el-row :gutter="20" class="kpi-cards">
      <el-col :span="6">
        <div class="kpi-card">
          <div class="kpi-icon">
            <el-icon><DataBoard /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-value">{{ totalFiles }}</div>
            <div class="kpi-label">总文件数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="kpi-card">
          <div class="kpi-icon">
            <el-icon><Check /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-value">{{ processedFiles }}</div>
            <div class="kpi-label">已处理文件</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="kpi-card">
          <div class="kpi-icon">
            <el-icon><Clock /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-value">{{ pendingFiles }}</div>
            <div class="kpi-label">待处理文件</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="kpi-card">
          <div class="kpi-icon">
            <el-icon><Warning /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-value">{{ failedFiles }}</div>
            <div class="kpi-label">失败文件</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20" class="chart-section">
      <el-col :span="12">
        <el-card class="chart-card">
          <template #header>
            <span>平台文件分布</span>
          </template>
          <div class="chart-container">
            <div ref="pieChart" class="chart"></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="chart-card">
          <template #header>
            <span>数据域分布</span>
          </template>
          <div class="chart-container">
            <div ref="barChart" class="chart"></div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近处理文件表格 -->
    <el-card class="table-card">
      <template #header>
        <span>最近处理的文件</span>
      </template>
      <el-table :data="recentFiles" style="width: 100%" stripe>
        <el-table-column prop="fileName" label="文件名" min-width="200" />
        <el-table-column prop="platform" label="平台" width="120">
          <template #default="{ row }">
            <el-tag :type="getPlatformType(row.platform)">
              {{ row.platform }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="dataDomain" label="数据域" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="discoveryTime" label="发现时间" width="180" />
        <el-table-column prop="lastProcessed" label="最后处理" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.dashboard {
  padding: var(--spacing-xl);
}

.page-header {
  text-align: center;
  margin-bottom: var(--spacing-2xl);
  background: var(--gradient-primary);
  color: white;
  padding: var(--spacing-2xl);
  border-radius: 12px;
}

.page-header h1 {
  margin: 0 0 var(--spacing-base) 0;
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-bold);
}

.page-header p {
  margin: 0;
  opacity: 0.9;
  font-size: var(--font-size-lg);
}

.kpi-cards {
  margin-bottom: var(--spacing-2xl);
}

.kpi-card {
  background: var(--gradient-card);
  border-radius: 12px;
  padding: var(--spacing-xl);
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transition: transform 0.3s ease;
}

.kpi-card:hover {
  transform: translateY(-4px);
}

.kpi-icon {
  font-size: var(--font-size-3xl);
  color: var(--secondary-color);
}

.kpi-value {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}

.kpi-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-xs);
}

.chart-section {
  margin-bottom: var(--spacing-2xl);
}

.chart-card {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.chart-container {
  height: 300px;
}

.chart {
  width: 100%;
  height: 100%;
}

.table-card {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
</style>
```

### 4. 数据表格密度（2026-11-28 补齐）

**为什么补这一节**：2026-11-28 复查发现，密度规则其实**早就写在**
`frontend/src/assets/erp-layout.css` 里（`.erp-compact / .erp-comfortable / .erp-spacious`），
但**全仓 0 个页面采用** —— 37 处用 `erp-table` 的页面全部落在 Element Plus 默认密度上，
行高 ~50px，录入型表格一屏只能看 10 行。规则存在、实施缺位，属于典型的
「规范被架空」：没有守护测试，规范就会被慢慢绕过。

**更隐蔽的一层（真机复核才发现）**：密度规则所在的 `erp-layout.css` **从未被任何入口引入**，
所以哪怕页面写上了 `erp-compact`，它也只是挂上去的一枚类名 —— 实测 `td` 内边距仍是
Element Plus 默认的 8px、行高 41px、字号 14px，一条密度规则都没命中。
⇒ 规范不只是「没人用」，还是**根本没进构建**。因此密度规则已独立成
`frontend/src/assets/erp-density.css`，并由 `main.js` 全局引入；
该文件全部规则都被三个密度类闸住，未声明密度类的页面与表格**零影响**。

#### 三档密度（唯一真源：`frontend/src/assets/erp-density.css`）

| 档位 | 类名 | 单元格上下内边距 | 字号 | 典型场景 |
|---|---|---|---|---|
| 紧凑 | `.erp-compact` | 4px（表头 6px） | 13px | 录入表格、数据浏览器、按月/按店台账 |
| 舒适 | `.erp-comfortable` | 12px | 默认 | 常规管理列表 |
| 宽松 | `.erp-spacious` | 16px | 默认 | 表单型页面 |

#### 用法

```vue
<!-- 表格 -->
<el-table class="erp-table erp-compact" :data="rows" stripe border>
  <el-table-column label="金额" width="110">
    <template #default="{ row }">
      <!-- 行内控件一律 small（24px），否则 32px 的控件 + 4px 内边距就把行撑到 40px+ -->
      <el-input-number v-model="row.amount" size="small" :controls="false" />
    </template>
  </el-table-column>
</el-table>
```

规则：
1. 表格加 `erp-table erp-compact` 两个类；`erp-table` 管宽度与溢出，`erp-compact` 管密度。
   两类都可挂在**祖先容器**上，也可直接挂在 `el-table` 根节点上（Element Plus 的
   `el-table` 根节点本身就是 `.el-table`，只写后代选择器时挂在根节点上一条都命中不了）。
2. **行内控件一律 `size="small"`**（24px）。这是紧凑档能否生效的前提 ——
   默认尺寸控件（32px）比紧凑行高还高，密度就白改了。
3. 单元格内**多行内容**（成本明细、人员列表、店铺+租户）必须压成**一行摘要**，
   完整信息进 `el-tooltip`。多行内容是行高失控的第一原因。
   ⚠️ 但**状态/警示类标签不能挪进 tooltip** —— 必须留在摘要行内可见；
   需要同行时用「输入框可压缩、标签不可压缩」的 flex 行（`flex: 0 0 auto`）。
4. 统计卡片不许用 `el-card` 排成多行栅格；指标多时用**一行紧凑指标条**，
   避免最后一张卡换行留下整块空白。
5. 页面级间距用 `.erp-mb-sm / .erp-mb-md`；`margin-bottom: 20px` 这类大间距要收敛。

#### 守护

`frontend/scripts/erpDensityContract.test.mjs` 断言：三档都定义在 `erp-density.css`、
**该文件被 `main.js` 真正引入**、规则只有一份出处、紧凑档同时支持两种声明写法、
宽松档表头选择器正确、紧凑档给出可量化指标、**两个目标页面确实声明了紧凑档**、
行内控件用 small、用户侧「备注」字段已退役、人员归属页接入 `PageHeader`。
`frontend/scripts/shopAssignmentDensity.test.mjs` 断言归属页的成本明细摘要、
**输入框与状态标签同行**等具体排版约束。
**没有守护测试的规范等于没有规范**；只断言「文本存在」也不够 ——
必须断言「规则进得了构建」（即入口确实 import 了密度文件）。

#### 页头 SSOT

页头一律用 `frontend/src/components/common/PageHeader.vue`（`title` / `subtitle` / `icon` / `family`），
不得再写裸 `<h1 style="font-size: 24px; ...">`。页头间距由组件内部控制，页面不另加。

## 📱 响应式设计

### 移动端适配
```css
@media (max-width: 768px) {
  .dashboard {
    padding: var(--spacing-base);
  }
  
  .page-header {
    padding: var(--spacing-lg);
  }
  
  .page-header h1 {
    font-size: var(--font-size-2xl);
  }
  
  .kpi-cards .el-col {
    margin-bottom: var(--spacing-base);
  }
  
  .kpi-card {
    padding: var(--spacing-lg);
  }
  
  .chart-section .el-col {
    margin-bottom: var(--spacing-base);
  }
  
  .chart-container {
    height: 250px;
  }
}
```

### 平板端适配
```css
@media (min-width: 769px) and (max-width: 1024px) {
  .kpi-cards .el-col {
    margin-bottom: var(--spacing-base);
  }
  
  .chart-section .el-col {
    margin-bottom: var(--spacing-base);
  }
}
```

## 🎨 动画效果

### 页面过渡动画
```css
.page-enter-active,
.page-leave-active {
  transition: all 0.3s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateX(30px);
}

.page-leave-to {
  opacity: 0;
  transform: translateX(-30px);
}
```

### 卡片悬停效果
```css
.card-hover {
  transition: all 0.3s ease;
}

.card-hover:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}
```

### 加载动画
```css
.loading-spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
```

## 🔧 实现指南

### 1. 主题配置
```javascript
// theme.js
export const theme = {
  colors: {
    primary: '#2c3e50',
    secondary: '#3498db',
    success: '#27ae60',
    warning: '#f39c12',
    error: '#e74c3c',
  },
  gradients: {
    primary: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    secondary: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
  },
  spacing: {
    xs: '4px',
    sm: '8px',
    base: '16px',
    lg: '24px',
    xl: '32px',
  },
  typography: {
    fontFamily: "'Helvetica Neue', Helvetica, 'PingFang SC', sans-serif",
    fontSize: {
      xs: '12px',
      sm: '14px',
      base: '16px',
      lg: '18px',
      xl: '20px',
    },
  },
}
```

### 2. 组件库配置
```javascript
// element-plus配置
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

app.use(ElementPlus, {
  locale: zhCn,
  size: 'default',
  zIndex: 3000,
})
```

### 3. 图表配置
```javascript
// echarts配置
import * as echarts from 'echarts'

const chartConfig = {
  backgroundColor: 'transparent',
  textStyle: {
    fontFamily: theme.typography.fontFamily,
    color: theme.colors.textPrimary,
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '3%',
    containLabel: true,
  },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    textStyle: {
      color: '#fff',
    },
  },
}
```

## 📊 性能优化

### 1. 懒加载
```javascript
// 路由懒加载
const routes = [
  {
    path: '/dashboard',
    component: () => import('@/views/Dashboard.vue'),
  },
  {
    path: '/collection',
    component: () => import('@/views/Collection.vue'),
  },
]
```

### 2. 组件缓存
```vue
<template>
  <keep-alive>
    <router-view />
  </keep-alive>
</template>
```

### 3. 图片优化
```javascript
// 图片懒加载
import { LazyLoad } from '@/utils/lazy-load'

export default {
  mounted() {
    LazyLoad.init()
  },
}
```

---

**设计原则**: 现代化、专业化、响应式、高性能  
**参考标准**: 赛狐ERP专业级数据看板  
**技术栈**: Vue.js 3 + Element Plus + ECharts  
**版本**: v1.0  
**状态**: 设计完成
