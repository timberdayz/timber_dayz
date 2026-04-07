# 前端数据看板和用户管理系统设计规划（v4.7.0）

**日期**: 2025-11-01  
**版本**: v4.7.0（规划中）  
**状态**: 📋 规划阶段

---

## 📋 需求概述

### 用户需求

1. **前端数据看板设计**
   - 各类数据看板（销售、库存、财务等）
   - 实时数据同步和展示
   - 多维度数据分析和可视化

2. **用户管理和权限系统**
   - 多角色支持（开发者、管理员、主管、操作员）
   - 注册账号和审批流程
   - 电子流设计（审批流程可视化）

### 设计目标

- ✅ **企业级ERP标准**：参考SAP、Oracle ERP设计
- ✅ **现代化UI/UX**：专业级数据可视化界面
- ✅ **细粒度权限控制**：基于角色的访问控制（RBAC）
- ✅ **电子审批流程**：完整的审批流程可视化

---

## 🎯 前端数据看板设计

### 1. 看板架构设计

#### 1.1 看板分类

```
数据看板系统
├── 销售看板（Sales Dashboard）
│   ├── 销售概览（GMV、订单数、客单价）
│   ├── 销售趋势（日/周/月趋势图）
│   ├── 店铺排名（Top N店铺）
│   ├── 产品排名（Top N产品）
│   └── 区域分析（按国家/地区）
│
├── 库存看板（Inventory Dashboard）
│   ├── 库存概览（总库存、缺货预警）
│   ├── 库存周转率
│   ├── 安全库存预警
│   └── 库存分布（按店铺/产品）
│
├── 财务看板（Finance Dashboard）
│   ├── 财务概览（收入、成本、利润）
│   ├── P&L报表（利润表）
│   ├── 现金流分析
│   ├── 费用分析
│   └── 税务报表
│
├── 产品看板（Product Dashboard）
│   ├── 产品表现（浏览量、转化率）
│   ├── 产品排名
│   ├── 新品表现
│   └── 产品生命周期分析
│
└── 运营看板（Operations Dashboard）
    ├── 运营指标（客服、物流、营销）
    ├── 运营效率分析
    └── 运营成本分析
```

#### 1.2 技术架构

**前端技术栈**：
- Vue.js 3 + Composition API
- Element Plus（UI组件库）
- ECharts（数据可视化）
- Pinia（状态管理）
- Vue Router（路由管理）

**后端API设计**：
- RESTful API（FastAPI）
- WebSocket（实时数据推送）
- 缓存策略（Redis）

**数据同步机制**：
- 实时同步（WebSocket推送）
- 定时刷新（每5分钟）
- 手动刷新（用户触发）

### 2. 看板组件设计

#### 2.1 通用组件

**KPI卡片组件** (`KPICard.vue`)
```vue
<KPICard
  title="总销售额"
  value="1,234,567"
  unit="CNY"
  trend="+12.5%"
  trendType="up"
  :loading="false"
/>
```

**图表组件** (`ChartCard.vue`)
```vue
<ChartCard
  title="销售趋势"
  type="line"
  :data="chartData"
  :options="chartOptions"
  height="300px"
/>
```

**数据表格组件** (`DataTable.vue`)
```vue
<DataTable
  :columns="columns"
  :data="tableData"
  :pagination="pagination"
  :loading="loading"
/>
```

**筛选器组件** (`FilterBar.vue`)
```vue
<FilterBar
  :filters="filters"
  @filter-change="handleFilterChange"
/>
```

#### 2.2 看板路由设计

```javascript
// frontend/src/router/index.js
{
  path: '/dashboard',
  name: 'Dashboard',
  component: () => import('@/views/Dashboard.vue'),
  children: [
    {
      path: 'sales',
      name: 'SalesDashboard',
      component: () => import('@/views/dashboard/SalesDashboard.vue'),
      meta: { requiresAuth: true, roles: ['developer', 'admin', 'supervisor', 'operator'] }
    },
    {
      path: 'inventory',
      name: 'InventoryDashboard',
      component: () => import('@/views/dashboard/InventoryDashboard.vue'),
      meta: { requiresAuth: true, roles: ['developer', 'admin', 'supervisor', 'operator'] }
    },
    {
      path: 'finance',
      name: 'FinanceDashboard',
      component: () => import('@/views/dashboard/FinanceDashboard.vue'),
      meta: { requiresAuth: true, roles: ['developer', 'admin', 'supervisor'] }
    },
    {
      path: 'product',
      name: 'ProductDashboard',
      component: () => import('@/views/dashboard/ProductDashboard.vue'),
      meta: { requiresAuth: true, roles: ['developer', 'admin', 'supervisor', 'operator'] }
    },
    {
      path: 'operations',
      name: 'OperationsDashboard',
      component: () => import('@/views/dashboard/OperationsDashboard.vue'),
      meta: { requiresAuth: true, roles: ['developer', 'admin', 'supervisor'] }
    }
  ]
}
```

