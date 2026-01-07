"""
字段映射模板缓存服务
支持智能模板缓存和快速匹配
"""

import json
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from sqlalchemy.orm import Session

from backend.models.database import FieldMapping

class TemplateCache:
    """字段映射模板缓存"""
    
    def __init__(self, cache_file: str = "temp/cache/field_mapping_templates.db"):
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._init_cache_db()
    
    def _init_cache_db(self):
        """初始化缓存数据库"""
        conn = sqlite3.connect(str(self.cache_file))
        cursor = conn.cursor()
        
        # 创建模板缓存表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS template_cache (
                cache_key TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                domain TEXT NOT NULL,
                granularity TEXT,
                sheet_name TEXT,
                template_data TEXT NOT NULL,
                confidence_score REAL DEFAULT 0.0,
                hit_count INTEGER DEFAULT 0,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_template_platform_domain 
            ON template_cache(platform, domain)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_template_last_used 
            ON template_cache(last_used)
        """)
        
        conn.commit()
        conn.close()
    
    def _generate_cache_key(self, platform: str, domain: str, 
                          granularity: Optional[str] = None, 
                          sheet_name: Optional[str] = None) -> str:
        """生成缓存键"""
        key_parts = [platform, domain]
        if granularity:
            key_parts.append(granularity)
        if sheet_name:
            key_parts.append(sheet_name)
        
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get_template(self, platform: str, domain: str, 
                    granularity: Optional[str] = None,
                    sheet_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取模板缓存"""
        cache_key = self._generate_cache_key(platform, domain, granularity, sheet_name)
        
        conn = sqlite3.connect(str(self.cache_file))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT template_data, confidence_score, hit_count
            FROM template_cache 
            WHERE cache_key = ?
        """, (cache_key,))
        
        row = cursor.fetchone()
        if row:
            template_data, confidence_score, hit_count = row
            
            # 更新命中次数和最后使用时间
            cursor.execute("""
                UPDATE template_cache 
                SET hit_count = hit_count + 1, last_used = CURRENT_TIMESTAMP
                WHERE cache_key = ?
            """, (cache_key,))
            conn.commit()
            
            conn.close()
            
            return {
                "template": json.loads(template_data),
                "confidence_score": confidence_score,
                "hit_count": hit_count + 1,
                "source": "cache"
            }
        
        conn.close()
        return None
    
    def save_template(self, platform: str, domain: str, 
                     template: Dict[str, Any],
                     granularity: Optional[str] = None,
                     sheet_name: Optional[str] = None,
                     confidence_score: float = 1.0) -> str:
        """保存模板到缓存"""
        cache_key = self._generate_cache_key(platform, domain, granularity, sheet_name)
        
        conn = sqlite3.connect(str(self.cache_file))
        cursor = conn.cursor()
        
        # 检查是否已存在
        cursor.execute("SELECT cache_key FROM template_cache WHERE cache_key = ?", (cache_key,))
        exists = cursor.fetchone()
        
        if exists:
            # 更新现有模板
            cursor.execute("""
                UPDATE template_cache 
                SET template_data = ?, confidence_score = ?, last_used = CURRENT_TIMESTAMP
                WHERE cache_key = ?
            """, (json.dumps(template), confidence_score, cache_key))
        else:
            # 插入新模板
            cursor.execute("""
                INSERT INTO template_cache 
                (cache_key, platform, domain, granularity, sheet_name, template_data, confidence_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (cache_key, platform, domain, granularity, sheet_name, 
                  json.dumps(template), confidence_score))
        
        conn.commit()
        conn.close()
        
        return cache_key
    
    def find_similar_templates(self, platform: str, domain: str, 
                              columns: List[str]) -> List[Dict[str, Any]]:
        """查找相似模板（基于列名匹配）"""
        conn = sqlite3.connect(str(self.cache_file))
        cursor = conn.cursor()
        
        # 查询同平台同域的模板
        cursor.execute("""
            SELECT cache_key, template_data, confidence_score, hit_count, last_used
            FROM template_cache 
            WHERE platform = ? AND domain = ?
            ORDER BY confidence_score DESC, hit_count DESC, last_used DESC
        """, (platform, domain))
        
        similar_templates = []
        for row in cursor.fetchall():
            cache_key, template_data, confidence_score, hit_count, last_used = row
            template = json.loads(template_data)
            
            # 计算列名匹配度
            template_columns = set(template.keys())
            input_columns = set(columns)
            
            # 计算交集比例
            intersection = len(template_columns.intersection(input_columns))
            union = len(template_columns.union(input_columns))
            match_ratio = intersection / union if union > 0 else 0
            
            if match_ratio > 0.3:  # 至少30%匹配
                similar_templates.append({
                    "cache_key": cache_key,
                    "template": template,
                    "confidence_score": confidence_score,
                    "hit_count": hit_count,
                    "match_ratio": match_ratio,
                    "last_used": last_used
                })
        
        conn.close()
        
        # 按匹配度和置信度排序
        similar_templates.sort(key=lambda x: (x["match_ratio"], x["confidence_score"]), reverse=True)
        return similar_templates[:5]  # 返回前5个最相似的
    
    def cleanup_expired_templates(self, days: int = 30):
        """清理过期模板"""
        conn = sqlite3.connect(str(self.cache_file))
        cursor = conn.cursor()
        
        cutoff_date = datetime.now() - timedelta(days=days)
        cursor.execute("""
            DELETE FROM template_cache 
            WHERE last_used < ?
        """, (cutoff_date,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        conn = sqlite3.connect(str(self.cache_file))
        cursor = conn.cursor()
        
        # 总模板数
        cursor.execute("SELECT COUNT(*) FROM template_cache")
        total_templates = cursor.fetchone()[0]
        
        # 按平台统计
        cursor.execute("""
            SELECT platform, COUNT(*) as count 
            FROM template_cache 
            GROUP BY platform 
            ORDER BY count DESC
        """)
        platform_stats = dict(cursor.fetchall())
        
        # 按域统计
        cursor.execute("""
            SELECT domain, COUNT(*) as count 
            FROM template_cache 
            GROUP BY domain 
            ORDER BY count DESC
        """)
        domain_stats = dict(cursor.fetchall())
        
        # 最热门的模板
        cursor.execute("""
            SELECT platform, domain, hit_count 
            FROM template_cache 
            ORDER BY hit_count DESC 
            LIMIT 10
        """)
        top_templates = cursor.fetchall()
        
        conn.close()
        
        return {
            "total_templates": total_templates,
            "platform_stats": platform_stats,
            "domain_stats": domain_stats,
            "top_templates": top_templates
        }

# 全局缓存实例
_template_cache = None

def get_template_cache() -> TemplateCache:
    """获取模板缓存实例"""
    global _template_cache
    if _template_cache is None:
        _template_cache = TemplateCache()
    return _template_cache

def clear_template_cache():
    """清空模板缓存"""
    global _template_cache
    _template_cache = None
