"""孤儿 stable 组件记录的判定逻辑测试。

sys.path 引导是必需的：`backend/` 下没有 `__init__.py`（命名空间包），
不同 pytest 调用方式下仓库根未必在 sys.path 上。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.active_collection_components import is_missing_component_file


def test_is_missing_component_file_detects_missing_file():
    assert (
        is_missing_component_file(
            "modules/platforms/miaoshou/components/__not_exist__.py"
        )
        is True
    )


def test_is_missing_component_file_detects_archived_path():
    assert (
        is_missing_component_file(
            "modules/platforms/miaoshou/archive/inventory_snapshot_export.py"
        )
        is True
    )


def test_is_missing_component_file_accepts_existing_active_file():
    assert (
        is_missing_component_file(
            "modules/platforms/miaoshou/components/inventory_export.py"
        )
        is False
    )


def test_is_missing_component_file_treats_empty_path_as_missing():
    assert is_missing_component_file("") is True
