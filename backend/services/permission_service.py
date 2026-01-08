"""
权限管理服务
提供系统预定义权限列表和权限树构建功能

v4.20.0: 系统管理模块API实现
"""

from typing import List, Dict, Any, Optional
from modules.core.logger import get_logger

logger = get_logger(__name__)


# 系统预定义权限列表（基于前端权限定义）
SYSTEM_PERMISSIONS = [
    # 工作台
    {"id": "business-overview", "name": "业务概览", "description": "查看业务概览数据", "resource": "dashboard", "action": "read", "category": "工作台"},
    
    # 数据采集与管理
    {"id": "collection-config", "name": "采集配置", "description": "管理数据采集配置", "resource": "collection", "action": "all", "category": "数据采集与管理"},
    {"id": "collection-tasks", "name": "采集任务", "description": "管理数据采集任务", "resource": "collection", "action": "all", "category": "数据采集与管理"},
    {"id": "collection-history", "name": "采集历史", "description": "查看数据采集历史", "resource": "collection", "action": "read", "category": "数据采集与管理"},
    {"id": "data-sync", "name": "数据同步", "description": "管理数据同步任务", "resource": "data", "action": "all", "category": "数据采集与管理"},
    {"id": "data-quarantine", "name": "数据隔离", "description": "管理数据隔离区", "resource": "data", "action": "all", "category": "数据采集与管理"},
    {"id": "data-browser", "name": "数据浏览", "description": "浏览原始数据", "resource": "data", "action": "read", "category": "数据采集与管理"},
    
    # 产品与库存
    {"id": "product-management", "name": "产品管理", "description": "管理产品信息", "resource": "product", "action": "all", "category": "产品与库存"},
    {"id": "inventory-management", "name": "库存管理", "description": "管理库存信息", "resource": "inventory", "action": "all", "category": "产品与库存"},
    {"id": "inventory-dashboard-v3", "name": "库存看板", "description": "查看库存看板", "resource": "inventory", "action": "read", "category": "产品与库存"},
    
    # 采购管理
    {"id": "purchase-orders", "name": "采购订单", "description": "管理采购订单", "resource": "purchase", "action": "all", "category": "采购管理"},
    {"id": "grn-management", "name": "入库管理", "description": "管理入库单", "resource": "purchase", "action": "all", "category": "采购管理"},
    {"id": "vendor-management", "name": "供应商管理", "description": "管理供应商信息", "resource": "vendor", "action": "all", "category": "采购管理"},
    {"id": "invoice-management", "name": "发票管理", "description": "管理发票信息", "resource": "finance", "action": "all", "category": "采购管理"},
    
    # 销售与分析
    {"id": "sales-dashboard-v3", "name": "销售看板", "description": "查看销售看板", "resource": "sales", "action": "read", "category": "销售与分析"},
    {"id": "sales-analysis", "name": "销售分析", "description": "查看销售分析", "resource": "sales", "action": "read", "category": "销售与分析"},
    {"id": "customer-management", "name": "客户管理", "description": "管理客户信息", "resource": "customer", "action": "all", "category": "销售与分析"},
    {"id": "order-management", "name": "订单管理", "description": "管理订单信息", "resource": "order", "action": "all", "category": "销售与分析"},
    {"id": "campaign:read", "name": "活动查看", "description": "查看营销活动", "resource": "campaign", "action": "read", "category": "销售与分析"},
    {"id": "target:read", "name": "目标查看", "description": "查看销售目标", "resource": "target", "action": "read", "category": "销售与分析"},
    
    # 财务管理
    {"id": "financial-management", "name": "财务管理", "description": "管理财务信息", "resource": "finance", "action": "all", "category": "财务管理"},
    {"id": "expense-management", "name": "费用管理", "description": "管理费用信息", "resource": "finance", "action": "all", "category": "财务管理"},
    {"id": "finance-reports", "name": "财务报表", "description": "查看财务报表", "resource": "finance", "action": "read", "category": "财务管理"},
    {"id": "fx-management", "name": "汇率管理", "description": "管理汇率信息", "resource": "finance", "action": "all", "category": "财务管理"},
    {"id": "fiscal-periods", "name": "会计期间", "description": "管理会计期间", "resource": "finance", "action": "all", "category": "财务管理"},
    
    # 店铺运营
    {"id": "store-management", "name": "店铺管理", "description": "管理店铺信息", "resource": "store", "action": "all", "category": "店铺运营"},
    {"id": "store-analytics", "name": "店铺分析", "description": "查看店铺分析", "resource": "store", "action": "read", "category": "店铺运营"},
    {"id": "account-management", "name": "账号管理", "description": "管理平台账号", "resource": "account", "action": "all", "category": "店铺运营"},
    {"id": "account-alignment", "name": "账号对齐", "description": "管理账号对齐", "resource": "account", "action": "all", "category": "店铺运营"},
    
    # 报表中心
    {"id": "sales-reports", "name": "销售报表", "description": "查看销售报表", "resource": "report", "action": "read", "category": "报表中心"},
    {"id": "inventory-reports", "name": "库存报表", "description": "查看库存报表", "resource": "report", "action": "read", "category": "报表中心"},
    {"id": "finance-reports-detail", "name": "财务报表详情", "description": "查看财务报表详情", "resource": "report", "action": "read", "category": "报表中心"},
    {"id": "vendor-reports", "name": "供应商报表", "description": "查看供应商报表", "resource": "report", "action": "read", "category": "报表中心"},
    {"id": "custom-reports", "name": "自定义报表", "description": "创建和查看自定义报表", "resource": "report", "action": "all", "category": "报表中心"},
    
    # 人力资源
    {"id": "human-resources", "name": "人力资源", "description": "管理人力资源", "resource": "hr", "action": "all", "category": "人力资源"},
    {"id": "employee-management", "name": "员工管理", "description": "管理员工信息", "resource": "hr", "action": "all", "category": "人力资源"},
    {"id": "attendance-management", "name": "考勤管理", "description": "管理考勤信息", "resource": "hr", "action": "all", "category": "人力资源"},
    {"id": "performance:read", "name": "绩效查看", "description": "查看绩效信息", "resource": "hr", "action": "read", "category": "人力资源"},
    
    # 审批中心
    {"id": "my-tasks", "name": "我的任务", "description": "查看我的审批任务", "resource": "approval", "action": "read", "category": "审批中心"},
    {"id": "my-requests", "name": "我的申请", "description": "查看我的申请", "resource": "approval", "action": "read", "category": "审批中心"},
    {"id": "approval-history", "name": "审批历史", "description": "查看审批历史", "resource": "approval", "action": "read", "category": "审批中心"},
    {"id": "workflow-config", "name": "流程配置", "description": "配置审批流程", "resource": "approval", "action": "all", "category": "审批中心"},
    
    # 消息中心
    {"id": "system-notifications", "name": "系统通知", "description": "查看系统通知", "resource": "notification", "action": "read", "category": "消息中心"},
    {"id": "alerts", "name": "告警", "description": "查看告警信息", "resource": "notification", "action": "read", "category": "消息中心"},
    {"id": "message-settings", "name": "消息设置", "description": "配置消息设置", "resource": "notification", "action": "all", "category": "消息中心"},
    
    # 系统管理
    {"id": "user-management", "name": "用户管理", "description": "管理用户信息", "resource": "system", "action": "all", "category": "系统管理"},
    {"id": "role-management", "name": "角色管理", "description": "管理角色信息", "resource": "system", "action": "all", "category": "系统管理"},
    {"id": "permission-management", "name": "权限管理", "description": "管理权限信息", "resource": "system", "action": "all", "category": "系统管理"},
    {"id": "system-settings", "name": "系统设置", "description": "管理系统设置", "resource": "system", "action": "all", "category": "系统管理"},
    {"id": "system-logs", "name": "系统日志", "description": "查看系统日志", "resource": "system", "action": "read", "category": "系统管理"},
    {"id": "personal-settings", "name": "个人设置", "description": "管理个人设置", "resource": "system", "action": "all", "category": "系统管理"},
    
    # 帮助中心
    {"id": "user-guide", "name": "用户指南", "description": "查看用户指南", "resource": "help", "action": "read", "category": "帮助中心"},
    {"id": "video-tutorials", "name": "视频教程", "description": "查看视频教程", "resource": "help", "action": "read", "category": "帮助中心"},
    {"id": "faq", "name": "常见问题", "description": "查看常见问题", "resource": "help", "action": "read", "category": "帮助中心"},
]


