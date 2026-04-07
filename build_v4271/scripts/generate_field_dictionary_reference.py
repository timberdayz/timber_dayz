#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成字段辞典内容对照表

这个脚本会：
1. 从数据库读取所有标准字段
2. 生成格式化的对照表（Markdown格式）
3. 包含字段代码、中文名称、英文名称、同义词、数据域等信息
4. 便于检查和发现映射问题
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from modules.core.logger import get_logger
from sqlalchemy import text

logger = get_logger(__name__)


def generate_field_dictionary_report():
    """生成字段辞典对照表"""
    db = next(get_db())
    try:
        # 查询所有标准字段，按数据域和字段组排序
        result = db.execute(text("""
            SELECT 
                field_code,
                cn_name,
                en_name,
                description,
                data_domain,
                field_group,
                synonyms,
                platform_synonyms,
                is_required,
                data_type,
                display_order
            FROM field_mapping_dictionary
            WHERE active = true
            ORDER BY 
                data_domain NULLS LAST,
                field_group NULLS LAST,
                display_order NULLS LAST,
                field_code
        """))
        
        fields = result.fetchall()
        
        # 按数据域分组
        domains = {}
        for field in fields:
            domain = field[4] or 'general'  # data_domain
            if domain not in domains:
                domains[domain] = []
            domains[domain].append(field)
        
        # 生成Markdown内容
        md_content = generate_markdown(domains, len(fields))
        
        # 保存到文件
        output_file = project_root / 'FIELD_DICTIONARY_REFERENCE.md'
        output_file.write_text(md_content, encoding='utf-8')
        
        print(f"\n[OK] 字段辞典对照表已生成: {output_file}")
        print(f"  总字段数: {len(fields)}")
        print(f"  数据域数: {len(domains)}")
        print(f"\n各数据域字段数:")
        for domain, domain_fields in sorted(domains.items()):
            print(f"  {domain}: {len(domain_fields)}个字段")
        
        return output_file
        
    except Exception as e:
        logger.error(f"生成对照表失败: {e}")
        raise
    finally:
        db.close()


