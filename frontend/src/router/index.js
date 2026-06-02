/**
 * Vue Router配置 - 现代化路由管理
 */

import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useAuthStore } from '@/stores/auth'
import {
  hasPersistedAuthSession,
  readPersistedAuthState,
} from '@/utils/authSession'

const routes = [
  {
    path: '/',
    redirect: '/business-overview'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/domains/platform/views/Login.vue'),
    meta: {
      title: '登录',
      public: true
    }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/domains/platform/views/Register.vue'),
    meta: {
      title: '注册',
      public: true
    }
  },
  {
    path: '/admin/users/pending',
    name: 'UserApproval',
    component: () => import('@/domains/platform/views/admin/UserApproval.vue'),
    meta: {
      title: '用户审批',
      icon: 'User',
      permission: 'user-management',
      roles: ['admin']
    }
  },
  {
    path: '/my-tasks/:taskId',
    name: 'TaskDetail',
    component: () => import('@/domains/platform/views/approval/TaskDetail.vue'),
    meta: {
      title: '任务详情',
      icon: 'List',
      permission: 'my-tasks',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/ultra-simple',
    name: 'UltraSimple',
    component: () => import('@/domains/platform/views/UltraSimplePage.vue'),
    meta: {
      title: '超简化页面',
      icon: 'Setting',
      permission: 'system-settings',
      roles: ['admin']
    }
  },
  {
    path: '/business-overview',
    name: 'BusinessOverview',
    component: () => import('@/domains/business/views/BusinessOverview.vue'),  // v4.11.0: 使用重构后的业务概览页面
    meta: {
      title: '业务概览',
      icon: 'DataBoard',
      permission: 'business-overview',
      roles: ['admin', 'manager', 'operator', 'finance', 'tourist', 'investor']
    }
  },
  {
    path: '/sales/order-management',
    name: 'OrderManagement',
    component: () => import('@/domains/business/views/sales/OrderManagement.vue'),
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
    component: () => import('@/domains/business/views/sales/SalesDetailByProduct.vue'),
    meta: {
      title: '销售明细（产品ID级别）',
      icon: 'List',
      permission: 'sales-detail',
      roles: ['admin']
    }
  },
  {
    path: '/human-resources',
    name: 'HumanResources',
    component: () => import('@/domains/business/views/HumanResources.vue'),
    meta: {
      title: '人力管理',
      icon: 'User',
      permission: 'human-resources',
      roles: ['admin']
    }
  },
  {
    path: '/financial-management',
    name: 'FinancialManagement',
    component: () => import('@/domains/business/views/FinancialManagement.vue'),
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
    component: () => import('@/domains/business/views/StoreManagement.vue'),
    meta: {
      title: '店铺管理',
      icon: 'Shop',
      permission: 'store-management',
      roles: ['admin']
    }
  },
  {
    path: '/system-config',
    name: 'SystemConfig',
    component: () => import('@/domains/platform/views/system/SystemConfig.vue'),
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
    component: () => import('@/domains/platform/views/system/DatabaseConfig.vue'),
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
    component: () => import('@/domains/platform/views/system/SecuritySettings.vue'),
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
    component: () => import('@/domains/platform/views/AccountManagement.vue'),
    meta: {
      title: '账号管理',
      icon: 'UserFilled',
      permission: 'account-management',
      roles: ['admin']
    }
  },
  {
    path: '/personal-settings',
    name: 'PersonalSettings',
    component: () => import('@/domains/platform/views/PersonalSettings.vue'),
    meta: {
      title: '个人设置',
      icon: 'Setting',
      permission: 'personal-settings',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/settings/notifications',
    name: 'NotificationPreferences',
    component: () => import('@/domains/platform/views/settings/NotificationPreferences.vue'),
    meta: {
      title: '通知偏好设置',
      icon: 'Bell',
      permission: 'personal-settings',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/settings/sessions',
    name: 'Sessions',
    component: () => import('@/domains/platform/views/settings/Sessions.vue'),
    meta: {
      title: '会话管理',
      icon: 'Monitor',
      permission: 'personal-settings',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  // ⭐ v4.6.0 DSS架构重构：新增数据同步路由（完全独立于字段映射审核）
  // ✅ 2026-01-08: 数据同步功能仅管理员可访问
  {
    path: '/data-sync/files',
    name: 'DataSyncFiles',
    component: () => import('@/domains/data_platform/views/DataSyncFiles.vue'),
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
    component: () => import('@/domains/data_platform/views/DataSyncFileDetail.vue'),
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
    component: () => import('@/domains/data_platform/views/DataSyncTasks.vue'),
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
    component: () => import('@/domains/data_platform/views/DataSyncHistory.vue'),
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
    component: () => import('@/domains/data_platform/views/DataSyncTemplates.vue'),
    meta: {
      title: '模板管理',
      icon: 'Files',
      permission: 'data-sync',
      roles: ['admin']  // ✅ 仅管理员可访问
    }
  },
  {
    path: '/data-sync/refresh-queue',
    name: 'DataSyncRefreshQueue',
    component: () => import('@/domains/data_platform/views/DataSyncRefreshQueue.vue'),
    meta: {
      title: '刷新队列',
      icon: 'Refresh',
      permission: 'data-sync',
      roles: ['admin']
    }
  },
  {
    path: '/cloud-sync',
    name: 'CloudSyncManagement',
    component: () => import('@/domains/data_platform/views/CloudSyncManagement.vue'),
    meta: {
      title: 'B类云端追平',
      icon: 'Connection',
      permission: 'data-sync',
      roles: ['admin']
    }
  },
  {
    path: '/data-consistency',
    name: 'DataConsistency',
    component: () => import('@/domains/data_platform/views/DataConsistency.vue'),  // v4.11.5: 数据一致性验证
    meta: {
      title: '数据一致性验证',
      icon: 'DocumentChecked',
      permission: 'data-governance',
      roles: ['admin']  // 🔒 仅管理员（数据质量敏感操作）
    }
  },
  {
    path: '/financial-overview',
    name: 'FinancialOverview',
    redirect: '/financial-management',
    meta: {
      title: '??????',
      icon: 'Money',
      permission: 'financial-management',
      roles: ['admin', 'manager', 'finance']
    }
  },
  {
    path: '/data-quarantine',
    name: 'DataQuarantine',
    component: () => import('@/domains/data_platform/views/DataQuarantine.vue'),
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
    component: () => import('@/domains/business/views/AccountAlignment.vue'),
    meta: {
      title: '账号对齐',
      icon: 'Shop',
      permission: 'account-alignment',
      roles: ['admin']
    }
  },
  {
    path: '/sales-dashboard-v3',
    name: 'SalesDashboardV3',
    component: () => import('@/domains/business/views/SalesDashboard.vue'),
    meta: {
      title: '销售看板v3',
      icon: 'TrendCharts',
      permission: 'sales-dashboard',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/user-management',
    name: 'UserManagement',
    component: () => import('@/domains/platform/views/UserManagement.vue'),
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
    component: () => import('@/domains/platform/views/RoleManagement.vue'),
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
    component: () => import('@/domains/platform/views/PermissionManagement.vue'),
    meta: {
      title: '权限管理',
      icon: 'Lock',
      permission: 'permission-management',
      roles: ['admin']
    }
  },
  {
    path: '/target-management',
    redirect: '/target-management/shop'
  },
  {
    path: '/target-management/shop',
    name: 'TargetManagementShop',
    component: () => import('@/domains/business/views/target/TargetManagement.vue'),
    meta: {
      title: '??????',
      icon: 'Aim',
      permission: 'target:read',
      roles: ['admin']
    }
  },
  {
    path: '/target-management/person',
    name: 'TargetManagementPerson',
    component: () => import('@/domains/business/views/target/TargetPersonManagement.vue'),
    meta: {
      title: '??????',
      icon: 'Aim',
      permission: 'target:read',
      roles: ['admin']
    }
  },
  {
    path: '/target-management/operation',
    name: 'TargetManagementOperation',
    component: () => import('@/domains/business/views/target/TargetOperationManagement.vue'),
    meta: {
      title: '??????',
      icon: 'Aim',
      permission: 'target:read',
      roles: ['admin']
    }
  },
  // ============================================================================
  // Phase 3: A类数据管理路由（销售目标、战役目标、经营成本）
  // ============================================================================
  {
    path: '/config/sales-targets',
    name: 'SalesTargetManagement',
    component: () => import('@/domains/business/views/config/SalesTargetManagement.vue'),
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
    component: () => import('@/domains/platform/views/Debug.vue'),
    meta: {
      title: '调试信息',
      icon: 'Setting',
      permission: 'system-settings',
      roles: ['admin']
    }
  },
  {
    path: '/test',
    name: 'Test',
    component: () => import('@/domains/business/views/Test.vue'),
    meta: {
      title: '测试页面',
      icon: 'Setting',
      permission: 'system-settings',
      roles: ['admin']
    }
  },
  
  // ==================== 数据采集中心 ====================
  {
    path: '/collection-config',
    name: 'CollectionConfig',
    component: () => import('@/domains/collection/views/collection/CollectionConfig.vue'),
    meta: {
      title: '采集配置',
      icon: 'Setting',
      permission: 'collection-config',
      roles: ['admin']
    }
  },
  {
    path: '/collection-coverage-audit',
    name: 'CollectionCoverageAudit',
    component: () => import('@/domains/collection/views/collection/CollectionCoverageAudit.vue'),
    meta: {
      title: '采集覆盖率巡检',
      icon: 'DataLine',
      permission: 'collection-coverage-audit',
      roles: ['admin']
    }
  },
  {
    path: '/collection-tasks',
    name: 'CollectionTasks',
    component: () => import('@/domains/collection/views/collection/CollectionTasks.vue'),
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
    component: () => import('@/domains/collection/views/collection/CollectionHistory.vue'),
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
    component: () => import('@/domains/collection/views/ComponentRecorder.vue'),
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
    component: () => import('@/domains/collection/views/ComponentVersions.vue'),
    meta: {
      title: '组件版本管理',
      icon: 'Files',
      permission: 'component-versions',
      roles: ['admin']
    }
  },
  
  // ==================== 采购管理 ====================
  
  // ==================== 销售扩展 ====================
  {
    path: '/customer-management',
    name: 'CustomerManagement',
    component: () => import('@/domains/business/views/sales/CustomerManagement.vue'),
    meta: {
      title: '客户管理',
      icon: 'UserFilled',
      permission: 'customer-management',
      roles: ['admin']
    }
  },
  {
    path: '/order-management',
    name: 'OrderManagement',
    component: () => import('@/domains/business/views/sales/OrderManagement.vue'),
    meta: {
      title: '订单管理',
      icon: 'Document',
      permission: 'order-management',
      roles: ['admin']
    }
  },
  {
    path: '/sales-campaign-management',
    name: 'SalesCampaignManagement',
    component: () => import('@/domains/business/views/sales/CampaignManagement.vue'),
    meta: {
      title: '销售战役管理',
      icon: 'Trophy',
      permission: 'campaign:read',
      roles: ['admin']
    }
  },
  
  // ==================== 财务扩展 ====================
  {
    path: '/expense-management',
    name: 'ExpenseManagement',
    component: () => import('@/domains/business/views/finance/ExpenseManagement.vue'),
    meta: {
      title: '费用管理',
      icon: 'Wallet',
      permission: 'expense-management',
      roles: ['admin', 'manager', 'finance']
    }
  },
  {
    path: '/b-cost-analysis',
    name: 'BCostAnalysis',
    component: () => import('@/domains/business/views/finance/BCostAnalysis.vue'),
    meta: {
      title: 'B类成本分析',
      icon: 'DataAnalysis',
      permission: 'b-cost-analysis',
      roles: ['admin', 'manager', 'finance']
    }
  },
  {
    path: '/finance-reports',
    name: 'FinanceReports',
    component: () => import('@/domains/business/views/finance/FinanceReports.vue'),
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
    component: () => import('@/domains/business/views/finance/FXManagement.vue'),
    meta: {
      title: '汇率管理',
      icon: 'Money',
      permission: 'fx-management',
      roles: ['admin', 'manager', 'finance']
    }
  },
  {
    path: '/fiscal-periods',
    name: 'FiscalPeriods',
    component: () => import('@/domains/business/views/finance/FiscalPeriods.vue'),
    meta: {
      title: '会计期间',
      icon: 'Calendar',
      permission: 'fiscal-periods',
      roles: ['admin', 'manager', 'finance']
    }
  },
  
  // ==================== 店铺扩展 ====================
  {
    path: '/store-analytics',
    name: 'StoreAnalytics',
    component: () => import('@/domains/business/views/store/StoreAnalytics.vue'),
    meta: {
      title: '店铺分析',
      icon: 'DataAnalysis',
      permission: 'store-analytics',
      roles: ['admin', 'manager', 'operator']
    }
  },
  
  // ==================== 报表中心 ====================
  
  // ==================== 人力资源扩展 ====================
  {
    path: '/employee-management',
    name: 'EmployeeManagement',
    component: () => import('@/domains/business/views/hr/EmployeeManagement.vue'),
    meta: {
      title: '我的档案',
      icon: 'UserFilled',
      permission: 'employee-management',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/attendance-management',
    redirect: () => ({ path: '/human-resources', query: { tab: 'attendance' } })
  },
  {
    path: '/my-income',
    name: 'MyIncome',
    component: () => import('@/domains/business/views/hr/MyIncome.vue'),
    meta: {
      title: '我的收入',
      icon: 'Money',
      permission: 'my-income',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/my-follow-investment-income',
    name: 'MyFollowInvestmentIncome',
    component: () => import('@/domains/business/views/hr/MyFollowInvestmentIncome.vue'),
    meta: {
      title: '我的跟投收益',
      icon: 'Money',
      permission: 'my-follow-investment-income',
      roles: ['admin', 'manager', 'operator', 'finance', 'investor']
    }
  },
  {
    path: '/employee-salary',
    name: 'EmployeeSalary',
    component: () => import('@/domains/business/views/hr/EmployeeSalary.vue'),
    meta: {
      title: '员工薪资',
      icon: 'Money',
      permission: 'human-resources',
      roles: ['admin']
    }
  },
  {
    path: '/hr-income-audit',
    name: 'HRIncomeAudit',
    component: () => import('@/domains/business/views/hr/IncomeAudit.vue'),
    meta: {
      title: '员工收入审计',
      icon: 'Document',
      permission: 'human-resources',
      roles: ['admin']
    }
  },
  {
    path: '/hr-performance-management',
    redirect: '/hr-performance-management/shop'
  },
  {
    path: '/hr-performance-management/shop',
    name: 'HRPerformanceManagementShop',
    component: () => import('@/domains/business/views/hr/PerformanceManagementShop.vue'),
    meta: {
      title: '店铺绩效管理',
      icon: 'Medal',
      permission: 'performance:config',
      roles: ['admin']
    }
  },
  {
    path: '/hr-performance-management/person',
    name: 'HRPerformanceManagementPerson',
    component: () => import('@/domains/business/views/hr/PerformanceManagementPerson.vue'),
    meta: {
      title: '个人绩效管理',
      icon: 'Medal',
      permission: 'performance:config',
      roles: ['admin']
    }
  },
  {
    path: '/hr-performance-display',
    redirect: '/hr-performance-display/shop'
  },
  {
    path: '/hr-performance-display/shop',
    name: 'HRPerformanceDisplayShop',
    component: () => import('@/domains/business/views/hr/PerformanceDisplayShop.vue'),
    meta: {
      title: '店铺绩效公示',
      icon: 'View',
      permission: 'performance:read',
      roles: ['admin', 'manager', 'operator', 'finance', 'tourist']
    }
  },
  {
    path: '/hr-performance-display/person',
    name: 'HRPerformanceDisplayPerson',
    component: () => import('@/domains/business/views/hr/PerformanceDisplayPerson.vue'),
    meta: {
      title: '个人绩效公示',
      icon: 'View',
      permission: 'performance:read',
      roles: ['admin', 'manager', 'operator', 'finance', 'tourist']
    }
  },
  {
    path: '/hr-shop-assignment',
    name: 'ShopAssignment',
    component: () => import('@/domains/business/views/hr/ShopAssignment.vue'),
    meta: {
      title: '人员店铺归属和提成比',
      icon: 'Connection',
      permission: 'human-resources',
      roles: ['admin']  // 仅管理员可见
    }
  },
  
  // ==================== 审批中心 ====================
  {
    path: '/my-tasks',
    name: 'MyTasks',
    component: () => import('@/domains/platform/views/approval/MyTasks.vue'),
    meta: {
      title: '我的待办',
      icon: 'List',
      permission: 'my-tasks',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/training/overview',
    name: 'TrainingOverview',
    component: () => import('@/domains/platform/views/training/TrainingOverview.vue'),
    meta: {
      title: '培训总览',
      icon: 'Reading',
      permission: 'training-management',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/training/programs',
    name: 'TrainingPrograms',
    component: () => import('@/domains/platform/views/training/TrainingPrograms.vue'),
    meta: {
      title: '培训项目',
      icon: 'Files',
      permission: 'training-management',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/training/assignments',
    name: 'TrainingAssignments',
    component: () => import('@/domains/platform/views/training/TrainingAssignments.vue'),
    meta: {
      title: '培训分配',
      icon: 'UserFilled',
      permission: 'training-management',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/training/assignments/:assignmentId',
    name: 'TrainingAssignmentDetail',
    component: () => import('@/domains/platform/views/training/TrainingAssignmentDetail.vue'),
    meta: {
      title: '培训详情',
      icon: 'Document',
      permission: 'my-training',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/training/results',
    name: 'TrainingResults',
    component: () => import('@/domains/platform/views/training/TrainingResults.vue'),
    meta: {
      title: '培训结果',
      icon: 'Histogram',
      permission: 'training-management',
      roles: ['admin', 'manager']
    }
  },
  {
    path: '/training/integration',
    name: 'TrainingIntegration',
    component: () => import('@/domains/platform/views/training/TrainingIntegration.vue'),
    meta: {
      title: '飞书接入',
      icon: 'Connection',
      permission: 'training-integration',
      roles: ['admin']
    }
  },
  {
    path: '/my-training',
    name: 'MyTraining',
    component: () => import('@/domains/platform/views/training/MyTraining.vue'),
    meta: {
      title: '我的培训',
      icon: 'Notebook',
      permission: 'my-training',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/my-requests',
    name: 'MyRequests',
    component: () => import('@/domains/platform/views/approval/MyRequests.vue'),
    meta: {
      title: '我的申请',
      icon: 'Document',
      permission: 'my-requests',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/approval-history',
    name: 'ApprovalHistory',
    component: () => import('@/domains/platform/views/approval/ApprovalHistory.vue'),
    meta: {
      title: '审批历史',
      icon: 'Clock',
      permission: 'approval-history',
      roles: ['admin', 'manager', 'operator', 'finance']
    }
  },
  {
    path: '/workflow-config',
    name: 'WorkflowConfig',
    component: () => import('@/domains/platform/views/approval/WorkflowConfig.vue'),
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
    component: () => import('@/domains/platform/views/messages/SystemNotifications.vue'),
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
    component: () => import('@/domains/platform/views/messages/Alerts.vue'),
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
    component: () => import('@/domains/platform/views/messages/MessageSettings.vue'),
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
    component: () => import('@/domains/platform/views/system/SystemLogs.vue'),
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
    component: () => import('@/domains/platform/views/system/DataBackup.vue'),
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
    component: () => import('@/domains/platform/views/system/SystemMaintenance.vue'),
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
    component: () => import('@/domains/platform/views/system/NotificationConfig.vue'),
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
    component: () => import('@/domains/platform/views/help/UserGuide.vue'),
    meta: {
      title: '操作指南',
      icon: 'Reading',
      permission: null,
      roles: ['admin', 'manager', 'operator', 'finance', 'tourist', 'investor']
    }
  },
  {
    path: '/video-tutorials',
    name: 'VideoTutorials',
    component: () => import('@/domains/platform/views/help/VideoTutorials.vue'),
    meta: {
      title: '视频教程',
      icon: 'VideoPlay',
      permission: null,
      roles: ['admin', 'manager', 'operator', 'finance', 'tourist', 'investor']
    }
  },
  {
    path: '/faq',
    name: 'FAQ',
    component: () => import('@/domains/platform/views/help/FAQ.vue'),
    meta: {
      title: '常见问题',
      icon: 'QuestionFilled',
      permission: null,
      roles: ['admin', 'manager', 'operator', 'finance', 'tourist', 'investor']
    }
  },
  
  // ==================== 开发工具扩展 ====================
  {
    path: '/api-docs',
    name: 'APIDocs',
    component: () => import('@/domains/platform/views/dev/APIDocs.vue'),
    meta: {
      title: 'API文档',
      icon: 'Document',
      permission: 'system-settings',
      roles: ['admin']
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
  const persistedState = readPersistedAuthState(localStorage)
  let isLoggedIn = authStore.isLoggedIn
  
  if (!isLoggedIn) {
    // 降级：检查 localStorage 中的 token
    if (hasPersistedAuthSession(persistedState)) {
      // 仅恢复完整持久化会话，避免 token 残留把匿名状态误判成已登录
      if (!authStore.user) {
        authStore.initAuth()
      }
      userStore.hydrateFromStorage()
      isLoggedIn = true
    }
  }
  
  // 最后检查 userStore（向后兼容）
  if (!isLoggedIn) {
    isLoggedIn = Boolean(userStore.token && userStore.userInfo)
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
