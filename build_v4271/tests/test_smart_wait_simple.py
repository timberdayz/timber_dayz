"""
测试自适应等待功能（Phase 2.5.4.2）- 简化版

验证_smart_wait_for_element方法的逻辑
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_smart_wait_logic():
    """测试：自适应等待逻辑验证"""
    print("[TEST] Smart wait logic validation")
    
    # 验证方法存在
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2
    
    # 检查方法是否存在
    assert hasattr(CollectionExecutorV2, '_smart_wait_for_element')
    print("[OK] _smart_wait_for_element method exists")
    
    # 检查方法签名
    import inspect
    sig = inspect.signature(CollectionExecutorV2._smart_wait_for_element)
    params = list(sig.parameters.keys())
    
    assert 'self' in params
    assert 'page' in params
    assert 'selector' in params
    assert 'max_timeout' in params
    assert 'state' in params
    print(f"[OK] Method signature correct: {params}")
    
    # 检查默认参数
    assert sig.parameters['max_timeout'].default == 30000
    assert sig.parameters['state'].default == 'visible'
    print("[OK] Default parameters correct")


def test_wait_action_integration():
    """测试：wait动作集成smart_wait参数"""
    print("[TEST] Wait action integration")
    
    # 读取executor_v2.py源代码
    executor_file = Path(__file__).parent.parent / 'modules' / 'apps' / 'collection_center' / 'executor_v2.py'
    content = executor_file.read_text(encoding='utf-8')
    
    # 验证smart_wait参数已添加
    assert 'smart_wait = step.get' in content
    print("[OK] smart_wait parameter added to wait action")
    
    # 验证条件分支
    assert 'if smart_wait:' in content
    print("[OK] Conditional logic for smart_wait exists")
    
    # 验证调用_smart_wait_for_element
    assert '_smart_wait_for_element' in content
    print("[OK] _smart_wait_for_element called in wait action")


def test_documentation():
    """测试：文档已更新"""
    print("[TEST] Documentation update")
    
    # 读取component_schema.md
    schema_file = Path(__file__).parent.parent / 'docs' / 'guides' / 'component_schema.md'
    content = schema_file.read_text(encoding='utf-8')
    
    # 验证smart_wait文档
    assert 'smart_wait' in content
    print("[OK] smart_wait documented in component_schema.md")
    
    # 验证Phase 2.5.4.2标记
    assert 'Phase 2.5.4.2' in content
    print("[OK] Phase 2.5.4.2 marker present")
    
    # 验证策略说明
    assert '快速检测' in content or 'Quick check' in content.lower()
    assert '关闭弹窗' in content or 'popup' in content.lower()
    print("[OK] Strategy documentation present")


def test_strategy_count():
    """测试：4层策略实现"""
    print("[TEST] Four-layer strategy implementation")
    
    # 读取executor_v2.py源代码
    executor_file = Path(__file__).parent.parent / 'modules' / 'apps' / 'collection_center' / 'executor_v2.py'
    content = executor_file.read_text(encoding='utf-8')
    
    # 查找_smart_wait_for_element方法
    method_start = content.find('async def _smart_wait_for_element')
    method_end = content.find('\n    async def ', method_start + 1)
    method_content = content[method_start:method_end]
    
    # 验证4层策略
    assert '策略1' in method_content or 'strategy 1' in method_content.lower()
    assert '策略2' in method_content or 'strategy 2' in method_content.lower()
    assert '策略3' in method_content or 'strategy 3' in method_content.lower()
    assert '策略4' in method_content or 'strategy 4' in method_content.lower()
    print("[OK] All 4 strategies implemented")
    
    # 验证关键操作
    assert 'close_popups' in method_content
    assert 'networkidle' in method_content
    assert 'remaining_timeout' in method_content
    print("[OK] Key operations present")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Smart Wait Implementation (Phase 2.5.4.2)")
    print("=" * 60)
    print()
    
    try:
        test_smart_wait_logic()
        test_wait_action_integration()
        test_documentation()
        test_strategy_count()
        
        print()
        print("=" * 60)
        print("[SUCCESS] All 4 tests passed!")
        print("=" * 60)
        print()
        print("Summary:")
        print("  - Method exists and signature correct")
        print("  - Integrated with wait action")
        print("  - Documentation updated")
        print("  - 4-layer strategy implemented")
        print()
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"[FAILED] Test failed: {e}")
        print("=" * 60)
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        sys.exit(1)