### 3. 数据API设计

#### 3.1 销售看板API

```python
# backend/routers/dashboard.py

@router.get("/api/dashboard/sales/overview")
async def get_sales_overview(
    start_date: str,
    end_date: str,
    shop_ids: Optional[List[str]] = None,
    platform: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    获取销售概览数据
    
    返回：
    {
        "gmv": 1234567.89,
        "order_count": 1234,
        "avg_order_value": 999.99,
        "growth_rate": 12.5,
        "trend": "up"  # up/down/stable
    }
    """
    pass

@router.get("/api/dashboard/sales/trend")
async def get_sales_trend(
    start_date: str,
    end_date: str,
    granularity: str = "daily",  # daily/weekly/monthly
    shop_ids: Optional[List[str]] = None,
    db: Session = Depends(get_db)
):
    """
    获取销售趋势数据
    
    返回：
    {
        "dates": ["2025-01-01", "2025-01-02", ...],
        "values": [1000, 1200, ...],
        "labels": ["销售额", "订单数", ...]
    }
    """
    pass

@router.get("/api/dashboard/sales/top-shops")
async def get_top_shops(
    start_date: str,
    end_date: str,
    top_n: int = 10,
    metric: str = "gmv",  # gmv/order_count
    db: Session = Depends(get_db)
):
    """
    获取Top N店铺排名
    
    返回：
    {
        "shops": [
            {
                "shop_id": "shop001",
                "shop_name": "Shop 1",
                "gmv": 123456.78,
                "order_count": 123,
                "rank": 1
            },
            ...
        ]
    }
    """
    pass
```

---

## 👥 用户管理和权限系统设计

### 1. 角色设计

#### 1.1 角色定义

**开发者（Developer）**
- 权限：所有功能（包括开发功能）
- 功能：字段映射、数据采集、系统配置、开发工具
- 特点：最高权限，用于开发和维护

**管理员（Admin）**
- 权限：系统管理和业务管理
- 功能：用户管理、账号管理、数据看板、报表导出
- 特点：系统管理权限，负责日常运营

**主管（Supervisor）**
- 权限：业务审批和监督
- 功能：数据看板、审批流程、报表查看、数据分析
- 特点：业务审批权限，负责决策和监督

**操作员（Operator）**
- 权限：基础操作权限
- 功能：数据查看、基础操作、数据录入
- 特点：日常操作权限，执行具体业务

#### 1.2 权限矩阵

| 功能模块 | 开发者 | 管理员 | 主管 | 操作员 |
|---------|--------|--------|------|--------|
| 字段映射 | ✅ | ❌ | ❌ | ❌ |
| 数据采集 | ✅ | ✅ | ❌ | ❌ |
| 数据看板 | ✅ | ✅ | ✅ | ✅（只读） |
| 财务管理 | ✅ | ✅ | ✅ | ❌ |
| 用户管理 | ✅ | ✅ | ❌ | ❌ |
| 账号管理 | ✅ | ✅ | ✅（审批） | ❌ |
| 审批流程 | ✅ | ✅ | ✅ | ❌ |
| 报表导出 | ✅ | ✅ | ✅ | ✅ |
| 系统配置 | ✅ | ✅ | ❌ | ❌ |

### 2. 数据库设计

