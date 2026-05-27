"""
字段映射路由 - 共享辅助函数

提供安全路径校验和文件路径解析器,供 field_mapping 子模块共享使用。
"""

from pathlib import Path as _SafePath

from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.services.file_path_resolver import get_file_path_resolver

file_path_resolver = get_file_path_resolver()


def _is_subpath(child: _SafePath, parent: _SafePath) -> bool:
    """判断 child 是否位于 parent 之下(兼容Python 3.9)。"""
    try:
        child_r = child.resolve()
        parent_r = parent.resolve()
        return str(child_r).startswith(str(parent_r))
    except Exception:
        return False


def _safe_resolve_path(file_path: str) -> str:
    """限制文件访问在允许的根目录:<project>/data/raw 与 <project>/downloads。"""
    from modules.core.path_manager import get_project_root, get_data_raw_dir, get_downloads_dir

    project_root = _SafePath(get_project_root())
    allowed_roots = [_SafePath(get_data_raw_dir()), _SafePath(get_downloads_dir())]

    p = _SafePath(file_path)
    if not p.is_absolute():
        p = (project_root / p).resolve()

    for root in allowed_roots:
        if _is_subpath(p, root):
            return str(p)

    return error_response(
        code=ErrorCode.DATA_VALIDATION_FAILED,
        message="文件路径不在允许的根目录内",
        error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
        recovery_suggestion="请检查文件路径是否在允许的根目录内,或联系系统管理员",
        status_code=400
    )
