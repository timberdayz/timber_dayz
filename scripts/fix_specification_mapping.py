#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复规格字段映射
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
    print("=== Fixing Specification Field Mapping ===\n")

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            # Step 1: Add specification column to fact_product_metrics (if not exists)
            print("--- Step 1: Adding specification column ---")
            check_result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'fact_product_metrics'
                    AND column_name = 'specification';
            """))
            
            if check_result.fetchone():
                print("  [OK] specification column already exists")
            else:
                conn.execute(text("""
                    ALTER TABLE fact_product_metrics
                    ADD COLUMN specification VARCHAR(256) NULL;
                """))
                print("  [ADDED] specification column (VARCHAR(256))")
            
            # Step 2: Check existing specification mappings
            print("\n--- Step 2: Checking existing specification mappings ---")
            result = conn.execute(text("""
                SELECT id, field_code, cn_name, en_name, data_domain, synonyms
                FROM field_mapping_dictionary
                WHERE field_code = 'specification' OR field_code = 'c68_c84_1'
                ORDER BY data_domain, id;
            """))
            
            existing_mappings = result.fetchall()
            for row in existing_mappings:
                print(f"  ID: {row[0]}, Code: {row[1]}, CN: {row[2]}, Domain: {row[4]}")
            
            # Step 3: Update or add products domain specification mapping
            print("\n--- Step 3: Ensuring products domain has specification mapping ---")
            
            # Check if products domain has specification
            check_result = conn.execute(text("""
                SELECT id, synonyms
                FROM field_mapping_dictionary
                WHERE field_code = 'specification' AND data_domain = 'products';
            """))
            
            products_spec = check_result.fetchone()
            
            if products_spec:
                # Update synonyms
                print(f"  [EXISTS] specification in products domain (ID: {products_spec[0]})")
                print("  [UPDATE] Updating synonyms...")
                
                current_synonyms = products_spec[1] if products_spec[1] else []
                if isinstance(current_synonyms, str):
                    current_synonyms = json.loads(current_synonyms)
                elif not isinstance(current_synonyms, list):
                    current_synonyms = []
                
                new_synonyms = [
                    "规格", "*规格", "产品规格", "specification", 
                    "variant", "variant_name", "sku_variant"
                ]
                
                # Merge and deduplicate
                all_synonyms = list(set(current_synonyms + new_synonyms))
                synonyms_json = json.dumps(all_synonyms, ensure_ascii=False)
                
                conn.execute(text(f"""
                    UPDATE field_mapping_dictionary
                    SET synonyms = '{synonyms_json}'::jsonb,
                        updated_at = NOW()
                    WHERE field_code = 'specification' AND data_domain = 'products';
                """))
                print(f"  [UPDATED] synonyms")
            else:
                # Add new mapping for products domain
                print("  [ADD] Creating specification mapping for products domain")
                
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
                print("  [ADDED] specification mapping for products domain")
            
            # Step 4: Delete c68_c84_1
            print("\n--- Step 4: Deleting c68_c84_1 mapping ---")
            check_result = conn.execute(text("""
                SELECT id, cn_name
                FROM field_mapping_dictionary
                WHERE field_code = 'c68_c84_1' AND data_domain = 'products';
            """))
            
            old_entry = check_result.fetchone()
            if old_entry:
                conn.execute(text("""
                    DELETE FROM field_mapping_dictionary
                    WHERE field_code = 'c68_c84_1' AND data_domain = 'products';
                """))
                print(f"  [DELETED] c68_c84_1 (CN: {old_entry[1]})")
            else:
                print("  [SKIP] c68_c84_1 not found")
            
            trans.commit()
            print("\n[OK] Specification field mapping fixed.")
            
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
        else:
            print(f"  [WARNING] specification column not found")
        
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
        else:
            print(f"  [WARNING] specification mapping not found in products domain")
        
        # Check c68_c84_1 is deleted
        result = conn.execute(text("""
            SELECT id
            FROM field_mapping_dictionary
            WHERE field_code = 'c68_c84_1';
        """))
        if result.fetchone():
            print(f"  [WARNING] c68_c84_1 still exists!")
        else:
            print(f"  [OK] c68_c84_1 deleted")

    print("\n=== Process Complete ===")

if __name__ == "__main__":
    main()

