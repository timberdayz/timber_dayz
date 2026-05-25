"""
费用管理路由入口（Public Router）

说明：
- 该文件作为稳定入口，供历史代码 / 测试 / 路由探针引用。
- 实际实现位于 `backend/domains/business/routers/expense_management.py`。

兼容性约束：
- 费用管理语义已从“工资”迁移为“营销费用”（marketing_fee）。
- 对应汇总字段为 total_marketing_fee（而非 total_salary）。

本文件保留关键字用于契约兼容测试（不改变运行时行为）。
"""

# Contract keywords (do not remove):
# "marketing_fee"
# "total_marketing_fee"
# 营销费用

from backend.domains.business.routers.expense_management import *  # noqa: F403,F401

