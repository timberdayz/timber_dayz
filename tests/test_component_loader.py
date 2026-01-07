"""
ComponentLoader 单元测试
"""

import pytest
import tempfile
import os
from pathlib import Path

from modules.apps.collection_center.component_loader import (
    ComponentLoader,
    ComponentValidationError
)


@pytest.fixture
def temp_components_dir():
    """创建临时组件目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建平台目录
        shopee_dir = Path(tmpdir) / 'shopee'
        shopee_dir.mkdir()
        
        # 创建测试组件
        login_component = shopee_dir / 'login.yaml'
        login_component.write_text("""
name: shopee_login
platform: shopee
type: login
version: "1.0.0"
description: "Test login component"
author: "test"

steps:
  - action: navigate
    url: "https://example.com/login"
  - action: fill
    selector: "input[name='username']"
    value: "{{account.username}}"
  - action: fill
    selector: "input[name='password']"
    value: "{{account.password}}"
  - action: click
    selector: "button[type='submit']"
""", encoding='utf-8')
        
        # 创建export组件
        export_component = shopee_dir / 'orders_export.yaml'
        export_component.write_text("""
name: shopee_orders_export
platform: shopee
type: export
version: "1.0.0"
description: "Test export component"
author: "test"
data_domain: orders

steps:
  - action: click
    selector: "button:has-text('Export')"
  - action: wait_for_download
    timeout: 60000
""", encoding='utf-8')
        
        # 创建无效组件（缺少必填字段）
        invalid_component = shopee_dir / 'invalid.yaml'
        invalid_component.write_text("""
name: invalid_component
platform: shopee
# 缺少 type 字段
""", encoding='utf-8')
        
        # 创建危险组件（包含javascript:）
        dangerous_component = shopee_dir / 'dangerous.yaml'
        dangerous_component.write_text("""
name: dangerous_component
platform: shopee
type: login

steps:
  - action: click
    selector: "button[onclick='alert()']"
""", encoding='utf-8')
        
        yield tmpdir


def test_load_component(temp_components_dir):
    """测试加载组件"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=True)
    
    # 加载登录组件
    component = loader.load('shopee/login')
    
    assert component['name'] == 'shopee_login'
    assert component['platform'] == 'shopee'
    assert component['type'] == 'login'
    assert len(component['steps']) == 4


def test_load_export_component(temp_components_dir):
    """测试加载export组件"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=True)
    
    # 加载export组件
    component = loader.load('shopee/orders_export')
    
    assert component['type'] == 'export'
    assert component['data_domain'] == 'orders'


def test_variable_replacement(temp_components_dir):
    """测试变量替换"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=True)
    
    # 加载组件并替换变量
    params = {
        'account': {
            'username': 'test_user',
            'password': 'test_pass'
        }
    }
    
    component = loader.load('shopee/login', params=params)
    
    # 检查变量是否被替换
    fill_steps = [s for s in component['steps'] if s['action'] == 'fill']
    assert fill_steps[0]['value'] == 'test_user'
    assert fill_steps[1]['value'] == 'test_pass'


def test_cache(temp_components_dir):
    """测试缓存功能"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=False)
    
    # 第一次加载
    component1 = loader.load('shopee/login')
    
    # 第二次加载（应该从缓存）
    component2 = loader.load('shopee/login')
    
    assert component1 == component2
    assert 'shopee/login' in loader._cache


def test_hot_reload(temp_components_dir):
    """测试热重载"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=True)
    
    # 加载组件
    loader.load('shopee/login')
    
    # 热重载模式下不应该缓存
    assert 'shopee/login' not in loader._cache


def test_invalid_component(temp_components_dir):
    """测试加载无效组件"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=True)
    
    # 应该抛出验证错误
    with pytest.raises(ComponentValidationError, match="Missing required field: type"):
        loader.load('shopee/invalid')


def test_dangerous_selector(temp_components_dir):
    """测试危险selector检测"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=True)
    
    # 应该抛出安全错误
    with pytest.raises(ComponentValidationError, match="Dangerous pattern detected"):
        loader.load('shopee/dangerous')


def test_component_not_found(temp_components_dir):
    """测试组件不存在"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=True)
    
    # 应该抛出文件不存在错误
    with pytest.raises(FileNotFoundError):
        loader.load('shopee/nonexistent')


def test_get_component_info(temp_components_dir):
    """测试获取组件信息"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=True)
    
    info = loader.get_component_info('shopee/login')
    
    assert info['name'] == 'shopee_login'
    assert info['platform'] == 'shopee'
    assert info['type'] == 'login'
    assert info['step_count'] == 4


def test_clear_cache(temp_components_dir):
    """测试清空缓存"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=False)
    
    # 加载组件（会缓存）
    loader.load('shopee/login')
    assert 'shopee/login' in loader._cache
    
    # 清空缓存
    loader.clear_cache()
    assert 'shopee/login' not in loader._cache


def test_load_all(temp_components_dir):
    """测试加载所有组件"""
    loader = ComponentLoader(components_dir=temp_components_dir, hot_reload=False)
    
    components = loader.load_all()
    
    assert 'shopee' in components
    # 应该加载了2个有效组件（login和orders_export），跳过了invalid和dangerous
    assert len([c for c in components['shopee'] if c in ['login', 'orders_export']]) == 2