def generate_markdown(domains, total_count):
    """生成Markdown格式的对照表"""
    
    md_lines = [
        "# 字段辞典内容对照表",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**总字段数**: {total_count}",
        "",
        "## 📋 使用说明",
        "",
        "本对照表用于：",
        "- ✅ 检查自动映射是否正确",
        "- ✅ 查找合适的标准字段进行映射",
        "- ✅ 发现辞典设计问题",
        "- ✅ 验证同义词是否完整",
        "",
        "**重要提示**：",
        "- `field_code` 是系统内部使用的标准字段代码（数据库列名）",
        "- `cn_name` 是中文显示名称（数据库列名层，用户选择）",
        "- `en_name` 是英文名称（备用显示）",
        "- `synonyms` 是同义词列表（用于智能匹配）",
        "",
        "---",
        "",
    ]
    
    # 按数据域生成章节
    domain_order = ['orders', 'products', 'traffic', 'services', 'general']
    
    for domain in domain_order:
        if domain not in domains:
            continue
            
        domain_fields = domains[domain]
        domain_name = {
            'orders': '订单域',
            'products': '产品域',
            'traffic': '流量域',
            'services': '服务域',
            'general': '通用域'
        }.get(domain, domain)
        
        md_lines.append(f"## 📦 {domain_name} ({domain}) - {len(domain_fields)}个字段")
        md_lines.append("")
        
        # 表格标题
        md_lines.append("| 字段代码 (field_code) | 中文名称 (cn_name) | 英文名称 (en_name) | 同义词 (synonyms) | 数据域 | 是否必填 | 数据类型 |")
        md_lines.append("|:---|:---|:---|:---|:---|:---|:---|")
        
        # 按字段组分组显示
        field_groups = {}
        for field in domain_fields:
            group = field[5] or 'other'  # field_group
            if group not in field_groups:
                field_groups[group] = []
            field_groups[group].append(field)
        
        # 按组排序
        group_order = ['required', 'dimension', 'amount', 'quantity', 'ratio', 'datetime', 'text', 'other']
        
        for group in group_order:
            if group not in field_groups:
                continue
                
            group_name = {
                'required': '必填字段',
                'dimension': '维度字段',
                'amount': '金额字段',
                'quantity': '数量字段',
                'ratio': '比率字段',
                'datetime': '时间字段',
                'text': '文本字段',
                'other': '其他字段'
            }.get(group, group)
            
            if len(field_groups) > 1:
                md_lines.append(f"### {group_name} ({len(field_groups[group])}个)")
                md_lines.append("")
            
            for field in field_groups[group]:
                field_code = field[0] or ''
                cn_name = field[1] or ''
                en_name = field[2] or ''
                description = field[3] or ''
                data_domain = field[4] or ''
                field_group = field[5] or ''
                synonyms = field[6] or []
                platform_synonyms = field[7] or {}
                is_required = field[8]
                data_type = field[9] or ''
                
                # 格式化同义词
                synonyms_str = ''
                if synonyms:
                    if isinstance(synonyms, list):
                        synonyms_str = ', '.join(synonyms[:5])  # 最多显示5个
                        if len(synonyms) > 5:
                            synonyms_str += f' ... (+{len(synonyms)-5}个)'
                    else:
                        synonyms_str = str(synonyms)
                
                # 格式化平台同义词
                if platform_synonyms and isinstance(platform_synonyms, dict):
                    platform_syns = []
                    for platform, syns in platform_synonyms.items():
                        if syns:
                            platform_syns.append(f"{platform}: {', '.join(syns[:2])}")
                    if platform_syns:
                        synonyms_str += f" [{', '.join(platform_syns[:2])}]"
                
                required_badge = '✅ 必填' if is_required else '❌'
                
                # 转义Markdown特殊字符
                field_code_escaped = field_code.replace('|', '\\|')
                cn_name_escaped = cn_name.replace('|', '\\|')
                en_name_escaped = en_name.replace('|', '\\|')
                synonyms_escaped = synonyms_str.replace('|', '\\|')
                
                md_lines.append(
                    f"| `{field_code_escaped}` | {cn_name_escaped} | {en_name_escaped} | {synonyms_escaped or '-'} | {data_domain} | {required_badge} | {data_type} |"
                )
        
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")
    
    # 添加未分类的域
    for domain, domain_fields in sorted(domains.items()):
        if domain not in domain_order:
            md_lines.append(f"## 📦 {domain} - {len(domain_fields)}个字段")
            md_lines.append("")
            md_lines.append("| 字段代码 | 中文名称 | 英文名称 | 同义词 | 数据域 | 是否必填 |")
            md_lines.append("|:---|:---|:---|:---|:---|:---|")
            
            for field in domain_fields:
                field_code = field[0] or ''
                cn_name = field[1] or ''
                en_name = field[2] or ''
                synonyms = field[6] or []
                is_required = field[8]
                
                synonyms_str = ', '.join(synonyms[:3]) if isinstance(synonyms, list) and synonyms else '-'
                required_badge = '✅ 必填' if is_required else '❌'
                
                md_lines.append(
                    f"| `{field_code}` | {cn_name} | {en_name} | {synonyms_str} | {domain} | {required_badge} |"
                )
            
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")
    
    # 添加问题检查建议
    md_lines.extend([
        "## 🔍 常见映射问题检查建议",
        "",
        "### 1. 检查字段名称是否准确",
        "",
        "**示例问题**：",
        "- ❌ `平台SKU` 被映射到 `平台`（不正确）",
        "- ✅ `平台SKU` 应该映射到 `platform_sku` 或 `产品SKU`",
        "",
        "**检查方法**：",
        "1. 查找原始字段中的关键词（如`SKU`、`产品`）",
        "2. 在同义词列中查找匹配项",
        "3. 确认映射到正确的字段代码",
        "",
        "### 2. 检查同义词是否完整",
        "",
        "**示例问题**：",
        "- 如果`平台SKU`没有被正确映射，检查`platform_sku`字段的同义词是否包含`平台SKU`",
        "",
        "**检查方法**：",
        "1. 扫描原始字段中的常见名称",
        "2. 检查标准字段的同义词是否覆盖这些名称",
        "3. 如果不完整，需要更新辞典的同义词",
        "",
        "### 3. 检查数据域是否正确",
        "",
        "**示例问题**：",
        "- `订单金额`字段应该在`orders`域，而不是`products`域",
        "",
        "**检查方法**：",
        "1. 确认字段的业务含义",
        "2. 检查数据域是否正确分类",
        "",
        "---",
        "",
        f"**最后更新**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ])
    
    return '\n'.join(md_lines)


if __name__ == "__main__":
    try:
        output_file = generate_field_dictionary_report()
        print(f"\n[OK] 对照表已保存到: {output_file}")
    except Exception as e:
        print(f"\n[ERROR] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

