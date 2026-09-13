"""Seed the approved internal product category taxonomy v1."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260911_internal_product_category_taxonomy_v1"
down_revision = "current_schema_20260911_company_product_categories"
branch_labels = None
depends_on = None


# The category contract is deliberately immutable migration data. Existing SPU values
# are never read or updated by this migration.
CATEGORY_ROWS = (
    {"category_code": "HOME_LIVING", "parent_category_code": None, "level": 1, "name_zh": "家居生活", "name_en": "Home & Living", "category_path": "家居生活", "status": "active", "is_selectable": True},
    {"category_code": "HOME_STORAGE", "parent_category_code": "HOME_LIVING", "level": 2, "name_zh": "收纳整理", "name_en": "Storage & Organization", "category_path": "家居生活/收纳整理", "status": "active", "is_selectable": True},
    {"category_code": "HOME_KITCHEN", "parent_category_code": "HOME_LIVING", "level": 2, "name_zh": "厨房餐饮", "name_en": "Kitchen & Dining", "category_path": "家居生活/厨房餐饮", "status": "active", "is_selectable": True},
    {"category_code": "HOME_CLEANING_LAUNDRY", "parent_category_code": "HOME_LIVING", "level": 2, "name_zh": "清洁洗护", "name_en": "Cleaning & Laundry", "category_path": "家居生活/清洁洗护", "status": "active", "is_selectable": True},
    {"category_code": "HOME_BATH", "parent_category_code": "HOME_LIVING", "level": 2, "name_zh": "卫浴用品", "name_en": "Bath", "category_path": "家居生活/卫浴用品", "status": "active", "is_selectable": True},
    {"category_code": "HOME_TEXTILES_BEDDING", "parent_category_code": "HOME_LIVING", "level": 2, "name_zh": "家纺寝具", "name_en": "Textiles & Bedding", "category_path": "家居生活/家纺寝具", "status": "active", "is_selectable": True},
    {"category_code": "HOME_DECOR_LIGHTING", "parent_category_code": "HOME_LIVING", "level": 2, "name_zh": "家居装饰照明", "name_en": "Home Decor & Lighting", "category_path": "家居生活/家居装饰照明", "status": "active", "is_selectable": True},
    {"category_code": "BEAUTY_PERSONAL_CARE", "parent_category_code": None, "level": 1, "name_zh": "美妆个护", "name_en": "Beauty & Personal Care", "category_path": "美妆个护", "status": "active", "is_selectable": True},
    {"category_code": "BEAUTY_SKINCARE", "parent_category_code": "BEAUTY_PERSONAL_CARE", "level": 2, "name_zh": "护肤", "name_en": "Skincare", "category_path": "美妆个护/护肤", "status": "active", "is_selectable": True},
    {"category_code": "BEAUTY_MAKEUP", "parent_category_code": "BEAUTY_PERSONAL_CARE", "level": 2, "name_zh": "彩妆", "name_en": "Makeup", "category_path": "美妆个护/彩妆", "status": "active", "is_selectable": True},
    {"category_code": "BEAUTY_TOOLS", "parent_category_code": "BEAUTY_PERSONAL_CARE", "level": 2, "name_zh": "美妆工具", "name_en": "Beauty Tools", "category_path": "美妆个护/美妆工具", "status": "active", "is_selectable": True},
    {"category_code": "BEAUTY_HAIRCARE_STYLING", "parent_category_code": "BEAUTY_PERSONAL_CARE", "level": 2, "name_zh": "洗护造型", "name_en": "Haircare & Styling", "category_path": "美妆个护/洗护造型", "status": "active", "is_selectable": True},
    {"category_code": "BEAUTY_PERSONAL_HYGIENE", "parent_category_code": "BEAUTY_PERSONAL_CARE", "level": 2, "name_zh": "个人清洁护理", "name_en": "Personal Hygiene", "category_path": "美妆个护/个人清洁护理", "status": "active", "is_selectable": True},
    {"category_code": "BEAUTY_DEVICES", "parent_category_code": "BEAUTY_PERSONAL_CARE", "level": 2, "name_zh": "美容个护电器", "name_en": "Beauty Devices", "category_path": "美妆个护/美容个护电器", "status": "active", "is_selectable": True},
    {"category_code": "FASHION_ACCESSORIES", "parent_category_code": None, "level": 1, "name_zh": "服饰鞋包配饰", "name_en": "Fashion & Accessories", "category_path": "服饰鞋包配饰", "status": "active", "is_selectable": True},
    {"category_code": "FASHION_WOMENSWEAR", "parent_category_code": "FASHION_ACCESSORIES", "level": 2, "name_zh": "女装", "name_en": "Womenswear", "category_path": "服饰鞋包配饰/女装", "status": "active", "is_selectable": True},
    {"category_code": "FASHION_MENSWEAR", "parent_category_code": "FASHION_ACCESSORIES", "level": 2, "name_zh": "男装", "name_en": "Menswear", "category_path": "服饰鞋包配饰/男装", "status": "active", "is_selectable": True},
    {"category_code": "FASHION_UNDERWEAR_SLEEPWEAR", "parent_category_code": "FASHION_ACCESSORIES", "level": 2, "name_zh": "内衣家居服", "name_en": "Underwear & Sleepwear", "category_path": "服饰鞋包配饰/内衣家居服", "status": "active", "is_selectable": True},
    {"category_code": "FASHION_SHOES", "parent_category_code": "FASHION_ACCESSORIES", "level": 2, "name_zh": "鞋靴", "name_en": "Shoes", "category_path": "服饰鞋包配饰/鞋靴", "status": "active", "is_selectable": True},
    {"category_code": "FASHION_BAGS_LUGGAGE", "parent_category_code": "FASHION_ACCESSORIES", "level": 2, "name_zh": "箱包旅行", "name_en": "Bags & Luggage", "category_path": "服饰鞋包配饰/箱包旅行", "status": "active", "is_selectable": True},
    {"category_code": "FASHION_JEWELRY_ACCESSORIES", "parent_category_code": "FASHION_ACCESSORIES", "level": 2, "name_zh": "时尚配饰", "name_en": "Jewelry & Accessories", "category_path": "服饰鞋包配饰/时尚配饰", "status": "active", "is_selectable": True},
    {"category_code": "FASHION_MODEST_TRADITIONAL", "parent_category_code": "FASHION_ACCESSORIES", "level": 2, "name_zh": "穆斯林与传统服饰", "name_en": "Modest & Traditional Wear", "category_path": "服饰鞋包配饰/穆斯林与传统服饰", "status": "active", "is_selectable": True},
    {"category_code": "SPORTS_OUTDOORS", "parent_category_code": None, "level": 1, "name_zh": "运动户外", "name_en": "Sports & Outdoors", "category_path": "运动户外", "status": "active", "is_selectable": True},
    {"category_code": "SPORTS_FITNESS", "parent_category_code": "SPORTS_OUTDOORS", "level": 2, "name_zh": "运动健身", "name_en": "Fitness", "category_path": "运动户外/运动健身", "status": "active", "is_selectable": True},
    {"category_code": "SPORTS_CAMPING_HIKING", "parent_category_code": "SPORTS_OUTDOORS", "level": 2, "name_zh": "露营徒步", "name_en": "Camping & Hiking", "category_path": "运动户外/露营徒步", "status": "active", "is_selectable": True},
    {"category_code": "SPORTS_BALL_RACKET", "parent_category_code": "SPORTS_OUTDOORS", "level": 2, "name_zh": "球类运动", "name_en": "Ball & Racket Sports", "category_path": "运动户外/球类运动", "status": "active", "is_selectable": True},
    {"category_code": "SPORTS_CYCLING_WHEELED", "parent_category_code": "SPORTS_OUTDOORS", "level": 2, "name_zh": "骑行与轮滑", "name_en": "Cycling & Wheeled Sports", "category_path": "运动户外/骑行与轮滑", "status": "active", "is_selectable": True},
    {"category_code": "SPORTS_WATER", "parent_category_code": "SPORTS_OUTDOORS", "level": 2, "name_zh": "水上运动", "name_en": "Water Sports", "category_path": "运动户外/水上运动", "status": "active", "is_selectable": True},
    {"category_code": "SPORTS_PROTECTION_ACCESSORIES", "parent_category_code": "SPORTS_OUTDOORS", "level": 2, "name_zh": "运动防护配件", "name_en": "Sports Protection & Accessories", "category_path": "运动户外/运动防护配件", "status": "active", "is_selectable": True},
    {"category_code": "PET_SUPPLIES", "parent_category_code": None, "level": 1, "name_zh": "宠物用品", "name_en": "Pet Supplies", "category_path": "宠物用品", "status": "active", "is_selectable": True},
    {"category_code": "PET_FEEDING", "parent_category_code": "PET_SUPPLIES", "level": 2, "name_zh": "喂养用品", "name_en": "Feeding Supplies", "category_path": "宠物用品/喂养用品", "status": "active", "is_selectable": True},
    {"category_code": "PET_CLEANING_TOILETING", "parent_category_code": "PET_SUPPLIES", "level": 2, "name_zh": "清洁如厕", "name_en": "Cleaning & Toileting", "category_path": "宠物用品/清洁如厕", "status": "active", "is_selectable": True},
    {"category_code": "PET_GROOMING_CARE", "parent_category_code": "PET_SUPPLIES", "level": 2, "name_zh": "宠物护理", "name_en": "Pet Grooming & Care", "category_path": "宠物用品/宠物护理", "status": "active", "is_selectable": True},
    {"category_code": "PET_BEDDING_HOUSING", "parent_category_code": "PET_SUPPLIES", "level": 2, "name_zh": "窝垫居住", "name_en": "Bedding & Housing", "category_path": "宠物用品/窝垫居住", "status": "active", "is_selectable": True},
    {"category_code": "PET_TOYS_TRAINING", "parent_category_code": "PET_SUPPLIES", "level": 2, "name_zh": "玩具训练", "name_en": "Toys & Training", "category_path": "宠物用品/玩具训练", "status": "active", "is_selectable": True},
    {"category_code": "BABY_MATERNITY", "parent_category_code": None, "level": 1, "name_zh": "母婴用品", "name_en": "Baby & Maternity", "category_path": "母婴用品", "status": "active", "is_selectable": True},
    {"category_code": "BABY_FEEDING", "parent_category_code": "BABY_MATERNITY", "level": 2, "name_zh": "喂养用品", "name_en": "Feeding Supplies", "category_path": "母婴用品/喂养用品", "status": "active", "is_selectable": True},
    {"category_code": "BABY_CARE_HYGIENE", "parent_category_code": "BABY_MATERNITY", "level": 2, "name_zh": "护理清洁", "name_en": "Care & Hygiene", "category_path": "母婴用品/护理清洁", "status": "active", "is_selectable": True},
    {"category_code": "BABY_TRAVEL_SAFETY", "parent_category_code": "BABY_MATERNITY", "level": 2, "name_zh": "出行安全", "name_en": "Travel & Safety", "category_path": "母婴用品/出行安全", "status": "active", "is_selectable": True},
    {"category_code": "BABY_GEAR", "parent_category_code": "BABY_MATERNITY", "level": 2, "name_zh": "婴幼儿装备", "name_en": "Baby Gear", "category_path": "母婴用品/婴幼儿装备", "status": "active", "is_selectable": True},
    {"category_code": "MATERNITY_POSTPARTUM", "parent_category_code": "BABY_MATERNITY", "level": 2, "name_zh": "孕产护理", "name_en": "Maternity & Postpartum", "category_path": "母婴用品/孕产护理", "status": "active", "is_selectable": True},
    {"category_code": "BABY_APPAREL", "parent_category_code": "BABY_MATERNITY", "level": 2, "name_zh": "婴童服饰", "name_en": "Baby Apparel", "category_path": "母婴用品/婴童服饰", "status": "active", "is_selectable": True},
    {"category_code": "TOYS_HOBBIES", "parent_category_code": None, "level": 1, "name_zh": "玩具爱好", "name_en": "Toys & Hobbies", "category_path": "玩具爱好", "status": "active", "is_selectable": True},
    {"category_code": "TOYS_INFANT_LEARNING", "parent_category_code": "TOYS_HOBBIES", "level": 2, "name_zh": "婴幼儿益智", "name_en": "Infant Learning", "category_path": "玩具爱好/婴幼儿益智", "status": "active", "is_selectable": True},
    {"category_code": "TOYS_DOLLS_FIGURES", "parent_category_code": "TOYS_HOBBIES", "level": 2, "name_zh": "玩偶手办", "name_en": "Dolls & Figures", "category_path": "玩具爱好/玩偶手办", "status": "active", "is_selectable": True},
    {"category_code": "TOYS_BUILDING_CONSTRUCTION", "parent_category_code": "TOYS_HOBBIES", "level": 2, "name_zh": "拼搭建构", "name_en": "Building & Construction", "category_path": "玩具爱好/拼搭建构", "status": "active", "is_selectable": True},
    {"category_code": "TOYS_ARTS_CRAFTS", "parent_category_code": "TOYS_HOBBIES", "level": 2, "name_zh": "手工美术", "name_en": "Arts & Crafts", "category_path": "玩具爱好/手工美术", "status": "active", "is_selectable": True},
    {"category_code": "TOYS_GAMES_PUZZLES", "parent_category_code": "TOYS_HOBBIES", "level": 2, "name_zh": "游戏拼图", "name_en": "Games & Puzzles", "category_path": "玩具爱好/游戏拼图", "status": "active", "is_selectable": True},
    {"category_code": "HOBBIES_COLLECTIBLES", "parent_category_code": "TOYS_HOBBIES", "level": 2, "name_zh": "兴趣收藏", "name_en": "Hobbies & Collectibles", "category_path": "玩具爱好/兴趣收藏", "status": "active", "is_selectable": True},
    {"category_code": "ELECTRONICS_ACCESSORIES", "parent_category_code": None, "level": 1, "name_zh": "数码与配件", "name_en": "Electronics & Accessories", "category_path": "数码与配件", "status": "active", "is_selectable": True},
    {"category_code": "ELEC_MOBILE_TABLET_ACCESSORIES", "parent_category_code": "ELECTRONICS_ACCESSORIES", "level": 2, "name_zh": "手机平板配件", "name_en": "Mobile & Tablet Accessories", "category_path": "数码与配件/手机平板配件", "status": "active", "is_selectable": True},
    {"category_code": "ELEC_AUDIO_VIDEO", "parent_category_code": "ELECTRONICS_ACCESSORIES", "level": 2, "name_zh": "影音设备", "name_en": "Audio & Video", "category_path": "数码与配件/影音设备", "status": "active", "is_selectable": True},
    {"category_code": "ELEC_SMART_WEARABLE", "parent_category_code": "ELECTRONICS_ACCESSORIES", "level": 2, "name_zh": "智能穿戴", "name_en": "Smart Wearables", "category_path": "数码与配件/智能穿戴", "status": "active", "is_selectable": True},
    {"category_code": "ELEC_CAMERA_ACCESSORIES", "parent_category_code": "ELECTRONICS_ACCESSORIES", "level": 2, "name_zh": "相机配件", "name_en": "Camera Accessories", "category_path": "数码与配件/相机配件", "status": "active", "is_selectable": True},
    {"category_code": "ELEC_COMPUTER_OFFICE", "parent_category_code": "ELECTRONICS_ACCESSORIES", "level": 2, "name_zh": "电脑办公数码", "name_en": "Computer & Office Electronics", "category_path": "数码与配件/电脑办公数码", "status": "active", "is_selectable": True},
    {"category_code": "ELEC_SMART_HOME", "parent_category_code": "ELECTRONICS_ACCESSORIES", "level": 2, "name_zh": "智能家居", "name_en": "Smart Home", "category_path": "数码与配件/智能家居", "status": "active", "is_selectable": True},
    {"category_code": "FOOD_BEVERAGE", "parent_category_code": None, "level": 1, "name_zh": "食品饮料", "name_en": "Food & Beverage", "category_path": "食品饮料", "status": "active", "is_selectable": True},
    {"category_code": "FOOD_SNACKS_CONFECTIONERY", "parent_category_code": "FOOD_BEVERAGE", "level": 2, "name_zh": "休闲食品", "name_en": "Snacks & Confectionery", "category_path": "食品饮料/休闲食品", "status": "active", "is_selectable": True},
    {"category_code": "FOOD_BEVERAGES", "parent_category_code": "FOOD_BEVERAGE", "level": 2, "name_zh": "饮品", "name_en": "Beverages", "category_path": "食品饮料/饮品", "status": "active", "is_selectable": True},
    {"category_code": "FOOD_COOKING_INGREDIENTS", "parent_category_code": "FOOD_BEVERAGE", "level": 2, "name_zh": "烹饪食材", "name_en": "Cooking Ingredients", "category_path": "食品饮料/烹饪食材", "status": "active", "is_selectable": True},
    {"category_code": "FOOD_TEA_COFFEE", "parent_category_code": "FOOD_BEVERAGE", "level": 2, "name_zh": "茶咖冲饮", "name_en": "Tea & Coffee", "category_path": "食品饮料/茶咖冲饮", "status": "active", "is_selectable": True},
    {"category_code": "HEALTH_WELLNESS", "parent_category_code": None, "level": 1, "name_zh": "健康护理", "name_en": "Health & Wellness", "category_path": "健康护理", "status": "active", "is_selectable": True},
    {"category_code": "HEALTH_SUPPLEMENTS", "parent_category_code": "HEALTH_WELLNESS", "level": 2, "name_zh": "营养补充", "name_en": "Supplements", "category_path": "健康护理/营养补充", "status": "active", "is_selectable": True},
    {"category_code": "HEALTH_CARE_DEVICES", "parent_category_code": "HEALTH_WELLNESS", "level": 2, "name_zh": "健康护理设备", "name_en": "Health Care Devices", "category_path": "健康护理/健康护理设备", "status": "active", "is_selectable": True},
    {"category_code": "HEALTH_PROTECTION_FIRST_AID", "parent_category_code": "HEALTH_WELLNESS", "level": 2, "name_zh": "防护急救用品", "name_en": "Protection & First Aid", "category_path": "健康护理/防护急救用品", "status": "active", "is_selectable": True},
    {"category_code": "TOOLS_HOME_IMPROVEMENT", "parent_category_code": None, "level": 1, "name_zh": "工具家装园艺", "name_en": "Tools, Home Improvement & Garden", "category_path": "工具家装园艺", "status": "active", "is_selectable": True},
    {"category_code": "TOOLS_HAND_POWER", "parent_category_code": "TOOLS_HOME_IMPROVEMENT", "level": 2, "name_zh": "手动与电动工具", "name_en": "Hand & Power Tools", "category_path": "工具家装园艺/手动与电动工具", "status": "active", "is_selectable": True},
    {"category_code": "TOOLS_HARDWARE", "parent_category_code": "TOOLS_HOME_IMPROVEMENT", "level": 2, "name_zh": "五金配件", "name_en": "Hardware", "category_path": "工具家装园艺/五金配件", "status": "active", "is_selectable": True},
    {"category_code": "HOME_IMPROVEMENT_ELECTRICAL_LIGHTING", "parent_category_code": "TOOLS_HOME_IMPROVEMENT", "level": 2, "name_zh": "家装电工照明", "name_en": "Electrical & Lighting", "category_path": "工具家装园艺/家装电工照明", "status": "active", "is_selectable": True},
    {"category_code": "GARDEN_OUTDOOR_LIVING", "parent_category_code": "TOOLS_HOME_IMPROVEMENT", "level": 2, "name_zh": "园艺户外生活", "name_en": "Garden & Outdoor Living", "category_path": "工具家装园艺/园艺户外生活", "status": "active", "is_selectable": True},
    {"category_code": "AUTOMOTIVE_MOTORCYCLE", "parent_category_code": None, "level": 1, "name_zh": "汽摩用品", "name_en": "Automotive & Motorcycle", "category_path": "汽摩用品", "status": "active", "is_selectable": True},
    {"category_code": "AUTO_INTERIOR_EXTERIOR", "parent_category_code": "AUTOMOTIVE_MOTORCYCLE", "level": 2, "name_zh": "汽车内外饰", "name_en": "Auto Interior & Exterior", "category_path": "汽摩用品/汽车内外饰", "status": "active", "is_selectable": True},
    {"category_code": "AUTO_CARE_MAINTENANCE", "parent_category_code": "AUTOMOTIVE_MOTORCYCLE", "level": 2, "name_zh": "汽车清洁养护", "name_en": "Auto Care & Maintenance", "category_path": "汽摩用品/汽车清洁养护", "status": "active", "is_selectable": True},
    {"category_code": "MOTORCYCLE_RIDING_ACCESSORIES", "parent_category_code": "AUTOMOTIVE_MOTORCYCLE", "level": 2, "name_zh": "摩托骑行配件", "name_en": "Motorcycle Riding Accessories", "category_path": "汽摩用品/摩托骑行配件", "status": "active", "is_selectable": True},
    {"category_code": "OFFICE_SCHOOL_SUPPLIES", "parent_category_code": None, "level": 1, "name_zh": "办公文教", "name_en": "Office & School Supplies", "category_path": "办公文教", "status": "active", "is_selectable": True},
    {"category_code": "OFFICE_STATIONERY", "parent_category_code": "OFFICE_SCHOOL_SUPPLIES", "level": 2, "name_zh": "文具办公", "name_en": "Stationery & Office", "category_path": "办公文教/文具办公", "status": "active", "is_selectable": True},
    {"category_code": "OFFICE_SCHOOL_LEARNING", "parent_category_code": "OFFICE_SCHOOL_SUPPLIES", "level": 2, "name_zh": "学习教育", "name_en": "School & Learning", "category_path": "办公文教/学习教育", "status": "active", "is_selectable": True},
    {"category_code": "OFFICE_PRINTING_PACKAGING", "parent_category_code": "OFFICE_SCHOOL_SUPPLIES", "level": 2, "name_zh": "打印包装耗材", "name_en": "Printing & Packaging Supplies", "category_path": "办公文教/打印包装耗材", "status": "active", "is_selectable": True},
)


def _has_column(table: str, schema: str, column: str) -> bool:
    return column in {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns(table, schema=schema)
    }


def upgrade() -> None:
    if not _has_column("dim_product_categories", "core", "is_selectable"):
        op.add_column(
            "dim_product_categories",
            sa.Column(
                "is_selectable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            schema="core",
        )
    else:
        op.execute(
            sa.text(
                "UPDATE core.dim_product_categories "
                "SET is_selectable = true WHERE is_selectable IS NULL"
            )
        )
        op.alter_column(
            "dim_product_categories",
            "is_selectable",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            schema="core",
        )

    statement = sa.text(
        """
        INSERT INTO core.dim_product_categories (
            category_code,
            parent_category_code,
            level,
            name_zh,
            name_en,
            category_path,
            status,
            is_selectable,
            version,
            effective_from
        ) VALUES (
            :category_code,
            :parent_category_code,
            :level,
            :name_zh,
            :name_en,
            :category_path,
            :status,
            :is_selectable,
            'v1',
            CURRENT_DATE
        )
        ON CONFLICT (category_code) DO UPDATE SET
            parent_category_code = EXCLUDED.parent_category_code,
            level = EXCLUDED.level,
            name_zh = EXCLUDED.name_zh,
            name_en = EXCLUDED.name_en,
            category_path = EXCLUDED.category_path,
            status = EXCLUDED.status,
            is_selectable = EXCLUDED.is_selectable,
            version = EXCLUDED.version,
            updated_at = NOW()
        """
    )
    op.get_bind().execute(statement, CATEGORY_ROWS)
    op.execute(
        sa.text(
            """
            UPDATE core.dim_product_categories
            SET is_selectable = false, updated_at = NOW()
            WHERE category_code = 'PET_DAILY'
            """
        )
    )


def downgrade() -> None:
    raise NotImplementedError("The internal product category taxonomy v1 migration is forward-only")
