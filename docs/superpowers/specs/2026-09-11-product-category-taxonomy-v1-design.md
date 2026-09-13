# 商品中心两级品类契约 v1

**状态**：已实施于本地开发数据库；远程发布另行走发布流程  
**日期**：2026-09-11  
**范围**：商品中心的内部一级/二级经营品类。  
**非范围**：本文件不改动数据库、API、前端；不设计或实施 TikTok Shop、Amazon、Google 等平台类目映射。

## 1. 决策

商品中心采用且仅采用两级内部品类：

```text
一级经营领域 -> 二级经营品群 -> SPU -> SKU
```

- 新建 SPU 必须且只能归属一个可选二级品类；其一级品类由二级品类的父级确定。历史 SPU 的缺失归属通过单独的数据治理任务补齐，不在本次字典发布中猜测改写。
- SKU 继承 SPU 的品类，不建立 SKU 级独立品类。
- 二级品类描述稳定的商品族；不得把具体单品、材质、规格、目标人群、平台活动或营销标签当作品类。
- 不设“其他”二级品类。无法归属的候选商品保留在待评估阶段，先完成分类决策再创建 SPU。
- 平台类目不构成内部品类层级，也不改变内部 SPU 归属；平台映射留待后续独立设计。
- `active` 二级品类必须拥有 `active` 一级父级。停用一级品类前，必须先迁移或停用其全部启用的二级品类；不得出现可见的启用二级品类却无法用于新 SPU 的状态。
- `status` 表示字典记录是否有效，`is_selectable` 表示是否可用于新建或重新归类的 SPU。完整 v1 目录的 `status` 与 `is_selectable` 均为 `active` / `true`；这只代表内部主数据可归类，不代表已完成任何市场合规、采购或上架审批。

当前系统已限制内部层级为 1 或 2，并要求二级品类拥有一级父级；该约束保持不变。

## 2. 内部分类目录

以下为完整的内部分类契约。它覆盖跨境电商常见经营领域，但不是任何平台站点的类目镜像。用户已确认完整 v1 目录均可用于内部主数据归类；具体商品的采购、合规和上架仍按各自流程决定。

| 一级代码 | 一级品类 | 二级代码：二级品类 |
|---|---|---|
| `HOME_LIVING` | 家居生活 | `HOME_STORAGE`：收纳整理；`HOME_KITCHEN`：厨房餐饮；`HOME_CLEANING_LAUNDRY`：清洁洗护；`HOME_BATH`：卫浴用品；`HOME_TEXTILES_BEDDING`：家纺寝具；`HOME_DECOR_LIGHTING`：家居装饰照明 |
| `BEAUTY_PERSONAL_CARE` | 美妆个护 | `BEAUTY_SKINCARE`：护肤；`BEAUTY_MAKEUP`：彩妆；`BEAUTY_TOOLS`：美妆工具；`BEAUTY_HAIRCARE_STYLING`：洗护造型；`BEAUTY_PERSONAL_HYGIENE`：个人清洁护理；`BEAUTY_DEVICES`：美容个护电器 |
| `FASHION_ACCESSORIES` | 服饰鞋包配饰 | `FASHION_WOMENSWEAR`：女装；`FASHION_MENSWEAR`：男装；`FASHION_UNDERWEAR_SLEEPWEAR`：内衣家居服；`FASHION_SHOES`：鞋靴；`FASHION_BAGS_LUGGAGE`：箱包旅行；`FASHION_JEWELRY_ACCESSORIES`：时尚配饰；`FASHION_MODEST_TRADITIONAL`：穆斯林与传统服饰 |
| `SPORTS_OUTDOORS` | 运动户外 | `SPORTS_FITNESS`：运动健身；`SPORTS_CAMPING_HIKING`：露营徒步；`SPORTS_BALL_RACKET`：球类运动；`SPORTS_CYCLING_WHEELED`：骑行与轮滑；`SPORTS_WATER`：水上运动；`SPORTS_PROTECTION_ACCESSORIES`：运动防护配件 |
| `PET_SUPPLIES` | 宠物用品 | `PET_FEEDING`：喂养用品；`PET_CLEANING_TOILETING`：清洁如厕；`PET_GROOMING_CARE`：宠物护理；`PET_BEDDING_HOUSING`：窝垫居住；`PET_TOYS_TRAINING`：玩具训练 |
| `BABY_MATERNITY` | 母婴用品 | `BABY_FEEDING`：喂养用品；`BABY_CARE_HYGIENE`：护理清洁；`BABY_TRAVEL_SAFETY`：出行安全；`BABY_GEAR`：婴幼儿装备；`MATERNITY_POSTPARTUM`：孕产护理；`BABY_APPAREL`：婴童服饰 |
| `TOYS_HOBBIES` | 玩具爱好 | `TOYS_INFANT_LEARNING`：婴幼儿益智；`TOYS_DOLLS_FIGURES`：玩偶手办；`TOYS_BUILDING_CONSTRUCTION`：拼搭建构；`TOYS_ARTS_CRAFTS`：手工美术；`TOYS_GAMES_PUZZLES`：游戏拼图；`HOBBIES_COLLECTIBLES`：兴趣收藏 |
| `ELECTRONICS_ACCESSORIES` | 数码与配件 | `ELEC_MOBILE_TABLET_ACCESSORIES`：手机平板配件；`ELEC_AUDIO_VIDEO`：影音设备；`ELEC_SMART_WEARABLE`：智能穿戴；`ELEC_CAMERA_ACCESSORIES`：相机配件；`ELEC_COMPUTER_OFFICE`：电脑办公数码；`ELEC_SMART_HOME`：智能家居 |
| `FOOD_BEVERAGE` | 食品饮料 | `FOOD_SNACKS_CONFECTIONERY`：休闲食品；`FOOD_BEVERAGES`：饮品；`FOOD_COOKING_INGREDIENTS`：烹饪食材；`FOOD_TEA_COFFEE`：茶咖冲饮 |
| `HEALTH_WELLNESS` | 健康护理 | `HEALTH_SUPPLEMENTS`：营养补充；`HEALTH_CARE_DEVICES`：健康护理设备；`HEALTH_PROTECTION_FIRST_AID`：防护急救用品 |
| `TOOLS_HOME_IMPROVEMENT` | 工具家装园艺 | `TOOLS_HAND_POWER`：手动与电动工具；`TOOLS_HARDWARE`：五金配件；`HOME_IMPROVEMENT_ELECTRICAL_LIGHTING`：家装电工照明；`GARDEN_OUTDOOR_LIVING`：园艺户外生活 |
| `AUTOMOTIVE_MOTORCYCLE` | 汽摩用品 | `AUTO_INTERIOR_EXTERIOR`：汽车内外饰；`AUTO_CARE_MAINTENANCE`：汽车清洁养护；`MOTORCYCLE_RIDING_ACCESSORIES`：摩托骑行配件 |
| `OFFICE_SCHOOL_SUPPLIES` | 办公文教 | `OFFICE_STATIONERY`：文具办公；`OFFICE_SCHOOL_LEARNING`：学习教育；`OFFICE_PRINTING_PACKAGING`：打印包装耗材 |

