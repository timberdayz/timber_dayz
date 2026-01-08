"""
配方优化器

优化录制生成的配方，去除重复步骤，提高执行效率
"""

import json
from pathlib import Path
from typing import Dict, List, Any


class RecipeOptimizer:
    """配方优化器"""
    
    def __init__(self):
        pass
    
    def optimize_recipe(self, recipe_path: Path) -> bool:
        """
        优化配方文件

        Args:
            recipe_path: 配方文件路径

        Returns:
            bool: 优化是否成功
        """
        try:
            from modules.utils.logger import logger
            if not recipe_path.exists():
                logger.error(f"配方文件不存在: {recipe_path}")
                return False
            
            # 加载原始配方
            original_recipe = json.loads(recipe_path.read_text(encoding='utf-8'))
            logger.info(f"[BOOK] 加载原始配方: {len(original_recipe.get('steps', []))} 个步骤")
            
            # 优化步骤
            optimized_steps = self._optimize_steps(original_recipe.get('steps', []))
            
            # 创建优化后的配方
            optimized_recipe = original_recipe.copy()
            optimized_recipe['steps'] = optimized_steps
            optimized_recipe['optimized'] = True
            optimized_recipe['optimization_info'] = {
                'original_steps': len(original_recipe.get('steps', [])),
                'optimized_steps': len(optimized_steps),
                'removed_duplicates': len(original_recipe.get('steps', [])) - len(optimized_steps)
            }
            
            # 保存优化后的配方
            optimized_path = recipe_path.parent / f"{recipe_path.stem}_optimized.json"
            optimized_path.write_text(
                json.dumps(optimized_recipe, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            
            logger.info(f"[OK] 配方优化完成: {optimized_path}")
            logger.info(f"   原始步骤: {len(original_recipe.get('steps', []))}")
            logger.info(f"   优化步骤: {len(optimized_steps)}")
            logger.info(f"   移除重复: {len(original_recipe.get('steps', [])) - len(optimized_steps)}")
            
            return True
            
        except Exception as e:
            logger.error(f"配方优化失败: {e}")
            return False
    
    def _optimize_steps(self, steps: List[Dict]) -> List[Dict]:
        """优化步骤列表"""
        if not steps:
            return []
        
        optimized = []
        seen_actions = set()
        
        for step in steps:
            action = step.get('action', '')
            description = step.get('description', '')
            
            # 创建唯一标识
            action_key = f"{action}:{description}"
            
            # 跳过重复的操作
            if action_key in seen_actions:
                logger.debug(f"跳过重复步骤: {description}")
                continue
            
            # 优化候选选择器
            optimized_candidates = self._optimize_candidates(step.get('candidates', []))
            
            # 创建优化后的步骤
            optimized_step = step.copy()
            optimized_step['step_id'] = len(optimized) + 1
            optimized_step['candidates'] = optimized_candidates
            
            optimized.append(optimized_step)
            seen_actions.add(action_key)
        
        return optimized
    
    def _optimize_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """优化候选选择器列表"""
        if not candidates:
            return []
        
        # 去重并按优先级排序
        seen_selectors = set()
        unique_candidates = []
        
        for candidate in candidates:
            selector_type = candidate.get('type', '')
            selector_value = candidate.get('value', '')
            
            # 创建选择器唯一标识
            selector_key = f"{selector_type}:{selector_value}"
            
            if selector_key not in seen_selectors:
                unique_candidates.append(candidate)
                seen_selectors.add(selector_key)
        
        # 按优先级排序
        return sorted(unique_candidates, key=lambda x: x.get('priority', 999))
    
    def create_simplified_recipe(self, recipe_path: Path, target_action: str = "select_past_7_days") -> bool:
        """
        创建简化的专用配方

        Args:
            recipe_path: 原始配方文件路径
            target_action: 目标操作类型

        Returns:
            bool: 创建是否成功
        """
        try:
            from modules.utils.logger import logger
            if not recipe_path.exists():
                logger.error(f"配方文件不存在: {recipe_path}")
                return False
            
            # 加载原始配方
            original_recipe = json.loads(recipe_path.read_text(encoding='utf-8'))
            
            # 创建简化配方
            simplified_recipe = {
                "page_key": "datacenter/product/performance",
                "generated_at": original_recipe.get('generated_at', ''),
                "url_pattern": "*/datacenter/product/performance*",
                "action_type": target_action,
                "description": "选择过去7天的简化配方",
                "steps": [
                    {
                        "step_id": 1,
                        "action": "open_picker",
                        "description": "打开日期选择器",
                        "candidates": [
                            {
                                "type": "css",
                                "value": ".bi-date-input.track-click-open-time-selector",
                                "priority": 1
                            },
                            {
                                "type": "css",
                                "value": ".value",
                                "priority": 2
                            },
                            {
                                "type": "text",
                                "value": "今天至",
                                "priority": 3
                            }
                        ]
                    },
                    {
                        "step_id": 2,
                        "action": "select_shortcut",
                        "description": "选择过去7天",
                        "candidates": [
                            {
                                "type": "text",
                                "value": "过去7 天",
                                "priority": 1
                            },
                            {
                                "type": "css",
                                "value": ".eds-date-shortcut-item__text",
                                "priority": 2
                            },
                            {
                                "type": "css",
                                "value": "li:has-text('过去7 天')",
                                "priority": 3
                            }
                        ]
                    }
                ]
            }
            
            # 保存简化配方
            simplified_path = recipe_path.parent / f"{recipe_path.stem}_simplified.json"
            simplified_path.write_text(
                json.dumps(simplified_recipe, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            
            logger.info(f"[OK] 简化配方创建完成: {simplified_path}")
            logger.info(f"   简化为 {len(simplified_recipe['steps'])} 个核心步骤")
            
            return True
            
        except Exception as e:
            logger.error(f"简化配方创建失败: {e}")
            return False


def optimize_latest_recipe():
    """优化最新的配方文件（便捷函数）"""
    import glob
    import os
    from modules.utils.logger import logger
    
    # 查找最新的配方文件
    pattern = os.path.join('temp', 'outputs', 'shopee', '**', 'products', 'weekly', '.diag', 'recipes', 'date_picker.json')
    candidates = glob.glob(pattern, recursive=True)
    
    if not candidates:
        logger.error("未找到配方文件")
        return False
    
    latest_path = Path(max(candidates, key=lambda p: os.path.getmtime(p)))
    
    optimizer = RecipeOptimizer()
    
    # 创建优化版本
    success1 = optimizer.optimize_recipe(latest_path)
    
    # 创建简化版本
    success2 = optimizer.create_simplified_recipe(latest_path)
    
    return success1 and success2


if __name__ == "__main__":
    import sys
    from pathlib import Path

    # 添加项目根目录到路径
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    optimize_latest_recipe()
