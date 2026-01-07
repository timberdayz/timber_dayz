"""
物化视图字段验证测试脚本（v4.6.0+）
验证物化视图查询返回期望的字段

使用方法:
    python scripts/test_materialized_view_fields.py [view_name]
    
如果不指定view_name，将测试所有视图
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from backend.services.materialized_view_service import MaterializedViewService
from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_view_fields(view_name: str):
    """
    测试视图字段
    
    Args:
        view_name: 视图名称
    """
    from sqlalchemy import text
    
    db = SessionLocal()
    try:
        logger.info(f"[测试视图字段] 开始测试视图: {view_name}")
        
        # 1. 验证视图定义
        definition_result = MaterializedViewService.validate_view_definition(db, view_name)
        if not definition_result["valid"]:
            logger.error(f"[测试视图字段] 视图定义验证失败: {definition_result.get('error')}")
            return False
        
        logger.info(f"[测试视图字段] 视图定义验证通过: 包含 {len(definition_result['columns'])} 个字段")
        logger.info(f"[测试视图字段] 包含metric_date字段: {definition_result['has_metric_date']}")
        
        # 2. 测试查询字段验证
        # 示例：验证常用查询字段
        common_fields = ["metric_date", "platform_code", "shop_id", "platform_sku"]
        validation_result = MaterializedViewService.validate_query_fields(
            db, view_name, select_fields=common_fields
        )
        
        if not validation_result["valid"]:
            logger.warning(f"[测试视图字段] 字段验证失败: {validation_result.get('error')}")
            logger.info(f"[测试视图字段] 可用字段: {validation_result.get('available_fields', [])}")
        else:
            logger.info(f"[测试视图字段] 字段验证通过")
        
        # 3. 测试实际查询（如果视图有数据）
        try:
            test_query = f"SELECT * FROM {view_name} LIMIT 1"
            result = db.execute(text(test_query))
            row = result.fetchone()
            if row:
                logger.info(f"[测试视图字段] 查询测试成功: 返回 {len(row._mapping)} 个字段")
            else:
                logger.warning(f"[测试视图字段] 视图无数据")
        except Exception as e:
            logger.warning(f"[测试视图字段] 查询测试失败: {e}")
        
        return True
    except Exception as e:
        logger.error(f"[测试视图字段] 测试失败: {e}", exc_info=True)
        return False
    finally:
        db.close()


def test_all_views():
    """测试所有视图"""
    from sqlalchemy import text
    
    db = SessionLocal()
    try:
        # 获取所有物化视图
        all_views = db.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public'
            ORDER BY matviewname
        """)).fetchall()
        
        view_names = [row[0] for row in all_views]
        logger.info(f"[测试视图字段] 找到 {len(view_names)} 个视图: {', '.join(view_names)}")
        
        results = []
        for view_name in view_names:
            success = test_view_fields(view_name)
            results.append({"view_name": view_name, "success": success})
        
        # 汇总结果
        success_count = sum(1 for r in results if r["success"])
        logger.info(f"[测试视图字段] 测试完成: {success_count}/{len(results)} 个视图通过")
        
        return results
    except Exception as e:
        logger.error(f"[测试视图字段] 获取视图列表失败: {e}", exc_info=True)
        return []
    finally:
        db.close()


def main():
    """主函数"""
    from sqlalchemy import text
    
    view_name = sys.argv[1] if len(sys.argv) > 1 else None
    
    if view_name:
        logger.info(f"[测试视图字段] 测试指定视图: {view_name}")
        success = test_view_fields(view_name)
        sys.exit(0 if success else 1)
    else:
        logger.info("[测试视图字段] 测试所有视图")
        results = test_all_views()
        success_count = sum(1 for r in results if r["success"])
        sys.exit(0 if success_count == len(results) else 1)


if __name__ == "__main__":
    main()

