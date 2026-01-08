#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新"运营人员"角色描述脚本

修正错误的描述："默认运营角色，用于新用户审批"
改为："日常操作人员角色，用于数据采集和业务操作"

执行方式:
    python scripts/update_operator_role_description.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings
from modules.core.logger import get_logger

logger = get_logger(__name__)

def update_operator_role_description():
    """更新运营人员角色描述"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                # 检查当前描述
                result = conn.execute(text("""
                    SELECT role_id, role_name, role_code, description 
                    FROM dim_roles 
                    WHERE role_code = 'operator' AND role_name = '运营人员'
                """))
                role = result.fetchone()
                
                if not role:
                    logger.warning("未找到 role_code='operator' 且 role_name='运营人员' 的角色")
                    return False
                
                current_desc = role[3]
                logger.info(f"当前描述: {current_desc}")
                
                # 更新描述
                if '用于新用户审批' in current_desc:
                    conn.execute(text("""
                        UPDATE dim_roles 
                        SET description = '日常操作人员角色，用于数据采集和业务操作',
                            updated_at = NOW()
                        WHERE role_code = 'operator' 
                          AND role_name = '运营人员'
                    """))
                    trans.commit()
                    logger.info("[OK] 运营人员角色描述已更新")
                    
                    # 验证更新结果
                    result = conn.execute(text("""
                        SELECT role_id, role_name, role_code, description, updated_at 
                        FROM dim_roles 
                        WHERE role_code = 'operator'
                    """))
                    updated_role = result.fetchone()
                    logger.info(f"更新后描述: {updated_role[3]}")
                    return True
                else:
                    logger.info("描述已正确，无需更新")
                    trans.rollback()
                    return True
                    
            except Exception as e:
                trans.rollback()
                logger.error(f"[ERROR] 更新失败: {e}", exc_info=True)
                return False
                
    except Exception as e:
        logger.error(f"[ERROR] 数据库连接失败: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    logger.info("开始更新运营人员角色描述...")
    success = update_operator_role_description()
    if success:
        logger.info("[完成] 运营人员角色描述更新完成")
        sys.exit(0)
    else:
        logger.error("[失败] 运营人员角色描述更新失败")
        sys.exit(1)
