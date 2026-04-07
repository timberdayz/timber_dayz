"""
测试MaterializedViewService字段验证方法（v4.6.0+）
不需要数据库连接，测试方法逻辑
"""
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.services.materialized_view_service import MaterializedViewService


def test_get_view_columns():
    """测试get_view_columns方法"""
    print("[测试] 测试get_view_columns方法...")
    
    # 模拟数据库会话
    db = Mock()
    
    # 模拟查询结果
    mock_result = Mock()
    mock_row1 = Mock()
    mock_row1.__getitem__ = lambda self, key: "metric_date" if key == 0 else None
    mock_row2 = Mock()
    mock_row2.__getitem__ = lambda self, key: "platform_code" if key == 0 else None
    mock_row3 = Mock()
    mock_row3.__getitem__ = lambda self, key: "platform_sku" if key == 0 else None
    
    mock_result.__iter__ = lambda self: iter([mock_row1, mock_row2, mock_row3])
    db.execute.return_value = mock_result
    
    # 测试方法
    columns = MaterializedViewService.get_view_columns(db, "test_view")
    
    # 验证结果
    assert len(columns) == 3, f"期望3个字段，实际{len(columns)}个"
    assert "metric_date" in columns, "缺少metric_date字段"
    assert "platform_code" in columns, "缺少platform_code字段"
    assert "platform_sku" in columns, "缺少platform_sku字段"
    
    print("[测试] get_view_columns方法测试通过 ✓")


def test_validate_query_fields():
    """测试validate_query_fields方法"""
    print("[测试] 测试validate_query_fields方法...")
    
    # 模拟数据库会话
    db = Mock()
    
    # 模拟get_view_columns返回的字段列表
    available_fields = ["metric_date", "platform_code", "shop_id", "platform_sku"]
    
    # 使用MagicMock来模拟get_view_columns方法
    MaterializedViewService.get_view_columns = Mock(return_value=available_fields)
    
    # 测试1: 所有字段都存在
    result1 = MaterializedViewService.validate_query_fields(
        db,
        "test_view",
        select_fields=["metric_date", "platform_code"],
        order_by_fields=["metric_date DESC"]
    )
    assert result1["valid"] == True, "字段验证应该通过"
    assert len(result1["missing_fields"]) == 0, "不应该有缺失字段"
    
    # 测试2: 有字段不存在
    result2 = MaterializedViewService.validate_query_fields(
        db,
        "test_view",
        select_fields=["metric_date", "non_existent_field"],
        order_by_fields=["another_missing_field"]
    )
    assert result2["valid"] == False, "字段验证应该失败"
    assert len(result2["missing_fields"]) > 0, "应该有缺失字段"
    assert "non_existent_field" in result2["missing_fields"], "应该包含缺失字段"
    
    # 测试3: 视图不存在
    MaterializedViewService.get_view_columns = Mock(return_value=[])
    result3 = MaterializedViewService.validate_query_fields(
        db,
        "non_existent_view",
        select_fields=["metric_date"]
    )
    assert result3["valid"] == False, "视图不存在时验证应该失败"
    assert result3["error"] is not None, "应该有错误信息"
    
    print("[测试] validate_query_fields方法测试通过 ✓")


def test_validate_view_definition():
    """测试validate_view_definition方法"""
    print("[测试] 测试validate_view_definition方法...")
    
    # 模拟数据库会话
    db = Mock()
    
    # 测试1: 视图包含metric_date字段
    MaterializedViewService.get_view_columns = Mock(return_value=["metric_date", "platform_code", "platform_sku"])
    result1 = MaterializedViewService.validate_view_definition(db, "test_view")
    assert result1["valid"] == True, "视图定义验证应该通过"
    assert result1["has_metric_date"] == True, "应该包含metric_date字段"
    
    # 测试2: 视图包含snapshot_date字段（替代metric_date）
    MaterializedViewService.get_view_columns = Mock(return_value=["snapshot_date", "platform_code", "platform_sku"])
    result2 = MaterializedViewService.validate_view_definition(db, "test_view")
    assert result2["valid"] == True, "视图定义验证应该通过（使用snapshot_date）"
    assert result2["has_metric_date"] == True, "应该识别snapshot_date为日期字段"
    
    # 测试3: 视图不包含日期字段
    MaterializedViewService.get_view_columns = Mock(return_value=["platform_code", "platform_sku"])
    result3 = MaterializedViewService.validate_view_definition(db, "test_view")
    assert result3["valid"] == False, "视图定义验证应该失败"
    assert result3["has_metric_date"] == False, "不应该包含日期字段"
    assert result3["error"] is not None, "应该有错误信息"
    
    # 测试4: 视图不存在
    MaterializedViewService.get_view_columns = Mock(return_value=[])
    result4 = MaterializedViewService.validate_view_definition(db, "non_existent_view")
    assert result4["valid"] == False, "视图不存在时验证应该失败"
    
    print("[测试] validate_view_definition方法测试通过 ✓")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("MaterializedViewService字段验证方法测试")
    print("=" * 60)
    
    try:
        test_get_view_columns()
        test_validate_query_fields()
        test_validate_view_definition()
        
        print("=" * 60)
        print("[成功] 所有测试通过 ✓")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"[失败] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"[错误] 测试执行出错: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

