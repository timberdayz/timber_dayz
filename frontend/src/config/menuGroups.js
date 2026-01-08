/**
 * 菜单分组配置
 * 企业级ERP标准菜单结构 - 完整版
 * 版本: v4.9.0
 * 对标: SAP、Oracle、金蝶、用友
 * 
 * v4.9.0更新：
 * - TopN产品排行（销售与分析）
 * - 库存健康仪表盘（产品与库存）
 * - 产品质量仪表盘（产品与库存）
 */

export const menuGroups = [
  {
    id: 'workspace',
    title: '工作台',
    icon: 'DataBoard',
    order: 1,
    defaultExpanded: true,
    items: [
      '/business-overview'
    ]
  },
  {
    id: 'data-collection',
    title: '数据采集与管理',
    icon: 'Connection',
    order: 2,
    defaultExpanded: true,
    badge: 'core',  // 核心功能标识
    items: [
      '/collection-config',      // 采集配置
      '/collection-tasks',       // 采集任务
      '/collection-history',     // 采集历史
      '/component-recorder',     // ⭐ Phase 8.1: 组件录制工具（UI化录制）
      '/component-versions',     // ⭐ Phase 9.4: 组件版本管理（A/B测试、快速回滚）
      // ⭐ v4.6.0 DSS架构重构：新增数据同步菜单项（完全替代字段映射审核）
      '/data-sync/files',        // 数据同步 - 文件列表
      '/data-sync/tasks',        // 数据同步 - 同步任务
      '/data-sync/history',      // 数据同步 - 同步历史
      '/data-sync/templates',    // 数据同步 - 模板管理
      '/data-quarantine',        // 数据隔离区
      // ⚠️ v4.12.0移除：数据浏览器功能已移除，使用Metabase替代（http://localhost:8080）
      // '/data-browser',           // 数据浏览器
      '/data-consistency'        // v4.11.5: 数据一致性验证
    ]
  },
  {
    id: 'product-inventory',
    title: '产品与库存',
    icon: 'Box',
    order: 3,
    defaultExpanded: true,
    items: [
      '/inventory-management',   // 库存管理（v4.10.0融合：产品管理+库存看板）
      '/inventory-dashboard-v3', // 库存看板
      '/inventory-health',       // v4.9.0: 库存健康仪表盘
      '/product-quality'         // v4.9.0: 产品质量仪表盘
    ]
  },
  {
    id: 'procurement',
    title: '采购管理',
    icon: 'ShoppingCart',
    order: 4,
    defaultExpanded: false,
    items: [
      '/purchase-orders',        // 采购订单（PO）
      '/grn-management',         // 入库单（GRN）
      '/vendor-management',      // 供应商管理
      '/invoice-management'      // 发票管理
    ]
  },
  {
    id: 'sales-analytics',
    title: '销售与分析',
    icon: 'TrendCharts',
    order: 5,
    defaultExpanded: true,
    items: [
      '/sales-dashboard-v3',        // 销售看板（v3版本）
      '/sales-campaign-management',  // 销售战役管理（A类数据）
      '/target-management',          // 目标管理（A类数据）
      '/customer-management',        // 客户管理
      '/order-management'            // 订单管理
      // 废弃路由（功能已合并到销售看板）：
      // '/sales-analysis', '/top-products', '/sales-trend'
    ]
  },
  {
    id: 'finance',
    title: '财务管理',
    icon: 'Money',
    order: 6,
    defaultExpanded: true,
    items: [
      '/financial-overview',     // v4.9.1: 财务总览
      '/financial-management',   // 应收应付
      '/expense-management',     // 费用管理
      '/finance-reports',        // 财务报表
      '/fx-management',          // 汇率管理
      '/fiscal-periods'          // 会计期间
    ]
  },
  {
    id: 'store-operations',
    title: '店铺运营',
    icon: 'Shop',
    order: 7,
    defaultExpanded: false,
    items: [
      '/store-management',       // 店铺管理
      '/store-analytics',        // 店铺分析
      '/account-management',     // 账号管理
      '/account-alignment'       // 账号对齐
    ]
  },
  {
    id: 'reports',
    title: '报表中心',
    icon: 'Document',
    order: 8,
    defaultExpanded: false,
    items: [
      '/sales-reports',          // 销售报表
      '/inventory-reports',      // 库存报表
      '/finance-reports-detail', // 财务报表（P&L）
      '/vendor-reports',         // 供应商报表
      '/custom-reports'          // 自定义报表
    ]
  },
  {
    id: 'human-resources',
    title: '人力资源',
    icon: 'User',
    order: 9,
    defaultExpanded: false,
    items: [
      '/human-resources',            // 人力管理
      '/employee-management',        // 员工档案
      '/attendance-management',      // 考勤管理
      '/hr-performance-management'  // 绩效管理
    ]
  },
  {
    id: 'approval',
    title: '审批中心',
    icon: 'Check',
    order: 10,
    defaultExpanded: false,
    items: [
      '/my-tasks',              // 我的待办
      '/my-requests',           // 我的申请
      '/approval-history',      // 审批历史
      '/workflow-config'        // 流程配置（仅管理员）
    ]
  },
  {
    id: 'messages',
    title: '消息中心',
    icon: 'Bell',
    order: 11,
    defaultExpanded: false,
    badge: 'new',  // 新消息标识
    items: [
      '/system-notifications',   // 系统通知
      '/alerts',                 // 预警提醒
      '/message-settings'        // 消息设置
    ]
  },
  {
    id: 'system',
    title: '系统管理',
    icon: 'Setting',
    order: 12,
    defaultExpanded: false,
    items: [
      '/user-management',        // 用户管理
      '/role-management',        // 角色管理
      '/permission-management',  // 权限管理
      '/system-config',          // 系统配置
      '/database-config',        // 数据库配置
      '/security-settings',      // 安全设置
      '/system-logs',            // 系统日志
      '/data-backup',            // 数据备份
      '/system-maintenance',     // 系统维护
      '/notification-config',    // 通知配置
      '/personal-settings'       // 个人设置
    ]
  },
  {
    id: 'help',
    title: '帮助中心',
    icon: 'QuestionFilled',
    order: 13,
    defaultExpanded: false,
    items: [
      '/user-guide',             // 操作指南
      '/video-tutorials',        // 视频教程
      '/faq'                     // 常见问题
    ]
  },
  {
    id: 'dev-tools',
    title: '开发工具',
    icon: 'Tools',
    order: 99,
    defaultExpanded: false,
    devOnly: true,  // 仅开发环境显示
    items: [
      '/debug',
      '/test',
      '/ultra-simple',
      '/api-docs'                // API文档
    ]
  }
]

