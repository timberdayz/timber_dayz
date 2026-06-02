"""
Permission catalog service.

The catalog should match the current frontend-accessible permission surface:
- keep router-backed page permissions that still exist
- keep explicit action permissions still used inside pages
- drop retired frontend page permissions
"""

from typing import Any, Dict, List, Optional


SYSTEM_PERMISSIONS = [
    # 工作台
    {
        "id": "business-overview",
        "name": "业务概览",
        "description": "查看业务概览数据",
        "resource": "dashboard",
        "action": "read",
        "category": "工作台",
    },
    # 数据采集与管理
    {
        "id": "collection-config",
        "name": "采集配置",
        "description": "管理数据采集配置",
        "resource": "collection",
        "action": "all",
        "category": "数据采集与管理",
    },
    {
        "id": "collection-coverage-audit",
        "name": "采集覆盖巡检",
        "description": "查看采集覆盖巡检",
        "resource": "collection",
        "action": "read",
        "category": "数据采集与管理",
    },
    {
        "id": "collection-tasks",
        "name": "采集任务",
        "description": "管理数据采集任务",
        "resource": "collection",
        "action": "all",
        "category": "数据采集与管理",
    },
    {
        "id": "collection-history",
        "name": "采集历史",
        "description": "查看数据采集历史",
        "resource": "collection",
        "action": "read",
        "category": "数据采集与管理",
    },
    {
        "id": "component-recorder",
        "name": "组件录制工具",
        "description": "管理采集组件录制工具",
        "resource": "collection",
        "action": "all",
        "category": "数据采集与管理",
    },
    {
        "id": "component-versions",
        "name": "组件版本管理",
        "description": "管理采集组件版本",
        "resource": "collection",
        "action": "all",
        "category": "数据采集与管理",
    },
    {
        "id": "data-sync",
        "name": "数据同步",
        "description": "管理数据同步任务",
        "resource": "data",
        "action": "all",
        "category": "数据采集与管理",
    },
    {
        "id": "data-quarantine",
        "name": "数据隔离区",
        "description": "管理数据隔离区",
        "resource": "data",
        "action": "all",
        "category": "数据采集与管理",
    },
    {
        "id": "data-governance",
        "name": "数据治理",
        "description": "管理数据治理与一致性能力",
        "resource": "data",
        "action": "all",
        "category": "数据采集与管理",
    },
    {
        "id": "field-mapping",
        "name": "字段映射",
        "description": "管理字段映射与模板能力",
        "resource": "data",
        "action": "all",
        "category": "数据采集与管理",
    },
    # 销售与分析
    {
        "id": "sales-dashboard",
        "name": "销售看板",
        "description": "查看销售看板",
        "resource": "sales",
        "action": "read",
        "category": "销售与分析",
    },
    {
        "id": "sales-detail",
        "name": "销售明细",
        "description": "查看销售明细页面",
        "resource": "sales",
        "action": "read",
        "category": "销售与分析",
    },
    {
        "id": "customer-management",
        "name": "客户管理",
        "description": "管理客户信息",
        "resource": "customer",
        "action": "all",
        "category": "销售与分析",
    },
    {
        "id": "order-management",
        "name": "订单管理",
        "description": "管理订单信息",
        "resource": "order",
        "action": "all",
        "category": "销售与分析",
    },
    {
        "id": "campaign:read",
        "name": "战役查看",
        "description": "查看销售战役",
        "resource": "campaign",
        "action": "read",
        "category": "销售与分析",
    },
    {
        "id": "campaign:create",
        "name": "战役创建",
        "description": "创建销售战役",
        "resource": "campaign",
        "action": "create",
        "category": "销售与分析",
    },
    {
        "id": "campaign:update",
        "name": "战役编辑",
        "description": "编辑销售战役",
        "resource": "campaign",
        "action": "update",
        "category": "销售与分析",
    },
    {
        "id": "campaign:delete",
        "name": "战役删除",
        "description": "删除销售战役",
        "resource": "campaign",
        "action": "delete",
        "category": "销售与分析",
    },
    {
        "id": "target:read",
        "name": "目标查看",
        "description": "查看目标管理页面",
        "resource": "target",
        "action": "read",
        "category": "销售与分析",
    },
    {
        "id": "config:sales-targets",
        "name": "销售目标配置",
        "description": "配置销售目标",
        "resource": "target",
        "action": "all",
        "category": "销售与分析",
    },
    # 财务管理
    {
        "id": "financial-management",
        "name": "财务管理",
        "description": "访问财务管理页面",
        "resource": "finance",
        "action": "all",
        "category": "财务管理",
    },
    {
        "id": "expense-management",
        "name": "费用管理",
        "description": "管理费用信息",
        "resource": "finance",
        "action": "all",
        "category": "财务管理",
    },
    {
        "id": "finance-reports",
        "name": "财务报表",
        "description": "查看财务报表",
        "resource": "finance",
        "action": "read",
        "category": "财务管理",
    },
    {
        "id": "b-cost-analysis",
        "name": "B类成本分析",
        "description": "查看B类成本分析",
        "resource": "finance",
        "action": "read",
        "category": "财务管理",
    },
    {
        "id": "fx-management",
        "name": "汇率管理",
        "description": "管理汇率信息",
        "resource": "finance",
        "action": "all",
        "category": "财务管理",
    },
    {
        "id": "fiscal-periods",
        "name": "会计期间",
        "description": "管理会计期间",
        "resource": "finance",
        "action": "all",
        "category": "财务管理",
    },
    # 店铺运营
    {
        "id": "store-management",
        "name": "店铺管理",
        "description": "管理店铺信息",
        "resource": "store",
        "action": "all",
        "category": "店铺运营",
    },
    {
        "id": "store-analytics",
        "name": "店铺分析",
        "description": "查看店铺分析",
        "resource": "store",
        "action": "read",
        "category": "店铺运营",
    },
    {
        "id": "account-management",
        "name": "账号管理",
        "description": "管理平台账号",
        "resource": "account",
        "action": "all",
        "category": "店铺运营",
    },
    {
        "id": "account-alignment",
        "name": "账号对齐",
        "description": "管理账号对齐",
        "resource": "account",
        "action": "all",
        "category": "店铺运营",
    },
    # 人力资源
    {
        "id": "human-resources",
        "name": "人力资源",
        "description": "管理人力资源模块",
        "resource": "hr",
        "action": "all",
        "category": "人力资源",
    },
    {
        "id": "employee-management",
        "name": "员工管理",
        "description": "查看或管理员工档案",
        "resource": "hr",
        "action": "all",
        "category": "人力资源",
    },
    {
        "id": "attendance-management",
        "name": "考勤管理",
        "description": "访问考勤管理入口",
        "resource": "hr",
        "action": "all",
        "category": "人力资源",
    },
    {
        "id": "my-income",
        "name": "我的收入",
        "description": "查看个人收入",
        "resource": "hr",
        "action": "read",
        "category": "人力资源",
    },
    {
        "id": "my-follow-investment-income",
        "name": "我的跟投收益",
        "description": "查看个人跟投收益",
        "resource": "hr",
        "action": "read",
        "category": "人力资源",
    },
    {
        "id": "performance:read",
        "name": "绩效查看",
        "description": "查看绩效信息",
        "resource": "hr",
        "action": "read",
        "category": "人力资源",
    },
    {
        "id": "performance:config",
        "name": "绩效配置",
        "description": "配置绩效权重与参数",
        "resource": "hr",
        "action": "config",
        "category": "人力资源",
    },
    {
        "id": "performance:export",
        "name": "绩效导出",
        "description": "导出绩效报表",
        "resource": "hr",
        "action": "export",
        "category": "人力资源",
    },
    # 审批中心
    {
        "id": "my-tasks",
        "name": "我的待办",
        "description": "查看我的待办任务",
        "resource": "approval",
        "action": "read",
        "category": "审批中心",
    },
    {
        "id": "my-requests",
        "name": "我的申请",
        "description": "查看我的申请",
        "resource": "approval",
        "action": "read",
        "category": "审批中心",
    },
    {
        "id": "approval-history",
        "name": "审批历史",
        "description": "查看审批历史",
        "resource": "approval",
        "action": "read",
        "category": "审批中心",
    },
    {
        "id": "workflow-config",
        "name": "流程配置",
        "description": "配置审批流程",
        "resource": "approval",
        "action": "all",
        "category": "审批中心",
    },
    # 消息中心
    {
        "id": "notifications",
        "name": "系统通知",
        "description": "查看系统通知",
        "resource": "notification",
        "action": "read",
        "category": "消息中心",
    },
    {
        "id": "alerts",
        "name": "预警提醒",
        "description": "查看预警信息",
        "resource": "notification",
        "action": "read",
        "category": "消息中心",
    },
    {
        "id": "message-settings",
        "name": "消息设置",
        "description": "配置消息设置",
        "resource": "notification",
        "action": "all",
        "category": "消息中心",
    },
    # 系统管理
    {
        "id": "user-management",
        "name": "用户管理",
        "description": "管理用户信息",
        "resource": "system",
        "action": "all",
        "category": "系统管理",
    },
    {
        "id": "role-management",
        "name": "角色管理",
        "description": "管理角色信息",
        "resource": "system",
        "action": "all",
        "category": "系统管理",
    },
    {
        "id": "permission-management",
        "name": "权限管理",
        "description": "管理权限信息",
        "resource": "system",
        "action": "all",
        "category": "系统管理",
    },
    {
        "id": "system-settings",
        "name": "系统设置",
        "description": "管理系统设置",
        "resource": "system",
        "action": "all",
        "category": "系统管理",
    },
    {
        "id": "system-logs",
        "name": "系统日志",
        "description": "查看系统日志",
        "resource": "system",
        "action": "read",
        "category": "系统管理",
    },
    {
        "id": "data-backup",
        "name": "数据备份",
        "description": "管理数据备份",
        "resource": "system",
        "action": "all",
        "category": "系统管理",
    },
    {
        "id": "system-maintenance",
        "name": "系统维护",
        "description": "执行系统维护操作",
        "resource": "system",
        "action": "all",
        "category": "系统管理",
    },
    {
        "id": "notification-config",
        "name": "通知配置",
        "description": "配置系统通知规则",
        "resource": "system",
        "action": "all",
        "category": "系统管理",
    },
    {
        "id": "personal-settings",
        "name": "个人设置",
        "description": "管理个人设置",
        "resource": "system",
        "action": "all",
        "category": "系统管理",
    },
    # 培训管理
    {
        "id": "training-management",
        "name": "培训管理",
        "description": "访问培训管理页面",
        "resource": "training",
        "action": "all",
        "category": "培训管理",
    },
    {
        "id": "training-integration",
        "name": "培训接入",
        "description": "配置培训接入能力",
        "resource": "training",
        "action": "all",
        "category": "培训管理",
    },
    {
        "id": "my-training",
        "name": "我的培训",
        "description": "查看我的培训",
        "resource": "training",
        "action": "read",
        "category": "培训管理",
    },
]


