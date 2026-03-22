# 采集脚本参考索引

本文档用于集中指向当前项目中**应保留并优先参考**的成熟采集脚本，避免后续在旧录制脚本、临时产物、历史备份中反复检索。

## 当前权威位置

- 正式组件目录：`modules/platforms/<platform>/components/`
- 录制与生成规范：`docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`
- 录制页产出说明：`docs/guides/RECORDER_PYTHON_OUTPUT.md`
- 复用成熟导出组件工作流：`docs/guides/COMPONENT_REUSE_WORKFLOW.md`

> 原则：
> - 后续编写采集脚本时，**优先看本索引列出的文件**
> - `temp/recordings/`、`data/recordings/`、`backups/` 下的原始回放脚本和历史副本**不再作为首选参考**

## 妙手 Miaoshou

### 优先参考
- `modules/platforms/miaoshou/components/export.py`
- `modules/platforms/miaoshou/components/date_picker.py`
- `modules/platforms/miaoshou/components/login.py`
- `modules/platforms/miaoshou/components/navigation.py`

### 复杂场景重点
- 导出下拉：hover/click 后展开菜单，再选 `menuitem`
- dropdown 作用域收敛
- 弹窗 / iframe / 字段选择对话框
- 下载监听与导出确认链路

## Shopee

### 优先参考
- `modules/platforms/shopee/components/services_export.py`
- `modules/platforms/shopee/components/products_export.py`
- `modules/platforms/shopee/components/analytics_export.py`
- `modules/platforms/shopee/components/orders_export.py`
- `modules/platforms/shopee/components/finance_export.py`
- `modules/platforms/shopee/components/date_picker.py`
- `modules/platforms/shopee/components/login.py`
- `modules/platforms/shopee/components/navigation.py`

### 复杂场景重点
- 导出任务生成后等待“最新记录”可下载
- 处理状态词：执行中 / 生成中 / 队列中 / 处理中
- 下载监听失败后的文件系统兜底
- 必要时使用 HAR/API 下载兜底

## TikTok

### 优先参考
- `modules/platforms/tiktok/components/export.py`
- `modules/platforms/tiktok/components/date_picker.py`
- `modules/platforms/tiktok/components/login.py`
- `modules/platforms/tiktok/components/navigation.py`
- `modules/platforms/tiktok/components/shop_switch.py`

### 复杂场景重点
- 导出按钮可见但禁用
- 先切 tab / 区域 / 店铺后导出按钮才可用
- 日期面板在 iframe 中
- 二次确认按钮与全局下载监听

## 不再优先参考的目录

以下目录中的脚本属于原始录制产物、临时中间文件或历史备份，不再作为首选参考：

- `data/recordings/`
- `temp/recordings/`
- `backups/recordings/`
- `backups/20250831_recordings_archive/temp/recordings/`
- `backups/20251229_legacy_components_migration/modules/platforms/`

## 使用建议

1. 先按平台定位到本索引中的正式组件。
2. 再按“复杂场景重点”查找相应实现。
3. 仅在正式组件中没有答案时，再回溯历史备份。
