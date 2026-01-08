/**
 * Vue Router配置 - 现代化路由管理
 */

import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/',
    redirect: '/business-overview'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: {
      title: '登录',
      public: true
    }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: {
      title: '注册',
      public: true
    }
  },
  {
    path: '/admin/users/pending',
    name: 'UserApproval',
    component: () => import('../views/admin/UserApproval.vue'),
    meta: {
      title: '用户审批',
      icon: 'User',
      permission: 'user-management',
      roles: ['admin']
    }
  },
  {
    path: '/ultra-simple',
    name: 'UltraSimple',
    component: () => import('../views/UltraSimplePage.vue'),
    meta: {
      title: '超简化页面',
      icon: 'Setting',
      permission: null,
      roles: []
    }
  },
  {
    path: '/test',
    name: 'Test',
    component: () => import('../views/TestPage.vue'),
    meta: {
      title: '测试页面',
      icon: 'Setting',
      permission: null,
      roles: []
    }
  },
  {
    path: '/business-overview',
    name: 'BusinessOverview',
    component: () => import('../views/BusinessOverview.vue'),  // v4.11.0: 使用重构后的业务概览页面
    meta: {
      title: '业务概览',
      icon: 'DataBoard',
      permission: 'business-overview',
      roles: ['admin', 'manager', 'operator']
    }
  },
  {
    path: '/sales-analysis',
    name: 'SalesAnalysis',
    component: () => import('../views/SalesAnalysis.vue'),
    meta: {
      title: '销售分析',
      icon: 'TrendCharts',
      permission: 'sales-analysis',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/sales-dashboard',
    name: 'SalesDashboard',
    component: () => import('../views/SalesDashboard.vue'),
    meta: {
      title: '销售看板',
      icon: 'DataAnalysis',
      permission: 'sales-dashboard',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/sales/order-management',
    name: 'OrderManagement',
    component: () => import('../views/sales/OrderManagement.vue'),
    meta: {
      title: '订单管理',
      icon: 'Document',
      permission: 'order-management',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/sales/sales-detail-by-product',
    name: 'SalesDetailByProduct',
    component: () => import('../views/sales/SalesDetailByProduct.vue'),
    meta: {
      title: '销售明细（产品ID级别）',
      icon: 'List',
      permission: 'sales-detail',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/inventory-management',
    name: 'InventoryManagement',
    component: () => import('../views/InventoryManagement.vue'),
    meta: {
      title: '库存管理',
      icon: 'Box',
      permission: 'inventory-management',
      roles: ['admin', 'manager', 'operator', 'inventory']
    }
  },
  {
    path: '/human-resources',
    name: 'HumanResources',
    component: () => import('../views/HumanResources.vue'),
    meta: {
      title: '人力管理',
      icon: 'User',
      permission: 'human-resources',
      roles: ['admin', 'manager', 'operator']
    }
  },
  {
    path: '/financial-management',
    name: 'FinancialManagement',
    component: () => import('../views/FinancialManagement.vue'),
    meta: {
      title: '财务管理',
      icon: 'Money',
      permission: 'financial-management',
      roles: ['admin', 'manager', 'finance']
    }
  },
  {
    path: '/store-management',
    name: 'StoreManagement',
    component: () => import('../views/StoreManagement.vue'),
    meta: {
      title: '店铺管理',
      icon: 'Shop',
      permission: 'store-management',
      roles: ['admin', 'manager', 'operator']
    }
  },
  {
    path: '/system-config',
    name: 'SystemConfig',
    component: () => import('../views/system/SystemConfig.vue'),
    meta: {
      title: '系统配置',
      icon: 'Setting',
      permission: 'system-settings',
      roles: ['admin']
    }
  },
  {
    path: '/database-config',
    name: 'DatabaseConfig',
    component: () => import('../views/system/DatabaseConfig.vue'),
    meta: {
      title: '数据库配置',
      icon: 'Connection',
      permission: 'system-settings',
      roles: ['admin']
    }
  },
  {
    path: '/security-settings',
    name: 'SecuritySettings',
    component: () => import('../views/system/SecuritySettings.vue'),
    meta: {
      title: '安全设置',
      icon: 'Lock',
      permission: 'system-settings',
      roles: ['admin']
    }
  },
  {
    path: '/account-management',
    name: 'AccountManagement',
    component: () => import('../views/AccountManagement.vue'),
    meta: {
      title: '账号管理',
      icon: 'UserFilled',
      permission: 'account-management',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/personal-settings',
    name: 'PersonalSettings',
    component: () => import('../views/PersonalSettings.vue'),
    meta: {
      title: '个人设置',
      icon: 'Setting',
      permission: 'personal-settings',
      roles: ['admin', 'manager', 'operator']
    }
  },
  {
    path: '/settings/notifications',
    name: 'NotificationPreferences',
    component: () => import('../views/settings/NotificationPreferences.vue'),
    meta: {
      title: '通知偏好设置',
      icon: 'Bell',
      permission: null,
      roles: []
    }
  },
  {
    path: '/settings/sessions',
    name: 'Sessions',
    component: () => import('../views/settings/Sessions.vue'),
    meta: {
      title: '会话管理',
      icon: 'Monitor',
      permission: 'personal-settings',
      roles: ['admin', 'manager', 'operator']
    }
  },
  // ⭐ v4.6.0 DSS架构重构：新增数据同步路由（完全独立于字段映射审核）
  // ✅ 2026-01-08: 数据同步功能仅管理员可访问
  {
    path: '/data-sync/files',
    name: 'DataSyncFiles',
    component: () => import('../views/DataSyncFiles.vue'),
    meta: {
      title: '文件列表',
      icon: 'Document',
      permission: 'data-sync',
      roles: ['admin']  // ✅ 仅管理员可访问
    }
  },
  {
    path: '/data-sync/file-detail/:fileId',
    name: 'DataSyncFileDetail',
    component: () => import('../views/DataSyncFileDetail.vue'),
    meta: {
      title: '文件详情',
      icon: 'Document',
      permission: 'data-sync',
      roles: ['admin']  // ✅ 仅管理员可访问
    }
  },
  {
    path: '/data-sync/tasks',
    name: 'DataSyncTasks',
    component: () => import('../views/DataSyncTasks.vue'),
    meta: {
      title: '同步任务',
      icon: 'Loading',
      permission: 'data-sync',
      roles: ['admin']  // ✅ 仅管理员可访问
    }
  },
  {
    path: '/data-sync/history',
    name: 'DataSyncHistory',
    component: () => import('../views/DataSyncHistory.vue'),
    meta: {
      title: '同步历史',
      icon: 'Clock',
      permission: 'data-sync',
      roles: ['admin']  // ✅ 仅管理员可访问
    }
  },
  {
    path: '/data-sync/templates',
    name: 'DataSyncTemplates',
    component: () => import('../views/DataSyncTemplates.vue'),
    meta: {
      title: '模板管理',
      icon: 'Files',
      permission: 'data-sync',
      roles: ['admin']  // ✅ 仅管理员可访问
    }
  },
  // ⚠️ v4.12.0移除：数据浏览器功能已移除，使用Metabase替代
  // {
  //   path: '/data-browser',
  //   name: 'DataBrowser',
  //   component: () => import('../views/DataBrowser.vue'),
  //   meta: {
  //     title: '数据库浏览器',
  //     icon: 'Search',
  //     permission: 'data-governance',
  //     roles: ['admin']  // 🔒 仅管理员（可查看原始数据库）
  //   }
  // },
  {
    path: '/data-consistency',
    name: 'DataConsistency',
    component: () => import('../views/DataConsistency.vue'),  // v4.11.5: 数据一致性验证
    meta: {
      title: '数据一致性验证',
      icon: 'DocumentChecked',
      permission: 'data-governance',
      roles: ['admin']  // 🔒 仅管理员（数据质量敏感操作）
    }
  },
  {
    path: '/top-products',
    name: 'TopProducts',
    component: () => import('../views/TopProducts.vue'),  // v4.9.0: TopN产品排行
    meta: {
      title: 'TopN产品排行',
      icon: 'TrendCharts',
      permission: null,  // v4.9.0: 暂时开放访问以便演示
      roles: []
    }
  },
  {
    path: '/inventory-health',
    name: 'InventoryHealth',
    component: () => import('../views/InventoryHealthDashboard.vue'),  // v4.9.0: 库存健康
    meta: {
      title: '库存健康仪表盘',
      icon: 'Box',
      permission: null,  // v4.9.0: 暂时开放访问以便演示
      roles: []
    }
  },
  {
    path: '/product-quality',
    name: 'ProductQuality',
    component: () => import('../views/ProductQualityDashboard.vue'),  // v4.9.0: 产品质量
    meta: {
      title: '产品质量仪表盘',
      icon: 'Medal',
      permission: null,
      roles: []
    }
  },
  {
    path: '/sales-trend',
    name: 'SalesTrend',
    component: () => import('../views/SalesTrendChart.vue'),  // v4.9.1: 销售趋势
    meta: {
      title: '销售趋势分析',
      icon: 'TrendCharts',
      permission: null,
      roles: []
    }
  },
  {
    path: '/financial-overview',
    name: 'FinancialOverview',
    component: () => import('../views/FinancialOverview.vue'),  // v4.9.1: 财务总览
    meta: {
      title: '财务总览',
      icon: 'Money',
      permission: null,
      roles: []
    }
  },
  {
    path: '/data-quarantine',
    name: 'DataQuarantine',
    component: () => import('../views/DataQuarantine.vue'),
    meta: {
      title: '数据隔离区',
      icon: 'Warning',
      permission: 'data-governance',
      roles: ['admin']  // 🔒 仅管理员（数据质量控制）
    }
  },
  {
    path: '/account-alignment',
    name: 'AccountAlignment',
    component: () => import('../views/AccountAlignment.vue'),
    meta: {
      title: '账号对齐',
      icon: 'Shop',
      permission: 'account-alignment',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/sales-dashboard-v3',
    name: 'SalesDashboardV3',
    component: () => import('../views/SalesDashboard.vue'),
    meta: {
      title: '销售看板v3',
      icon: 'TrendCharts',
      permission: 'sales-dashboard',
      roles: ['admin', 'manager', 'operator']
    }
  },
  {
    path: '/inventory-dashboard-v3',
    name: 'InventoryDashboardV3',
    component: () => import('../views/InventoryDashboardSimple.vue'),  // 临时使用简化版
    meta: {
      title: '库存看板v3',
      icon: 'DataLine',
      permission: 'inventory-management',
      roles: ['admin', 'manager', 'operator']
    }
  },
  {
    path: '/user-management',
    name: 'UserManagement',
    component: () => import('../views/UserManagement.vue'),
    meta: {
      title: '用户管理',
      icon: 'UserFilled',
      permission: 'user-management',
      roles: ['admin']
    }
  },
  {
    path: '/role-management',
    name: 'RoleManagement',
    component: () => import('../views/RoleManagement.vue'),
    meta: {
      title: '角色管理',
      icon: 'Key',
      permission: 'role-management',
      roles: ['admin']
    }
  },
  {
    path: '/permission-management',
    name: 'PermissionManagement',
    component: () => import('../views/PermissionManagement.vue'),
    meta: {
      title: '权限管理',
      icon: 'Lock',
      permission: 'role-management',
      roles: ['admin']
    }
  },
  {
    path: '/target-management',
    name: 'TargetManagement',
    component: () => import('../views/target/TargetManagement.vue'),
    meta: {
      title: '目标管理',
      icon: 'Aim',
      permission: 'target:read',
      roles: ['admin']  // ✅ 仅管理员可访问
    }
  },
  // ============================================================================
  // Phase 3: A类数据管理路由（销售目标、战役目标、经营成本）
  // ============================================================================
  {
    path: '/config/sales-targets',
    name: 'SalesTargetManagement',
    component: () => import('../views/config/SalesTargetManagement.vue'),
    meta: {
      title: '销售目标配置',
      icon: 'Histogram',
      permission: 'config:sales-targets',
      roles: ['admin']  // ✅ 仅管理员可访问
    }
  },
  {
    path: '/debug',
    name: 'Debug',
    component: () => import('../views/Debug.vue'),
    meta: {
      title: '调试信息',
      icon: 'Setting',
      permission: null,
      roles: []
    }
  },
  {
    path: '/test',
    name: 'Test',
    component: () => import('../views/Test.vue'),
    meta: {
      title: '测试页面',
      icon: 'Setting',
      permission: null,
      roles: []
    }
  },
  
  // ==================== 数据采集中心 ====================
  {
    path: '/collection-config',
    name: 'CollectionConfig',
    component: () => import('../views/collection/CollectionConfig.vue'),
    meta: {
      title: '采集配置',
      icon: 'Setting',
      permission: 'collection-config',
      roles: ['admin']
    }
  },
  {
    path: '/collection-tasks',
    name: 'CollectionTasks',
    component: () => import('../views/collection/CollectionTasks.vue'),
    meta: {
      title: '采集任务',
      icon: 'List',
      permission: 'collection-tasks',
      roles: ['admin']
    }
  },
  {
    path: '/collection-history',
    name: 'CollectionHistory',
    component: () => import('../views/collection/CollectionHistory.vue'),
    meta: {
      title: '采集历史',
      icon: 'Clock',
      permission: 'collection-history',
      roles: ['admin']
    }
  },
  {
    path: '/component-recorder',
    name: 'ComponentRecorder',
    component: () => import('../views/ComponentRecorder.vue'),
    meta: {
      title: '组件录制工具',
      icon: 'VideoPlay',
      permission: 'component-recorder',
      roles: ['admin']
    }
  },
  {
    path: '/component-versions',
    name: 'ComponentVersions',
    component: () => import('../views/ComponentVersions.vue'),
    meta: {
      title: '组件版本管理',
      icon: 'Files',
      permission: 'component-versions',
      roles: ['admin']
    }
  },
  
  // ==================== 采购管理 ====================
  {
    path: '/purchase-orders',
    name: 'PurchaseOrders',
    component: () => import('../views/procurement/PurchaseOrders.vue'),
    meta: {
      title: '采购订单',
      icon: 'Document',
      permission: 'purchase-orders',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/grn-management',
    name: 'GRNManagement',
    component: () => import('../views/procurement/GRNManagement.vue'),
    meta: {
      title: '入库单',
      icon: 'Box',
      permission: 'grn-management',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/vendor-management',
    name: 'VendorManagement',
    component: () => import('../views/procurement/VendorManagement.vue'),
    meta: {
      title: '供应商管理',
      icon: 'OfficeBuilding',
      permission: 'vendor-management',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/invoice-management',
    name: 'InvoiceManagement',
    component: () => import('../views/procurement/InvoiceManagement.vue'),
    meta: {
      title: '发票管理',
      icon: 'Document',
      permission: 'invoice-management',
      roles: ['admin', 'manager', 'finance']
    }
  },
  
  // ==================== 销售扩展 ====================
  {
    path: '/customer-management',
    name: 'CustomerManagement',
    component: () => import('../views/sales/CustomerManagement.vue'),
    meta: {
      title: '客户管理',
      icon: 'UserFilled',
      permission: 'customer-management',
      roles: ['admin', 'manager', 'operator']
    }
  },
  {
    path: '/order-management',
    name: 'OrderManagement',
    component: () => import('../views/sales/OrderManagement.vue'),
    meta: {
      title: '订单管理',
      icon: 'Document',
      permission: 'order-management',
      roles: ['admin', 'manager', 'operator']
    }
  },
  {
    path: '/sales-campaign-management',
    name: 'SalesCampaignManagement',
    component: () => import('../views/sales/CampaignManagement.vue'),
    meta: {
      title: '销售战役管理',
      icon: 'Trophy',
      permission: 'campaign:read',
      roles: ['admin', 'manager', 'operator']
    }
  },
  
  // ==================== 财务扩展 ====================
  {
    path: '/expense-management',
    name: 'ExpenseManagement',
    component: () => import('../views/finance/ExpenseManagement.vue'),
    meta: {
      title: '费用管理',
      icon: 'Wallet',
      permission: 'expense-management',
      roles: ['admin', 'manager', 'finance']
    }
  },
  {
    path: '/finance-reports',
    name: 'FinanceReports',
    component: () => import('../views/finance/FinanceReports.vue'),
    meta: {
      title: '财务报表',
      icon: 'Document',
      permission: 'finance-reports',
      roles: ['admin', 'manager', 'finance']
    }
  },
  {
    path: '/fx-management',
    name: 'FXManagement',
    component: () => import('../views/finance/FXManagement.vue'),
    meta: {
      title: '汇率管理',
      icon: 'Money',
      permission: 'fx-management',
      roles: ['admin']
    }
  },
  {
    path: '/fiscal-periods',
    name: 'FiscalPeriods',
    component: () => import('../views/finance/FiscalPeriods.vue'),
    meta: {
      title: '会计期间',
      icon: 'Calendar',
      permission: 'fiscal-periods',
      roles: ['admin', 'finance']
    }
  },
  
  // ==================== 店铺扩展 ====================
  {
    path: '/store-analytics',
    name: 'StoreAnalytics',
    component: () => import('../views/store/StoreAnalytics.vue'),
    meta: {
      title: '店铺分析',
      icon: 'DataAnalysis',
      permission: 'store-analytics',
      roles: ['admin', 'manager']
    }
  },
  
  // ==================== 报表中心 ====================
  {
    path: '/sales-reports',
    name: 'SalesReports',
    component: () => import('../views/reports/SalesReports.vue'),
    meta: {
      title: '销售报表',
      icon: 'Document',
      permission: 'sales-reports',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/inventory-reports',
    name: 'InventoryReports',
    component: () => import('../views/reports/InventoryReports.vue'),
    meta: {
      title: '库存报表',
      icon: 'Document',
      permission: 'inventory-reports',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/finance-reports-detail',
    name: 'FinanceReportsDetail',
    component: () => import('../views/reports/FinanceReportsDetail.vue'),
    meta: {
      title: '财务报表详情',
      icon: 'Document',
      permission: 'finance-reports-detail',
      roles: ['admin', 'finance']
    }
  },
  {
    path: '/vendor-reports',
    name: 'VendorReports',
    component: () => import('../views/reports/VendorReports.vue'),
    meta: {
      title: '供应商报表',
      icon: 'Document',
      permission: 'vendor-reports',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/custom-reports',
    name: 'CustomReports',
    component: () => import('../views/reports/CustomReports.vue'),
    meta: {
      title: '自定义报表',
      icon: 'Document',
      permission: 'custom-reports',
      roles: ['admin']
    }
  },
  
  // ==================== 人力资源扩展 ====================
  {
    path: '/employee-management',
    name: 'EmployeeManagement',
    component: () => import('../views/hr/EmployeeManagement.vue'),
    meta: {
      title: '员工档案',
      icon: 'UserFilled',
      permission: 'employee-management',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/attendance-management',
    name: 'AttendanceManagement',
    component: () => import('../views/hr/AttendanceManagement.vue'),
    meta: {
      title: '考勤管理',
      icon: 'Clock',
      permission: 'attendance-management',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/hr-performance-management',
    name: 'HRPerformanceManagement',
    component: () => import('../views/hr/PerformanceManagement.vue'),
    meta: {
      title: '绩效管理',
      icon: 'Medal',
      permission: 'performance:read',
      roles: ['admin', 'manager', 'operator']
    }
  },
  
  // ==================== 审批中心 ====================
  {
    path: '/my-tasks',
    name: 'MyTasks',
    component: () => import('../views/approval/MyTasks.vue'),
    meta: {
      title: '我的待办',
      icon: 'List',
      permission: 'my-tasks',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/my-requests',
    name: 'MyRequests',
    component: () => import('../views/approval/MyRequests.vue'),
    meta: {
      title: '我的申请',
      icon: 'Document',
      permission: 'my-requests',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/approval-history',
    name: 'ApprovalHistory',
    component: () => import('../views/approval/ApprovalHistory.vue'),
    meta: {
      title: '审批历史',
      icon: 'Clock',
      permission: 'approval-history',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/workflow-config',
    name: 'WorkflowConfig',
    component: () => import('../views/approval/WorkflowConfig.vue'),
    meta: {
      title: '流程配置',
      icon: 'Setting',
      permission: 'workflow-config',
      roles: ['admin']
    }
  },
  
  // ==================== 消息中心 ====================
  {
    path: '/system-notifications',
    name: 'SystemNotifications',
    component: () => import('../views/messages/SystemNotifications.vue'),
    meta: {
      title: '系统通知',
      icon: 'Bell',
      permission: 'notifications',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/alerts',
    name: 'Alerts',
    component: () => import('../views/messages/Alerts.vue'),
    meta: {
      title: '预警提醒',
      icon: 'Warning',
      permission: 'alerts',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/message-settings',
    name: 'MessageSettings',
    component: () => import('../views/messages/MessageSettings.vue'),
    meta: {
      title: '消息设置',
      icon: 'Setting',
      permission: 'message-settings',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  
  // ==================== 系统管理扩展 ====================
  {
    path: '/system-logs',
    name: 'SystemLogs',
    component: () => import('../views/system/SystemLogs.vue'),
    meta: {
      title: '系统日志',
      icon: 'Document',
      permission: 'system-logs',
      roles: ['admin']
    }
  },
  {
    path: '/data-backup',
    name: 'DataBackup',
    component: () => import('../views/system/DataBackup.vue'),
    meta: {
      title: '数据备份',
      icon: 'Folder',
      permission: 'system-settings',
      roles: ['admin']
    }
  },
  {
    path: '/system-maintenance',
    name: 'SystemMaintenance',
    component: () => import('../views/system/SystemMaintenance.vue'),
    meta: {
      title: '系统维护',
      icon: 'Tools',
      permission: 'system-settings',
      roles: ['admin']
    }
  },
  {
    path: '/notification-config',
    name: 'NotificationConfig',
    component: () => import('../views/system/NotificationConfig.vue'),
    meta: {
      title: '通知配置',
      icon: 'Bell',
      permission: 'system-settings',
      roles: ['admin']
    }
  },
  
  // ==================== 帮助中心 ====================
  {
    path: '/user-guide',
    name: 'UserGuide',
    component: () => import('../views/help/UserGuide.vue'),
    meta: {
      title: '操作指南',
      icon: 'Reading',
      permission: 'help-center',
      roles: []  // 所有人可见
    }
  },
  {
    path: '/video-tutorials',
    name: 'VideoTutorials',
    component: () => import('../views/help/VideoTutorials.vue'),
    meta: {
      title: '视频教程',
      icon: 'VideoPlay',
      permission: 'help-center',
      roles: []  // 所有人可见
    }
  },
  {
    path: '/faq',
    name: 'FAQ',
    component: () => import('../views/help/FAQ.vue'),
    meta: {
      title: '常见问题',
      icon: 'QuestionFilled',
      permission: 'help-center',
      roles: []  // 所有人可见
    }
  },
  
  // ==================== 开发工具扩展 ====================
  {
    path: '/api-docs',
    name: 'APIDocs',
    component: () => import('../views/dev/APIDocs.vue'),
    meta: {
      title: 'API文档',
      icon: 'Document',
      permission: null,
      roles: []
    }
  },
  
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    redirect: '/business-overview'
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    } else {
      return { top: 0 }
    }
  }
})

// 🔒 路由守卫 - 严格权限控制（开发和生产环境一致）
router.beforeEach((to, from, next) => {
  // ⭐ v4.19.0: 统一使用 useAuthStore（功能更完整）
  const authStore = useAuthStore()
  const userStore = useUserStore()
  
  // 设置页面标题
  document.title = to.meta.title ? `${to.meta.title} - 西虹ERP系统` : '西虹ERP系统'
  
  // ⭐ v4.19.0: 定义公开路由（不需要登录）
  const publicRoutes = ['/login', '/register']
  const isPublicRoute = publicRoutes.includes(to.path) || to.meta?.public
  
  // ⭐ v4.19.5 修复：改进登录状态检查逻辑
  // 优先检查 authStore，如果未初始化则检查 localStorage
  let isLoggedIn = authStore.isLoggedIn
  
  if (!isLoggedIn) {
    // 降级：检查 localStorage 中的 token
    const savedToken = localStorage.getItem('access_token')
    if (savedToken && savedToken.length > 0) {
      // 如果有 token 但没有用户信息，尝试恢复
      if (!authStore.user) {
        authStore.initAuth()
      }
      isLoggedIn = true
    }
  }
  
  // 最后检查 userStore（向后兼容）
  if (!isLoggedIn) {
    isLoggedIn = userStore.token && userStore.token.length > 0
  }
  
  // ⭐ v4.19.0: 如果已登录，访问公开路由应该重定向到默认页面
  if (isLoggedIn && isPublicRoute) {
    next('/business-overview')
    return
  }
  
  // ⭐ v4.19.0: 检查是否已登录
  if (!isLoggedIn) {
    // 如果是公开路由，允许访问
    if (isPublicRoute) {
      next()
      return
    }
    // 否则重定向到登录页面，保存原始路径用于登录后重定向
    next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
    return
  }
  
  // ⭐ Phase 8.1修复: 检查是否为管理员（管理员拥有所有权限）
  // ⭐ v4.19.0: 使用userStore.hasRole（保持现有逻辑，避免破坏现有功能）
  const isAdmin = userStore.hasRole(['admin'])
  
  // ✅ 权限检查（管理员跳过，符合RBAC标准）
  if (!isAdmin && to.meta.permission) {
      if (!userStore.hasPermission(to.meta.permission)) {
      console.warn(`[权限拦截] 缺少权限: ${to.meta.permission}`)
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/b19377c4-4cc0-48a0-b4b5-1a0a5b6ad0ac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'router/index.js:879',message:'Permission check FAILED - redirecting',data:{permission:to.meta.permission},timestamp:Date.now(),sessionId:'debug-session',hypothesisId:'H2'})}).catch(()=>{});
      // #endregion
        next('/business-overview')
        return
    }
  }
  
  // ✅ 角色权限检查（所有人都需要检查角色）
  if (to.meta.roles && to.meta.roles.length > 0) {
      if (!userStore.hasRole(to.meta.roles)) {
      console.warn(`[权限拦截] 角色不匹配，需要: ${to.meta.roles.join(', ')}`)
        next('/business-overview')
        return
    }
  }
  
  next()
})

export default router