### 2.1 交叉品类归属规则

对同时看似属于多个二级品类的商品，按以下排他规则归属。它们是 v1 的分类优先级，后续新增交叉品类时必须同时补充本节。

| 商品情形 | 唯一归属规则 |
|---|---|
| 茶、咖啡及其冲饮或即饮产品 | 归入 `FOOD_TEA_COFFEE`；`FOOD_BEVERAGES` 仅接收不以茶或咖啡为主体的饮品。 |
| 具备联网、App、语音或自动化控制能力的灯具或家居设备 | 优先归入 `ELEC_SMART_HOME`。 |
| 需固定安装、接入建筑电路或属于电工配件的灯具 | 在不满足智能家居条件时，归入 `HOME_IMPROVEMENT_ELECTRICAL_LIGHTING`。 |
| 非固定安装、以氛围或装饰用途为主的普通灯具 | 在不满足前两项条件时，归入 `HOME_DECOR_LIGHTING`。 |
| 自行车、轮滑及其专用防护用品 | 专为骑行或轮滑设计、且商品核心使用场景为该运动的头盔、护具等，归入 `SPORTS_CYCLING_WHEELED`。 |
| 通用或多运动项目的防护用品 | 不具有骑行/轮滑专用属性的护具、护腕、护膝等，归入 `SPORTS_PROTECTION_ACCESSORIES`。 |
| 婴幼儿出行、运输或乘车安全用品 | 推车、背带、汽车安全座椅及主要用于外出安全的配件，归入 `BABY_TRAVEL_SAFETY`。 |
| 婴幼儿日常居家装备 | 高脚椅、游戏围栏、摇椅等主要在居家场景使用的装备，归入 `BABY_GEAR`。 |

## 3. 现有字典迁移原则

以下既有代码保持稳定，不重命名：`HOME_LIVING`、`HOME_STORAGE`、`HOME_KITCHEN`、`BEAUTY_PERSONAL_CARE`、`BEAUTY_TOOLS`、`SPORTS_OUTDOORS`、`SPORTS_FITNESS`、`PET_SUPPLIES`。

`PET_DAILY`（宠物日用品）不再是 v1 契约中的可选二级品类。实施时不得直接删除或静默重写历史归属：即使已有 SPU 引用该代码，也要将其保留为有效但不可选的历史字典记录。后续按商品事实重新归类时，必须记录迁移审计，完成全量核对后才可停用该遗留代码。

每次品类迁移必须写入不可变的“SPU 品类归属历史”记录。至少保存 `spu`、旧一级/二级代码、新一级/二级代码、迁移理由、操作者、发生时间、审批人或迁移批次 ID；迁移批次须在停用 `PET_DAILY` 前完成 SPU 总数、成功数和异常数的全量核对。`dim_spu` 保存当前归属，不替代该历史记录。

当前数据模型只有 `active` / `inactive` 两种状态。本次新增 `is_selectable` 字段，避免把“历史可读但不可再选”的遗留类目与“字典已停用”混为一谈；不新增“规划”状态枚举。

## 4. 启用门槛与治理

二级品类进入内部字典前，必须满足：

1. 业务 Owner 定义了品类边界及至少一个正例和反例。
2. 至少存在一个拟入库或已验证的 SPU 使用场景。

食品饮料、健康护理、美容个护电器、母婴和汽摩用品在采购、对外销售或上架前，仍须完成目标市场合规与履约可行性确认；这不是内部分类可选性的前置条件。

## 5. 实施边界与验证

本设计的内部目录实施已完成：

1. 已新增完整 v1 字典，并保留现有稳定代码与 `is_selectable` 字段。
2. `PET_DAILY` 已保留为不可选历史值，未自动迁移任何存量 SPU；后续迁移另行审计。
3. 已验证新建 SPU 二级必填、一级自动回填、父子关系一致，以及父级停用不会遗留启用子类。

验收标准是：新建 SPU 有且仅有一个可选有效二级品类；SKU 不产生独立品类；历史 `PET_DAILY` 归属不丢失且不可用于新归类。
