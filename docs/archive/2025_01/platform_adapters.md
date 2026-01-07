# 平台适配器指南 / Platform Adapters Guide

> 文档索引（推荐入口）: docs/INDEX.md

## 目标

为每个平台提供统一的适配层，屏蔽页面差异，将业务流程以组件组合实现。

## 基础接口

- 基类：modules/platforms/adapter_base.py::PlatformAdapter
- 需实现：
  - platform_id: str
  - login() -> LoginComponent
  - navigation() -> NavigationComponent
  - date_picker() -> DatePickerComponent
  - exporter() -> ExportComponent
  - capabilities() -> Dict

## Shopee 示例（骨架）

- adapter：modules/platforms/shopee/adapter.py
- 组件：modules/platforms/shopee/components/{login,navigation,date_picker,export,metrics_selector}.py

## 最佳实践

- 适配器不持有重逻辑，仅负责工厂与简单能力声明
- 组件使用 ExecutionContext 注入账号/logger
- UI 差异通过组件与配方解决，避免在业务流程硬编码
- 重要变更需 bump 组件/配方版本并记录变更