/**
 * 路由显示名称映射（用于统一管理）
 */
export const routeDisplayNames = {
  // 旧路由 → 新显示名称
  '/sales-dashboard': '销售看板',
  '/sales-dashboard-v3': '销售看板',
  '/sales-campaign-management': '销售战役管理',
  '/hr-performance-management': '绩效管理',
  '/target-management': '目标管理',
  '/inventory-dashboard-v3': '库存看板',
  // ⚠️ v4.12.0移除：数据浏览器功能已移除，使用Metabase替代
  // '/data-browser': '数据浏览器',
  '/financial-management': '应收应付',  // 重命名
  // ⭐ v4.6.0新增：数据同步路由显示名称
  '/data-sync/files': '文件列表',
  '/data-sync/tasks': '同步任务',
  '/data-sync/history': '同步历史',
  '/data-sync/templates': '模板管理',
  // ⭐ Phase 8.1新增：组件录制工具
  '/component-recorder': '组件录制工具',
  // ⭐ Phase 9.4新增：组件版本管理
  '/component-versions': '组件版本管理'
}

/**
 * 废弃路由（不在菜单中显示）
 */
export const deprecatedRoutes = [
  '/sales-dashboard',  // 旧版销售看板，被v3替代
  '/sales-analysis',   // 销售分析（功能已合并到销售看板）
  '/top-products',      // TopN产品排行（功能已合并到销售看板）
  '/sales-trend'        // 销售趋势分析（功能已合并到销售看板）
]
