# 模板决策资产(Definitions)

这个目录是**模板的真相源**: 「哪个平台的导出长什么样、我要哪些数据、哪几列参与去重」
—— 这些是**人工判断的结果**, 所以它们在 Git 里, 不在数据库里。

## 为什么

模板表 `core.field_mapping_templates` 里混着两类东西:

| 类别 | 例子 | 去处 |
|---|---|---|
| **决策资产** | 列清单、核心字段清单、解析规则、表头行、维度 | **Git**(本目录) |
| **运行时状态** | 版本号、发布时间、命中次数、成功率、审计字段 | **数据库** |

以前两者混在一张表里, 于是「改了模板」这件事只发生在数据库里:
没法 review、没法 diff、没法回滚、换环境还得手工重配一遍。

现在改模板 = 改本目录里的一个 JSON = 一次普通的、可 review 的提交。

## 目录结构

```
templates/
  README.md                  ← 本文件
  definitions/               ← 基线定义(进 Git, 27 份)
    tiktok__orders__monthly.json
    shopee__services__daily__agent.json
    ...
  overlays/                  ← 环境差异(进 Git; 只放差异, 不重复基线)
```

## 文件命名

```
<platform>__<data_domain>__<granularity>[__<sub_domain>][__<account>].json
```

例:

- `tiktok__orders__monthly.json` → tiktok / orders / monthly
- `shopee__services__daily__agent.json` → shopee / services / daily / agent

一个维度**只能有一份定义** —— 重复会被校验直接拒绝。

## 定义里有什么

| 字段 | 含义 |
|---|---|
| `platform` / `data_domain` / `granularity` / `sub_domain` / `account` | 维度身份(唯一键) |
| `header_row` | 表头在第几行(0-based) |
| `sheet_name` / `encoding` | 工作表名 / 文件编码 |
| `header_columns` | 模板的完整列清单(**顺序有意义**) |
| `deduplication_fields` | 参与去重指纹的列 |
| `core_fields` | **核心字段清单** = 需求(`semantic_key` / `raw_name` / `required` / `in_hash`) |
| `ignored_extra_fields` | 「已确认的新列」已阅标记 |
| `header_bindings` | 列 → 语义键的绑定(别名、位置、是否必填) |
| `field_parse_rules` | 字段级解析规则(如日期格式) |
| `notes` | 人写的说明 |

**不在**定义里(属于数据库): `id` / `version` / `status` / `usage_count` /
`success_rate` / `created_by` / `created_at` / `updated_by` / `updated_at` /
`template_name` / `format_signature`。

写进定义会被校验直接拒绝 —— 它们的值每次巡检都会变, 进 Git 只会产生噪音 diff。

`header_bindings` 里的 `confidence` 是**算法置信度**(不是人工决策), 同样不进 Git,
比对时也不参与 —— 否则每次重算都会报假差异。

## 怎么用

### 基线来自**生产库**(2026-11-14 起)

> [!IMPORTANT]
> 本目录的基线是**从生产库导出的**, 不是从开发库。
> 生产是唯一在跑的系统 ⇒ 它是「这个维度现在到底长什么样」的事实源。
>
> 踩过的坑: 最初的基线是从**本机开发库**导出的, 于是它把开发库的
> 诊断产物(某一版多了 2 列的 `tiktok/orders/monthly`)当成了「约定」,
> 守卫一上线就报 6 个维度对不上 —— **报的是差异, 但差异里混着开发库的垃圾**。
> ⇒ 重新从生产库导出后, 守卫才对得上, 它报的差异才真的等于「有人在库里改了模板」。
>
> 本机开发库与本目录**本来就不一致**(开发库更旧/更新, 且带测试变体),
> 这不是缺陷 —— 不要拿开发库的 `--check` 结果当生产结论。

### 改模板(日常路径)

改库里的模板 → 重新导出 → 提交:

```bash
python scripts/export_template_definitions.py
git add templates/definitions
git commit -m "chore(templates): 更新 tiktok/orders/monthly 列清单"
```

也可以先在界面上改模板, 再导出 —— **界面仍然是日常入口**, 本目录是它的**留痕层**。

### 校验(离线, CI 可跑)

```bash
python scripts/apply_template_definitions.py --validate-only
```

只检查定义文件本身: 格式、必填字段、维度键唯一性、**不许混进运行时状态字段**。
不连数据库 ⇒ GitHub CI 里可以直接跑。

### 差异守卫(需要库)

```bash
python scripts/apply_template_definitions.py --check
```

比对「仓库定义」与「库内 published 实例」的决策资产。
有任何差异就以退出码 **1** 结束, 并逐条打印差异。
⇒ 这是「有人在库里改了模板但没改 Git」或反之的守门人。

> 注意: GitHub CI 上**没有业务库**, 所以 `--check` 跑不了。
> 它要在有库的环境跑(本机、部署前检查)。

### 投影(把定义写进库)

