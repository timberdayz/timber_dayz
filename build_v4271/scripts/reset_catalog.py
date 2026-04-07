#!/usr/bin/env python3
"""重置catalog_files表"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.begin() as conn:
        # 清空catalog_files表
        result = conn.execute(text("DELETE FROM catalog_files"))
        print(f"[OK] 删除了{result.rowcount}条旧记录")
        
        print("[OK] catalog_files表已重置")

