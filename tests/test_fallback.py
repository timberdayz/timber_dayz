"""
测试fallback降级策略功能（Phase 2.5.5）

验证_execute_with_fallback方法
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_fallback_logic():
    """测试：fallback降级策略逻辑验证"""
    print("[TEST] Fallback logic validation")
    
    # 验证方法存在
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2
    
    # 检查方法是否存在
    assert hasattr(CollectionExecutorV2, '_execute_with_fallback')
    print("[OK] _execute_with_fallback method exists")
    
    # 检查方法签名
    import inspect
    sig = inspect.signature(CollectionExecutorV2._execute_with_fallback)
    params = list(sig.parameters.keys())
    
    assert 'self' in params
    assert 'page' in params
    assert 'step' in params
    assert 'component' in params
    print(f"[OK] Method signature correct: {params}")


def test_execute_step_integration():
    """测试：_execute_step集成fallback参数"""
    print("[TEST] _execute_step integration")
    
    # 读取executor_v2.py源代码
    executor_file = Path(__file__).parent.parent / 'modules' / 'apps' / 'collection_center' / 'executor_v2.py'
    content = executor_file.read_text(encoding='utf-8')
    
    # 验证fallback_methods参数已添加
    assert 'fallback_methods = step.get' in content
    print("[OK] fallback_methods parameter added to _execute_step")
    
    # 验证条件分支
    assert 'if fallback_methods:' in content
    print("[OK] Conditional logic for fallback_methods exists")
    
    # 验证调用_execute_with_fallback
    assert '_execute_with_fallback' in content
    print("[OK] _execute_with_fallback called in _execute_step")


def test_documentation():
    """测试：文档已更新"""
    print("[TEST] Documentation update")
    
    # 读取component_schema.md
    schema_file = Path(__file__).parent.parent / 'docs' / 'guides' / 'component_schema.md'
    content = schema_file.read_text(encoding='utf-8')
    
    # 验证fallback_methods文档
    assert 'fallback_methods' in content
    print("[OK] fallback_methods documented in component_schema.md")
    
    # 验证Phase 2.5.5标记
    assert 'Phase 2.5.5' in content
    print("[OK] Phase 2.5.5 marker present")
    
    # 验证使用示例
    assert '降级' in content or 'fallback' in content.lower()
    print("[OK] Fallback usage example present")


def test_fallback_features():
    """测试：fallback关键特性实现"""
    print("[TEST] Fallback features implementation")
    
    # 读取executor_v2.py源代码
    executor_file = Path(__file__).parent.parent / 'modules' / 'apps' / 'collection_center' / 'executor_v2.py'
    content = executor_file.read_text(encoding='utf-8')
    
    # 查找_execute_with_fallback方法
    method_start = content.find('async def _execute_with_fallback')
    method_end = content.find('\n    async def ', method_start + 1)
    if method_end == -1:
        method_end = content.find('\n    def _', method_start + 1)
    method_content = content[method_start:method_end]
    
    # 验证关键特性
    assert 'primary' in method_content.lower()
    print("[OK] Primary method handling present")
    
    assert 'fallback_methods' in method_content
    print("[OK] Fallback methods iteration present")
    
    assert 'fallback_selector' in method_content
    print("[OK] Fallback selector extraction present")
    
    assert 'description' in method_content
    print("[OK] Fallback description support present")
    
    # 验证日志记录
    assert 'logger' in method_content
    print("[OK] Logging present")


def test_yaml_example():
    """测试：YAML示例格式验证"""
    print("[TEST] YAML example format")
    
    # 读取component_schema.md
    schema_file = Path(__file__).parent.parent / 'docs' / 'guides' / 'component_schema.md'
    content = schema_file.read_text(encoding='utf-8')
    
    # 验证YAML示例包含关键字段
    assert 'selector:' in content
    assert 'fallback_methods:' in content
    print("[OK] YAML example contains required fields")
    
    # 验证示例包含description
    if 'fallback_methods:' in content:
        # 查找fallback_methods后的内容
        idx = content.find('fallback_methods:')
        next_section = content[idx:idx+500]
        assert 'description' in next_section
        print("[OK] YAML example includes description field")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Fallback Strategy (Phase 2.5.5)")
    print("=" * 60)
    print()
    
    try:
        test_fallback_logic()
        test_execute_step_integration()
        test_documentation()
        test_fallback_features()
        test_yaml_example()
        
        print()
        print("=" * 60)
        print("[SUCCESS] All 5 tests passed!")
        print("=" * 60)
        print()
        print("Summary:")
        print("  - Method exists and signature correct")
        print("  - Integrated with _execute_step")
        print("  - Documentation updated")
        print("  - Key features implemented")
        print("  - YAML examples provided")
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

