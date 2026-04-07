#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
添加规格字段并修复映射
"""

import sys
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine
from sqlalchemy import text

def main():
    print("=== Adding Specification Field ===\n")

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            # Step 1: Add specification column to fact_product_metrics
            print("--- Step 1: Adding specification column ---")
            check_result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'fact_product_metrics'
                    AND column_name = 'specification';
            """))
            
            if check_result.fetchone():
                print("  [SKIP] specification column already exists")
            else:
                conn.execute(text("""
                    ALTER TABLE fact_product_metrics
                    ADD COLUMN specification VARCHAR(256) NULL;
                """))
                print("  [ADDED] specification column (VARCHAR(256))")
            
            # Step 2: Add standard specification mapping
            print("\n--- Step 2: Adding standard specification mapping ---")
            
            # Check if standard 'specification' mapping exists
            check_result = conn.execute(text("""
                SELECT id
                FROM field_mapping_dictionary
                WHERE field_code = 'specification' AND data_domain = 'products';
            """))
            
            if check_result.fetchone():
                print("  [SKIP] specification mapping already exists")
            else:
                synonyms = [
                    "规格", "*规格", "产品规格", "specification", 
                    "variant", "variant_name", "sku_variant"
                ]
                synonyms_json = json.dumps(synonyms, ensure_ascii=False)
                
                conn.execute(text(f"""
                    INSERT INTO field_mapping_dictionary
                    (field_code, cn_name, en_name, data_domain, field_group,
                     is_required, data_type, description, synonyms,
                     active, created_by, created_at)
                    VALUES
                    ('specification', '规格', 'Specification', 'products', 'dimension',
                     false, 'string', '产品规格描述（颜色、尺寸等），如：silver S 35cmX5cm', 
                     '{synonyms_json}'::jsonb,
                     true, 'system', NOW())
                """))
                print("  [ADDED] specification mapping")
            
            # Step 3: Delete c68_c84_1 and other non-standard mappings
            print("\n--- Step 3: Deleting non-standard specification mappings ---")
            
            non_standard_fields = ['c68_c84_1']
            
            deleted_count = 0
            for old_code in non_standard_fields:
                check_result = conn.execute(text("""
                    SELECT id, cn_name
                    FROM field_mapping_dictionary
                    WHERE field_code = :code AND data_domain = 'products';
                """), {"code": old_code})
                
                old_entry = check_result.fetchone()
                if old_entry:
                    conn.execute(text("""
                        DELETE FROM field_mapping_dictionary
                        WHERE field_code = :code AND data_domain = 'products';
                    """), {"code": old_code})
                    print(f"  [DELETED] {old_code} (CN: {old_entry[1]})")
                    deleted_count += 1
                else:
                    print(f"  [SKIP] {old_code} not found")
            
            trans.commit()
            print(f"\n[OK] Specification field added. Deleted {deleted_count} non-standard mappings.")
            
        except Exception as e:
            trans.rollback()
            print(f"\n[ERROR] {e}")
            print("[ROLLBACK] Transaction rolled back.")
            import traceback
            traceback.print_exc()

    # Verification
    print("\n--- Verification ---")
    with engine.connect() as conn:
        # Check table column
        result = conn.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'fact_product_metrics'
                AND column_name = 'specification';
        """))
        row = result.fetchone()
        if row:
            print(f"  [OK] Table column: {row[0]} ({row[1]})")
        
        # Check mapping
        result = conn.execute(text("""
            SELECT field_code, cn_name, en_name, synonyms
            FROM field_mapping_dictionary
            WHERE field_code = 'specification' AND data_domain = 'products';
        """))
        row = result.fetchone()
        if row:
            print(f"  [OK] Mapping: {row[0]} ({row[1]})")
            print(f"    EN: {row[2]}")
            print(f"    Synonyms: {row[3]}")

    print("\n=== Process Complete ===")

if __name__ == "__main__":
    main()

