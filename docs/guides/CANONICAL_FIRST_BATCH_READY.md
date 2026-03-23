# Canonical 第一批实际测试对象

本文档只回答一个问题：

**组件版本管理页里，当前哪些 canonical 组件可以作为第一批实际测试对象。**

## 第一批名单

### Shopee

- `login`
- `products_export`

说明：
- 这是当前最适合最先打通的一条 Shopee 主链路
- `products_export` 已经过多轮契约与链路修复

### TikTok

- `login`
- `shop_switch`
- `export`

说明：
- 这是 TikTok 当前最短可用 canonical 链路
- 适合先验证登录、店铺切换、统一导出入口

### Miaoshou

- `login`
- `export`

说明：
- 这是妙手当前最短可用 canonical 链路
- 后续复杂优化仍集中在 `export`

## 第一批测试顺序

建议在组件版本管理页按下面顺序推进：

1. `shopee/login`
2. `shopee/products_export`
3. `tiktok/login`
4. `tiktok/shop_switch`
5. `tiktok/export`
6. `miaoshou/login`
7. `miaoshou/export`

## 第一批目标

这一批的目标不是“一次性全平台稳定上线”，而是：

- 先让三平台都各有一条 canonical 主链路可测试
- 让后续优化都围绕唯一 canonical 组件展开
- 不再回到旧录制脚本和重复组件上浪费时间

## 第一批通过后再进入的组件

当上面 7 个组件都能稳定测试后，再进入下一批：

- `shopee/services_export`
- `shopee/analytics_export`
- `shopee/orders_export`
- `shopee/finance_export`

## 当前不要放进第一批的对象

- 非 canonical 组件
- 旧录制草稿
- 平台内部辅助实现
- `*_config.py`
- 历史别名入口

## 一句话结论

如果你现在就要开始在组件版本管理页里实际测试，  
**就从这 7 个 canonical 组件开始。**