class PermissionService:
    """权限管理服务类"""
    
    @staticmethod
    def get_all_permissions() -> List[Dict[str, Any]]:
        """获取所有系统预定义权限"""
        return SYSTEM_PERMISSIONS.copy()
    
    @staticmethod
    def get_permissions_by_category(category: Optional[str] = None) -> List[Dict[str, Any]]:
        """按分类获取权限"""
        if category:
            return [p for p in SYSTEM_PERMISSIONS if p.get("category") == category]
        return SYSTEM_PERMISSIONS.copy()
    
    @staticmethod
    def build_permission_tree() -> List[Dict[str, Any]]:
        """构建权限树（按模块分组）"""
        # 按分类分组
        category_map: Dict[str, List[Dict[str, Any]]] = {}
        for perm in SYSTEM_PERMISSIONS:
            category = perm.get("category", "其他")
            if category not in category_map:
                category_map[category] = []
            category_map[category].append(perm)
        
        # 构建树形结构
        tree = []
        for category, perms in category_map.items():
            # 分类节点
            category_node = {
                "id": f"category:{category}",
                "name": category,
                "description": f"{category}模块",
                "resource": category,
                "action": None,
                "category": category,
                "children": []
            }
            
            # 添加权限子节点
            for perm in perms:
                child_node = {
                    "id": perm["id"],
                    "name": perm["name"],
                    "description": perm["description"],
                    "resource": perm["resource"],
                    "action": perm.get("action"),
                    "category": perm.get("category"),
                    "children": None
                }
                category_node["children"].append(child_node)
            
            tree.append(category_node)
        
        return tree
    
    @staticmethod
    def get_permission_by_id(permission_id: str) -> Optional[Dict[str, Any]]:
        """根据权限ID获取权限信息"""
        for perm in SYSTEM_PERMISSIONS:
            if perm["id"] == permission_id:
                return perm.copy()
        return None


def get_permission_service() -> PermissionService:
    """获取权限管理服务实例"""
    return PermissionService()
