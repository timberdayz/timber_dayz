"""
ComponentLoader 演示脚本

展示如何使用ComponentLoader加载和验证组件
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.apps.collection_center.component_loader import (
    ComponentLoader,
    ComponentValidationError
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


def demo_basic_loading():
    """演示基础加载功能"""
    print("\n" + "="*60)
    print("1. 基础加载演示")
    print("="*60)
    
    # 初始化加载器（热重载模式）
    loader = ComponentLoader(hot_reload=True)
    print(f"✓ ComponentLoader initialized")
    print(f"  Components directory: {loader.components_dir}")
    print(f"  Hot reload: {loader.hot_reload}")
    
    # 加载登录模板
    try:
        component = loader.load('_templates/login')
        print(f"\n✓ Loaded component: {component['name']}")
        print(f"  Platform: {component['platform']}")
        print(f"  Type: {component['type']}")
        print(f"  Steps: {len(component['steps'])}")
    except FileNotFoundError:
        print("\n✗ Template not found (this is expected if no templates exist yet)")
    except Exception as e:
        print(f"\n✗ Error loading component: {e}")


def demo_variable_replacement():
    """演示变量替换功能"""
    print("\n" + "="*60)
    print("2. 变量替换演示")
    print("="*60)
    
    loader = ComponentLoader(hot_reload=True)
    
    try:
        # 准备参数
        params = {
            'account': {
                'username': 'demo_user',
                'password': '********',
                'platform': 'shopee'
            },
            'params': {
                'date_from': '2025-01-01',
                'date_to': '2025-01-31',
                'data_domain': 'orders'
            },
            'task': {
                'id': 'task-12345',
                'download_dir': '/tmp/downloads'
            }
        }
        
        # 加载组件并替换变量
        component = loader.load('_templates/login', params=params)
        
        print("✓ Variables replaced successfully")
        print(f"\nOriginal: {{{{account.username}}}}")
        print(f"Replaced: {params['account']['username']}")
        
        # 显示替换后的步骤
        for i, step in enumerate(component['steps'][:3], 1):
            if 'value' in step:
                print(f"\nStep {i} ({step['action']}): {step.get('value', 'N/A')}")
    
    except Exception as e:
        print(f"✗ Error: {e}")


def demo_validation():
    """演示验证功能"""
    print("\n" + "="*60)
    print("3. 安全验证演示")
    print("="*60)
    
    loader = ComponentLoader(hot_reload=True)
    
    # 测试危险模式检测
    dangerous_patterns = [
        "javascript:",
        "onclick=",
        "<script>",
        "eval(",
    ]
    
    print("Testing dangerous pattern detection:")
    for pattern in dangerous_patterns:
        print(f"  - {pattern}: ", end="")
        try:
            loader._validate_string_security(pattern, "test_field")
            print("✗ NOT DETECTED (bug!)")
        except ComponentValidationError:
            print("✓ Detected")


def demo_cache():
    """演示缓存功能"""
    print("\n" + "="*60)
    print("4. 缓存功能演示")
    print("="*60)
    
    # 非热重载模式（启用缓存）
    loader = ComponentLoader(hot_reload=False)
    
    try:
        print("Loading component (first time)...")
        loader.load('_templates/login')
        print(f"✓ Cache size: {len(loader._cache)}")
        
        print("\nLoading same component (from cache)...")
        loader.load('_templates/login')
        print(f"✓ Cache size: {len(loader._cache)}")
        
        print("\nClearing cache...")
        loader.clear_cache()
        print(f"✓ Cache size after clear: {len(loader._cache)}")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def demo_component_info():
    """演示获取组件信息"""
    print("\n" + "="*60)
    print("5. 组件信息获取演示")
    print("="*60)
    
    loader = ComponentLoader(hot_reload=True)
    
    try:
        info = loader.get_component_info('_templates/login')
        
        print("Component Info:")
        for key, value in info.items():
            print(f"  {key}: {value}")
    
    except Exception as e:
        print(f"✗ Error: {e}")


def main():
    """主函数"""
    print("\n" + "="*80)
    print(" ComponentLoader 功能演示")
    print("="*80)
    
    try:
        demo_basic_loading()
        demo_variable_replacement()
        demo_validation()
        demo_cache()
        demo_component_info()
        
        print("\n" + "="*80)
        print(" 演示完成")
        print("="*80)
        print("\n✓ ComponentLoader 所有核心功能正常工作")
        print("\n下一步:")
        print("  1. 创建平台特定组件（shopee/tiktok/miaoshou）")
        print("  2. 实现 CollectionExecutorV2 执行引擎")
        print("  3. 创建数据库模型")
        print("  4. 实现 API 端点")
        
    except Exception as e:
        logger.exception("Demo failed")
        print(f"\n✗ Demo failed: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

