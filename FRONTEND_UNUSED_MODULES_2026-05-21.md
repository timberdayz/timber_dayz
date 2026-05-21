# 前端无用模块梳理（2026-05-21，HK）

梳理口径（静态分析）：
- 菜单可见项：`frontend/src/config/menuGroups.js`
- 路由注册项：`frontend/src/router/index.js`
- 代码引用：全仓 `@/...` alias 引用核对

## 已确认无引用并已删除（避免后续误用维护）

以下文件在路由/菜单/代码中均无引用痕迹，属于历史遗留显示模块与旧 UI 组件，本次已删除：

- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\Dashboard.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\FinancialOverview.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\InventoryDashboard.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\Management.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\SimpleBusinessOverview.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\hr\AttendanceManagement.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\components\common\Sidebar.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\components\common\SimpleSidebar.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\components\common\SimpleHeader.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\components\common\JsonViewer.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\domains\business\views\SalesAnalysis.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\domains\business\views\TopProducts.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\domains\business\views\SalesTrendChart.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\domains\business\views\InventoryDashboardSimple.vue`
- `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\domains\platform\views\TestPage.vue`

同时已调整 `frontend/src/App.vue`：去除启动日志 emoji，符合“Windows 终端输出避免 emoji”的约束。

## 路由收敛（降低隐性维护面）

已从 `frontend/src/router/index.js` 移除以下历史/废弃路由（避免继续维护/误用开发）：
- `/inventory-dashboard-v3`
- `/sales-analysis`
- `/sales-dashboard`
- `/top-products`
- `/sales-trend`
- `/test-legacy`