```bash
python scripts/apply_template_definitions.py --apply --dry-run   # 先看计划
python scripts/apply_template_definitions.py --apply             # 真投影
```

走的是与界面发布**同一条路**
(`FieldMappingTemplateService.save_template`: 归档旧版本 + 版本号自增 + 家族投影),
所以投影出来的模板与手工发布的模板没有区别。

`--apply` 会**发布新版本**, 属于会改变线上行为的人工决策 —— 先跑 `--dry-run` 看清差异。

### 改 `deduplication_fields` 必须**同口径重建存量 data_hash**

> [!WARNING]
> `data_hash` 是事实表的**行身份**(唯一键 + `ON CONFLICT DO UPDATE`),
> 不是内容摘要。⇒ 改了 `deduplication_fields`(或作用域里的身份键)之后,
> **已入库行的 hash 与新算出的 hash 不同** ⇒ 同一份快照再采一次不会命中旧行
> ⇒ **被当成新数据插入** ⇒ 事实表按快照次数膨胀。
>
> ⇒ 「改去重口径」与「重建存量 hash」是**一件事的两半**, 必须同时做。

库存维度就是踩过这个坑: 2026-11-03 前后作用域身份键从 `shop_id` 换成了
`shop_account_id`(代码里 `backend/services/catalog_files_identity_backfill.py`
早就记着「口径切换会让所有 hash 失效 ⇒ 要求一次全量重建」),
同一份快照在切换前后各入库一次 ⇒ 4111 行里多出 **256 组**同 SKU×仓×日期的重复行。

重建脚本: `scripts/rebuild_inventory_snapshot_hash.py`

```bash
python scripts/rebuild_inventory_snapshot_hash.py                    # 只读: 看口径分布与计划
python scripts/rebuild_inventory_snapshot_hash.py --apply \
    --backup-dir /tmp/inv_rebuild                                    # 真执行(先备份)
python scripts/rebuild_inventory_snapshot_hash.py --verify           # 复核
```

它的四道闸: 默认只读 / 逐行认领历史口径(认不出来就中止) /
用**应用自身**的 hash 函数算(不手写哈希算法) / 写库前先备份。

### 执行顺序: **先重建, 后投影**（别弄反）

> [!IMPORTANT]
> 顺序反了会**直接中止**, 不是「数据写坏」。

重建脚本认领历史行时, 用的是**库里已发布模板**的 `deduplication_fields`
(那才是历史行当初算 hash 用的字段集)。而新字段集取自**仓库里的定义文件**。

⇒ 若**先投影模板**(库内模板的去重字段已改成新的), 再跑重建:
历史行用新字段集认领 ⇒ **认不出来** ⇒ 脚本判定「口径没搞清楚」⇒ 中止, 一行不写。

⇒ 正确顺序:

| 步骤 | 命令 | 说明 |
|---|---|---|
| 1 | `rebuild_inventory_snapshot_hash.py --apply --backup-dir …` | 先重建: 此时库内模板还是旧口径, 历史行才认领得到 |
| 2 | `apply_template_definitions.py --apply` | 再投影: 让库里模板与仓库定义一致 |
| 3 | `rebuild_inventory_state_from_snapshots.py --full-rebuild` | 重刷状态层(mart), 让下游跟上 |

两步之间尽量**没有采集入库**(否则采集按旧模板算 hash, 又会插新行)。
实测生产 `ENABLE_COLLECTION=false`、窗口期内 `ingest_timestamp` 不变 ⇒ 安全。

> 投影之后再重建, 脚本会走**幂等分支**: 认出「库里已全部是新口径」⇒ 报
> 「无需重建」并退出 0, 不做任何写入 ⇒ 重复执行是安全的。

## 环境差异(overlay)

基线定义覆盖所有环境。个别环境需要**少量**差异时, 用 overlay:

```bash
python scripts/apply_template_definitions.py --check --overlay staging
```

overlay 文件放在 `templates/overlays/`, 格式:

```json
{
  "overlay": "staging",
  "definitions": [
    {
      "platform": "tiktok",
      "data_domain": "orders",
      "granularity": "monthly",
      "core_fields": ["..."]
    }
  ]
}
```

overlay 只允许**覆盖决策字段**, 不允许改维度键(改了就是另一个模板, 该另起一份定义)。
当前仓库**没有实际使用的 overlay** —— `templates/overlays/example.json` 只是格式示例,
不会被自动加载。

## 与 `scripts/sync_templates_to_cloud.ps1` 的关系

那个脚本是 `pg_dump` 式的**整表搬运**(导出模板表 → 压缩 → 传云端)。
批次 3 之后它不再是「模板进 Git」的主路径 —— 决策资产在本目录里,
数据库同步只负责**运行时状态**。

它保留下来, 原因是云端环境仍需要完整模板表(含版本历史),
而 Git 目录只表达**期望状态**。两者不冲突, 职责不同。