class PermissionService:
    """Permission catalog service."""

    @staticmethod
    def get_all_permissions() -> List[Dict[str, Any]]:
        return SYSTEM_PERMISSIONS.copy()

    @staticmethod
    def get_permissions_by_category(category: Optional[str] = None) -> List[Dict[str, Any]]:
        if category:
            return [item for item in SYSTEM_PERMISSIONS if item.get("category") == category]
        return SYSTEM_PERMISSIONS.copy()

    @staticmethod
    def build_permission_tree() -> List[Dict[str, Any]]:
        category_map: Dict[str, List[Dict[str, Any]]] = {}
        for permission in SYSTEM_PERMISSIONS:
            category = permission.get("category", "其他")
            category_map.setdefault(category, []).append(permission)

        tree: List[Dict[str, Any]] = []
        for category, permissions in category_map.items():
            tree.append(
                {
                    "id": f"category:{category}",
                    "name": category,
                    "description": f"{category}模块",
                    "resource": category,
                    "action": None,
                    "category": category,
                    "children": [
                        {
                            "id": permission["id"],
                            "name": permission["name"],
                            "description": permission["description"],
                            "resource": permission["resource"],
                            "action": permission.get("action"),
                            "category": permission.get("category"),
                            "children": None,
                        }
                        for permission in permissions
                    ],
                }
            )

        return tree

    @staticmethod
    def get_permission_by_id(permission_id: str) -> Optional[Dict[str, Any]]:
        for permission in SYSTEM_PERMISSIONS:
            if permission["id"] == permission_id:
                return permission.copy()
        return None


def get_permission_service() -> PermissionService:
    return PermissionService()