#### 2.1 用户表（Users）

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'operator',  -- developer/admin/supervisor/operator
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/active/suspended/deleted
    department VARCHAR(50),
    phone VARCHAR(20),
    avatar_url VARCHAR(255),
    last_login_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    updated_by INTEGER REFERENCES users(id)
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_status ON users(status);
```

#### 2.2 角色表（Roles）

```sql
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    role_code VARCHAR(20) UNIQUE NOT NULL,  -- developer/admin/supervisor/operator
    role_name VARCHAR(50) NOT NULL,
    description TEXT,
    permissions JSONB,  -- 存储权限配置
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 初始化角色数据
INSERT INTO roles (role_code, role_name, description, permissions) VALUES
('developer', '开发者', '系统开发维护人员', '{"all": true}'),
('admin', '管理员', '系统管理员', '{"dashboard": true, "user_management": true, "account_management": true}'),
('supervisor', '主管', '业务主管', '{"dashboard": true, "approval": true, "report": true}'),
('operator', '操作员', '基础操作人员', '{"dashboard": {"read": true}, "report": {"read": true}}');
```

#### 2.3 权限表（Permissions）

```sql
CREATE TABLE permissions (
    id SERIAL PRIMARY KEY,
    permission_code VARCHAR(50) UNIQUE NOT NULL,
    permission_name VARCHAR(100) NOT NULL,
    module VARCHAR(50) NOT NULL,  -- dashboard/field_mapping/data_collection/user_management
    action VARCHAR(50) NOT NULL,  -- create/read/update/delete/approve
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 初始化权限数据
INSERT INTO permissions (permission_code, permission_name, module, action, description) VALUES
('field_mapping:create', '字段映射-创建', 'field_mapping', 'create', '创建字段映射'),
('field_mapping:read', '字段映射-查看', 'field_mapping', 'read', '查看字段映射'),
('field_mapping:update', '字段映射-更新', 'field_mapping', 'update', '更新字段映射'),
('field_mapping:delete', '字段映射-删除', 'field_mapping', 'delete', '删除字段映射'),
('dashboard:sales:read', '销售看板-查看', 'dashboard', 'read', '查看销售看板'),
('dashboard:finance:read', '财务看板-查看', 'dashboard', 'read', '查看财务看板'),
('user_management:create', '用户管理-创建', 'user_management', 'create', '创建用户'),
('user_management:approve', '用户管理-审批', 'user_management', 'approve', '审批用户注册'),
('account_management:create', '账号管理-创建', 'account_management', 'create', '创建账号'),
('account_management:approve', '账号管理-审批', 'account_management', 'approve', '审批账号注册');
```

#### 2.4 账号注册申请表（AccountRegistration）

```sql
CREATE TABLE account_registrations (
    id SERIAL PRIMARY KEY,
    applicant_id INTEGER NOT NULL REFERENCES users(id),
    platform VARCHAR(50) NOT NULL,  -- shopee/tiktok/amazon
    account_name VARCHAR(100) NOT NULL,
    shop_id VARCHAR(100),
    shop_name VARCHAR(200),
    login_url VARCHAR(500),
    account_type VARCHAR(50),  -- seller/buyer/supplier
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/approved/rejected
    current_step INTEGER NOT NULL DEFAULT 1,  -- 当前审批步骤
    total_steps INTEGER NOT NULL DEFAULT 3,  -- 总审批步骤数
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    rejected_at TIMESTAMP,
    rejection_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_account_registrations_applicant ON account_registrations(applicant_id);
CREATE INDEX idx_account_registrations_status ON account_registrations(status);
CREATE INDEX idx_account_registrations_platform ON account_registrations(platform);
```

#### 2.5 审批流程表（ApprovalWorkflow）

```sql
CREATE TABLE approval_workflows (
    id SERIAL PRIMARY KEY,
    registration_id INTEGER NOT NULL REFERENCES account_registrations(id),
    step_number INTEGER NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    approver_role VARCHAR(20) NOT NULL,  -- admin/supervisor
    approver_id INTEGER REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/approved/rejected
    comment TEXT,
    approved_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_approval_workflows_registration ON approval_workflows(registration_id);
CREATE INDEX idx_approval_workflows_status ON approval_workflows(status);
CREATE INDEX idx_approval_workflows_approver ON approval_workflows(approver_id);
```

### 3. 电子审批流程设计

#### 3.1 审批流程定义

**账号注册审批流程**（3步）

```
步骤1: 提交申请
  ├─ 申请人：操作员/管理员
  ├─ 提交信息：平台、账号名、店铺ID、登录URL
  └─ 状态：pending

步骤2: 主管审批
  ├─ 审批人：主管（supervisor）
  ├─ 审批内容：审核账号信息、店铺信息
  ├─ 操作：批准/拒绝
  └─ 状态：approved/rejected

步骤3: 管理员确认
  ├─ 审批人：管理员（admin）
  ├─ 审批内容：最终确认、激活账号
  ├─ 操作：批准/拒绝
  └─ 状态：approved/rejected → 账号激活
```

#### 3.2 电子流界面设计

**审批流程可视化组件** (`ApprovalFlow.vue`)

```vue
<template>
  <div class="approval-flow">
    <div class="flow-steps">
      <div 
        v-for="(step, index) in steps" 
        :key="index"
        :class="['step', getStepStatusClass(step)]"
      >
        <div class="step-icon">
          <el-icon v-if="step.status === 'approved'"><Check /></el-icon>
          <el-icon v-else-if="step.status === 'rejected'"><Close /></el-icon>
          <el-icon v-else><Clock /></el-icon>
        </div>
        <div class="step-content">
          <div class="step-title">{{ step.step_name }}</div>
          <div class="step-info">
            <span v-if="step.approver">审批人：{{ step.approver.name }}</span>
            <span v-if="step.approved_at">审批时间：{{ formatDate(step.approved_at) }}</span>
          </div>
          <div v-if="step.comment" class="step-comment">
            审批意见：{{ step.comment }}
          </div>
        </div>
        <div class="step-connector" v-if="index < steps.length - 1"></div>
      </div>
    </div>
    
    <div class="flow-actions" v-if="canApprove">
      <el-button type="primary" @click="handleApprove">批准</el-button>
      <el-button type="danger" @click="handleReject">拒绝</el-button>
    </div>
  </div>
</template>
```

#### 3.3 审批API设计

```python
# backend/routers/approval.py

@router.post("/api/approval/account-registration/submit")
async def submit_account_registration(
    registration: AccountRegistrationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    提交账号注册申请
    
    权限：developer/admin/operator
    """
    pass

@router.get("/api/approval/account-registration/list")
async def list_account_registrations(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取账号注册申请列表
    
    权限：
    - developer/admin：查看所有申请
    - supervisor：查看待审批的申请
    - operator：查看自己提交的申请
    """
    pass

@router.get("/api/approval/account-registration/{registration_id}/flow")
async def get_approval_flow(
    registration_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取审批流程详情（电子流可视化）
    
    返回：
    {
        "registration_id": 1,
        "steps": [
            {
                "step_number": 1,
                "step_name": "提交申请",
                "status": "approved",
                "approver": {"id": 1, "name": "张三"},
                "approved_at": "2025-11-01 10:00:00",
                "comment": "申请信息完整"
            },
            ...
        ],
        "current_step": 2,
        "can_approve": true
    }
    """
    pass

@router.post("/api/approval/account-registration/{registration_id}/approve")
async def approve_registration(
    registration_id: int,
    approval: ApprovalAction,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    审批账号注册申请
    
    权限：admin/supervisor（根据当前步骤）
    
    请求体：
    {
        "action": "approve",  # approve/reject
        "comment": "审批意见"
    }
    """
    pass
```

---

## 🚀 实施计划

### Phase 1: 用户管理系统（1-2周）
1. ✅ 数据库表设计（Users、Roles、Permissions）
2. ✅ 后端API开发（用户CRUD、权限验证）
3. ✅ 前端界面开发（用户列表、角色管理）
4. ✅ 权限中间件开发（JWT Token、角色验证）

### Phase 2: 审批流程系统（1-2周）
1. ✅ 数据库表设计（AccountRegistration、ApprovalWorkflow）
2. ✅ 后端API开发（审批流程、电子流API）
3. ✅ 前端界面开发（审批流程可视化、审批操作）

### Phase 3: 数据看板系统（2-3周）
1. ✅ 后端API开发（看板数据API）
2. ✅ 前端组件开发（KPI卡片、图表组件）
3. ✅ 看板页面开发（销售、库存、财务等）
4. ✅ 实时数据同步（WebSocket）

### Phase 4: 测试和优化（1周）
1. ✅ 单元测试
2. ✅ 集成测试
3. ✅ 性能优化
4. ✅ 用户验收测试

---

## 📚 相关文档

- [企业级ERP开发标准](.cursorrules)
- [API设计规范](docs/DEVELOPMENT_RULES/API_DESIGN.md)
- [安全规范](docs/DEVELOPMENT_RULES/SECURITY.md)
- [数据库设计规范](docs/DEVELOPMENT_RULES/DATABASE_DESIGN.md)

---

**规划完成时间**: 2025-11-01  
**预计开始时间**: 2025-11-02  
**预计完成时间**: 2025-11-30

