"""
物化视图依赖关系分析脚本
执行：python scripts/analyze_mv_dependencies.py

功能：
1. 分析物化视图的依赖关系
2. 生成依赖关系图
3. 验证刷新顺序
4. 检测循环依赖

v4.9.2新增
"""
import sys
from pathlib import Path
import re

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def extract_table_dependencies(sql_definition):
    """从SQL定义中提取依赖的表/视图"""
    dependencies = set()
    
    # 查找FROM和JOIN子句
    pattern = r'(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)'
    matches = re.findall(pattern, sql_definition, re.IGNORECASE)
    
    for match in matches:
        # 排除子查询和关键字
        if match.lower() not in ('select', 'where', 'group', 'order', 'having'):
            dependencies.add(match)
    
    return dependencies

def analyze_mv_dependencies():
    """分析物化视图依赖关系"""
    db = SessionLocal()
    
    try:
        logger.info("=" * 60)
        logger.info("[依赖分析] 物化视图依赖关系分析")
        logger.info("=" * 60)
        
        # 获取所有物化视图
        result = db.execute(text("""
            SELECT matviewname, definition
            FROM pg_matviews
            WHERE schemaname = 'public'
            ORDER BY matviewname
        """))
        
        views_info = {}
        for row in result:
            view_name, definition = row[0], row[1]
            dependencies = extract_table_dependencies(definition)
            views_info[view_name] = {
                'dependencies': dependencies,
                'dependent_mvs': set(),  # 依赖的其他物化视图
                'dependent_tables': set()  # 依赖的普通表
            }
            
            # 分类依赖
            for dep in dependencies:
                if dep.startswith('mv_'):
                    views_info[view_name]['dependent_mvs'].add(dep)
                else:
                    views_info[view_name]['dependent_tables'].add(dep)
        
        # 1. 显示依赖关系
        logger.info("\n[1] 视图依赖关系:")
        for view_name, info in sorted(views_info.items()):
            logger.info(f"\n  {view_name}:")
            if info['dependent_tables']:
                logger.info(f"    [源表] {', '.join(sorted(info['dependent_tables']))}")
            if info['dependent_mvs']:
                logger.info(f"    [依赖视图] {', '.join(sorted(info['dependent_mvs']))}")
            if not info['dependencies']:
                logger.info("    [独立视图] 无依赖")
        
        # 2. 计算依赖层级（用于确定刷新顺序）
        logger.info("\n[2] 依赖层级分析:")
        
        layers = {}
        processed = set()
        
        # 第0层：无物化视图依赖的视图（只依赖普通表）
        layer_0 = [v for v, info in views_info.items() if not info['dependent_mvs']]
        layers[0] = layer_0
        processed.update(layer_0)
        logger.info(f"  第0层（基础视图，{len(layer_0)}个）:")
        for v in sorted(layer_0):
            logger.info(f"    - {v}")
        
        # 后续层：依赖已处理视图的视图
        current_layer = 1
        while len(processed) < len(views_info):
            layer_n = []
            for v, info in views_info.items():
                if v not in processed:
                    # 所有依赖的MV都已处理
                    if info['dependent_mvs'].issubset(processed):
                        layer_n.append(v)
            
            if not layer_n:
                # 检测到循环依赖
                remaining = set(views_info.keys()) - processed
                logger.error(f"\n  [ERROR] 检测到循环依赖或孤立视图:")
                for v in remaining:
                    logger.error(f"    - {v} 依赖: {views_info[v]['dependent_mvs']}")
                break
            
            layers[current_layer] = layer_n
            processed.update(layer_n)
            logger.info(f"\n  第{current_layer}层（派生视图，{len(layer_n)}个）:")
            for v in sorted(layer_n):
                logger.info(f"    - {v} ← 依赖: {', '.join(sorted(views_info[v]['dependent_mvs']))}")
            
            current_layer += 1
        
        # 3. 生成推荐刷新顺序
        logger.info("\n[3] 推荐刷新顺序:")
        refresh_order = []
        for layer_num in sorted(layers.keys()):
            refresh_order.extend(sorted(layers[layer_num]))
        
        logger.info("  刷新顺序（按层级）:")
        for i, view in enumerate(refresh_order, 1):
            layer = [k for k, v in layers.items() if view in v][0]
            logger.info(f"    {i:2d}. {view} (Layer {layer})")
        
        # 4. Python代码输出
        logger.info("\n[4] Python代码（可复制到MaterializedViewService）:")
        logger.info(f"\nREFRESH_ORDER = {refresh_order}")
        
        logger.info("\n" + "=" * 60)
        logger.info("[完成] 依赖分析完成")
        logger.info("=" * 60)
        
        return {
            "views": views_info,
            "layers": layers,
            "refresh_order": refresh_order
        }
        
    except Exception as e:
        logger.error(f"[ERROR] 分析失败: {e}", exc_info=True)
        return None
    finally:
        db.close()

if __name__ == "__main__":
    result = analyze_mv_dependencies()
    sys.exit(0 if result else 1)

