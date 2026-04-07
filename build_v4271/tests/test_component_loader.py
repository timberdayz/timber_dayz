"""
ComponentLoader 单元测试（迁离 YAML 后，以 Python 组件为唯一来源）。
"""

import pytest

from modules.apps.collection_center.component_loader import (
    ComponentLoader,
    ComponentValidationError,
)


def test_load_python_component_login():
    """load() 应该从 Python 组件构建兼容 dict。"""
    loader = ComponentLoader(hot_reload=True)
    component = loader.load("shopee/login")

    assert component["platform"] == "shopee"
    assert component["type"] == "login"
    # Python 组件应带有 _python_component_class 元信息
    assert "_python_component_class" in component


def test_build_component_dict_from_python():
    """build_component_dict_from_python 返回带元数据的 dict。"""
    loader = ComponentLoader(hot_reload=True)
    params = {"params": {"data_domain": "orders"}}
    comp = loader.build_component_dict_from_python("shopee", "orders_export", params)
    assert comp is not None
    assert comp["platform"] == "shopee"
    assert comp["_params"] == params


def test_cache_behavior():
    """非热重载模式下应缓存组件。"""
    loader = ComponentLoader(hot_reload=False)
    c1 = loader.load("shopee/login")
    c2 = loader.load("shopee/login")
    assert c1 == c2
    assert "shopee/login" in loader._cache


def test_hot_reload_no_cache():
    """热重载模式下不应缓存组件。"""
    loader = ComponentLoader(hot_reload=True)
    loader.load("shopee/login")
    assert "shopee/login" not in loader._cache


def test_component_not_found():
    """不存在的 Python 组件应抛出 FileNotFoundError。"""
    loader = ComponentLoader(hot_reload=True)
    with pytest.raises(FileNotFoundError):
        loader.load("shopee/nonexistent_component_xxx")


def test_get_component_info():
    """get_component_info 应返回基本元信息。"""
    loader = ComponentLoader(hot_reload=True)
    info = loader.get_component_info("shopee/login")
    assert info["name"]
    assert info["platform"] == "shopee"
    assert info["type"] == "login"


def test_clear_cache():
    """clear_cache 应清空内部缓存。"""
    loader = ComponentLoader(hot_reload=False)
    loader.load("shopee/login")
    assert loader._cache
    loader.clear_cache()
    assert loader._cache == {}


def test_validate_string_security():
    """_validate_string_security 应检测危险模式。"""
    loader = ComponentLoader(hot_reload=True)
    with pytest.raises(ComponentValidationError):
        loader._validate_string_security("javascript:alert(1)", "test_field")


def test_replace_variables_for_non_python_component():
    """_replace_variables 仍可用于非 Python 组件 dict。"""
    loader = ComponentLoader(hot_reload=True)
    component = {
        "name": "test",
        "platform": "shopee",
        "type": "login",
        "steps": [
            {"action": "fill", "value": "{{account.username}}"},
        ],
    }
    params = {"account": {"username": "user1"}}
    replaced = loader._replace_variables(component, params)
    assert replaced["steps"][0]["value"] == "user1"

