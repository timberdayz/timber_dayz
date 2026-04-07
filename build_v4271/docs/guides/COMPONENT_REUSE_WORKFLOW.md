# 复用成熟导出组件工作流

本文档用于指导当前项目在时间紧张时，如何**优先复用成熟 `export` 组件**，只新增或修复运行它所需的最小前置组件，以最快方式形成可测试、可提升为 stable 的正式采集脚本。

## 1. 结论先行

推荐路线不是“重录所有导出脚本”，而是：

1. 复用成熟 `export`
2. 只补最小前置组件
3. 将修改后的脚本注册进 `ComponentVersion`
4. 在组件版本管理页测试
5. 通过后提升为 stable

## 2. 哪些脚本会出现在组件版本管理页

组件版本管理页读取的是 **`ComponentVersion` 表**，不是单纯扫描磁盘文件。

这意味着：

- 只改磁盘文件，不保证页面一定新增版本记录
- 只有进入 `ComponentVersion` 体系的脚本，才能稳定出现在页面中

当前两条正规入口：

### 2.1 录制页保存
- 录制页保存会创建新版本记录
- 默认 `is_stable=False`
- file_path 会写入版本化 `.py` 路径

### 2.2 批量注册 Python 组件
- 版本管理页支持 “批量注册 Python 组件”
- 会扫描 `modules/platforms/*/components/*.py`
- 将尚未注册的 Python 组件写入 `ComponentVersion`

## 3. 当前正式脚本路径

### 3.1 正式组件目录

当前正式脚本统一放在：

`modules/platforms/<platform>/components/`

例如：
- `modules/platforms/shopee/components/`
- `modules/platforms/tiktok/components/`
- `modules/platforms/miaoshou/components/`

### 3.2 两类正式文件

#### A. 标准主文件 / 基线文件
- `login.py`
- `navigation.py`
- `date_picker.py`
- `shop_switch.py`
- `orders_export.py`
- `products_export.py`
- `services_export.py`

这些文件更像平台当前的主实现或 fallback 基线。

#### B. 版本化执行文件
录制保存后，后端会生成：

`modules/platforms/{platform}/components/{base_name}_{version_suffix}.py`

例如：
- `login_v1_0_1.py`
- `orders_export_v1_0_3.py`

这类文件的路径会写入 `ComponentVersion.file_path`，并由版本管理页展示为“实际执行文件”。

## 4. 旧路径与新路径的关系

以下旧路径**不再是正式采集脚本路径**：

- `temp/recordings/`
- `data/recordings/`
- `backups/...`
- 历史 `config/collection_components/...`

当前正式路径只有：

- `modules/platforms/<platform>/components/`

## 5. 推荐工作流

### Step 1: 判断是否值得复用成熟 export

优先复用成熟 `export` 的条件：
- 当前平台已有成熟 `export`
- 目标页面与现役页面结构相近
- 复杂逻辑主要在导出后链路，而不是导出前业务流

不建议重录成熟 `export`，除非确认现役实现明显不适配目标页面。

### Step 2: 只补最小前置组件

#### Shopee
通常优先复用：
- `orders_export.py`
- `products_export.py`
- `analytics_export.py`
- `finance_export.py`
- `services_export.py`

常见需要补的前置：
- `login`
- `navigation`
- `date_picker`

#### TikTok
通常优先复用：
- `export.py`

常见需要补的前置：
- `login`
- `shop_switch`
- `navigation`
- `date_picker`

#### 妙手
通常优先复用：
- `export.py`

常见需要补的前置：
- `login`
- `navigation`
- `date_picker`

## 6. 修改文件时的建议

### 6.1 直接改主文件,适合快速试错

适合：
- 先快速验证思路
- 当前目标是让成熟组件在新页面跑通

做法：
- 直接修改 `modules/platforms/<platform>/components/*.py`
- 改完后执行一次“批量注册 Python 组件”

### 6.2 通过录制保存生成新版本,适合正式沉淀

适合：
- 你已经有稳定修改结果
- 希望保留明确版本号

做法：
- 通过录制页保存
- 让系统写出版本化 `.py`
- 再去组件版本管理页测试并提 stable

## 7. 改完后如何让版本管理页看到脚本

### 路线 A：批量注册
适合你手动修改了现役主文件。

步骤：
1. 修改 `modules/platforms/<platform>/components/*.py`
2. 打开组件版本管理页
3. 点击“批量注册 Python 组件”
4. 刷新列表确认新组件/新 file_path 已进入 `ComponentVersion`

### 路线 B：录制保存
适合你通过录制页产出版本化新文件。

步骤：
1. 在录制页保存 Python 代码
2. 系统自动创建版本记录
3. 版本管理页直接可见

## 8. 测试与 stable

无论走哪条路径，正式采集前都必须：

1. 在组件版本管理页测试组件
2. 测试通过后提升为 stable

只有 stable 版本可用于正式采集和定时调度。

## 9. 平台级最小化建议

### 最省时间的默认策略

- Shopee：先补 `login`，再看是否要补 `navigation/date_picker`
- TikTok：先补 `login + shop_switch`，再看是否要补 `navigation/date_picker`
- 妙手：先补 `login + navigation`，再看是否要补 `date_picker`

然后统一复用成熟 `export`。

## 10. 不要做的事

- 不要重录成熟导出流程
- 不要把旧录制目录当正式路径
- 不要只改文件而不注册版本,然后期待页面自动出现
- 不要在未测试前直接把组件当正式采集组件使用
