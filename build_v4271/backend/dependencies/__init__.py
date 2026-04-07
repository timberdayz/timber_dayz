"""
Backend 共享依赖 (Shared Dependencies)

将认证、权限等依赖从 router 中提取出来，
消除 router 之间的循环导入风险，为 router 拆分做准备。
"""

from backend.dependencies.auth import get_current_user, require_admin

__all__ = ["get_current_user", "require_admin"]
