"""
测试自适应等待功能（Phase 2.5.4.2）

验证CollectionExecutorV2._smart_wait_for_element方法
"""

import sys
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.apps.collection_center.executor_v2 import CollectionExecutorV2
from modules.apps.collection_center.popup_handler import UniversalPopupHandler


async def test_smart_wait_immediate_success():
    """测试：元素立即存在（策略1成功）"""
    print("[TEST] Smart wait - immediate success")
    
    # 创建mock对象
    page = AsyncMock()
    page.wait_for_selector = AsyncMock(return_value=True)
    
    popup_handler = Mock(spec=UniversalPopupHandler)
    
    # 创建executor
    executor = CollectionExecutorV2(
        platform="test",
        account_id="test_001",
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-01"},
        granularity="daily"
    )
    executor.popup_handler = popup_handler
    
    # 执行自适应等待
    result = await executor._smart_wait_for_element(
        page, 
        "div.test-element", 
        max_timeout=30000
    )
    
    # 验证
    assert result == True
    assert page.wait_for_selector.call_count == 1  # 只调用一次（策略1）
    print("[OK] Element found immediately")


async def test_smart_wait_after_popup():
    """测试：关闭弹窗后找到元素（策略2成功）"""
    print("[TEST] Smart wait - success after closing popup")
    
    # 创建mock对象
    page = AsyncMock()
    
    # 第1次失败（快速检测），第2次成功（关闭弹窗后）
    call_count = 0
    async def mock_wait_for_selector(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Timeout")  # 策略1失败
        return True  # 策略2成功
    
    page.wait_for_selector = mock_wait_for_selector
    
    popup_handler = AsyncMock(spec=UniversalPopupHandler)
    popup_handler.close_popups = AsyncMock()
    
    # 创建executor
    executor = CollectionExecutorV2(
        platform="test",
        account_id="test_001",
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-01"},
        granularity="daily"
    )
    executor.popup_handler = popup_handler
    
    # 执行自适应等待
    result = await executor._smart_wait_for_element(
        page, 
        "div.test-element", 
        max_timeout=30000
    )
    
    # 验证
    assert result == True
    assert popup_handler.close_popups.called  # 调用了关闭弹窗
    print("[OK] Element found after closing popups")


async def test_smart_wait_timeout():
    """测试：所有策略都失败（超时）"""
    print("[TEST] Smart wait - all strategies fail")
    
    # 创建mock对象
    page = AsyncMock()
    page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))
    page.wait_for_load_state = AsyncMock(side_effect=Exception("Timeout"))
    
    popup_handler = AsyncMock(spec=UniversalPopupHandler)
    popup_handler.close_popups = AsyncMock()
    
    # 创建executor
    executor = CollectionExecutorV2(
        platform="test",
        account_id="test_001",
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-01"},
        granularity="daily"
    )
    executor.popup_handler = popup_handler
    
    # 执行自适应等待（应该抛出异常）
    try:
        await executor._smart_wait_for_element(
            page, 
            "div.nonexistent-element", 
            max_timeout=5000  # 短超时用于测试
        )
        assert False, "Should have raised exception"
    except Exception as e:
        assert "All smart wait strategies failed" in str(e) or "Smart wait timeout" in str(e)
        print(f"[OK] Timeout as expected: {e}")


async def test_smart_wait_integration():
    """测试：wait动作集成smart_wait参数"""
    print("[TEST] Smart wait - integration with wait action")
    
    # 创建mock对象
    page = AsyncMock()
    page.wait_for_selector = AsyncMock(return_value=True)
    
    popup_handler = Mock(spec=UniversalPopupHandler)
    
    # 创建executor
    executor = CollectionExecutorV2(
        platform="test",
        account_id="test_001",
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-01"},
        granularity="daily"
    )
    executor.popup_handler = popup_handler
    
    # 测试步骤（使用smart_wait）
    step = {
        "action": "wait",
        "type": "selector",
        "selector": "div.test-element",
        "smart_wait": True,
        "timeout": 30000
    }
    
    component = {"platform": "test"}
    
    # 执行步骤
    await executor._execute_step(page, step, component)
    
    # 验证：应该调用了wait_for_selector（策略1）
    assert page.wait_for_selector.called
    print("[OK] Smart wait integrated with wait action")


async def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Testing Smart Wait (Phase 2.5.4.2)")
    print("=" * 60)
    print()
    
    try:
        await test_smart_wait_immediate_success()
        await test_smart_wait_after_popup()
        await test_smart_wait_timeout()
        await test_smart_wait_integration()
        
        print()
        print("=" * 60)
        print("[SUCCESS] All 4 tests passed!")
        print("=" * 60)
        
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


if __name__ == "__main__":
    asyncio.run(run_all_tests())

