# 快速启动指南：所有功能一览

> 历史说明：旧版仓库曾将 Metabase 作为默认 BI 路径。
> 当前现役运行路径为 PostgreSQL-first，账号管理、业务概览和 Dashboard
> 不再依赖 Metabase 作为主查询层或默认启动步骤。

## 启动系统

```bash
python run.py
```

开发模式下也可以手动分别启动：

```bash
# 后端
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# 前端
cd frontend
npm run dev
```

## 访问地址

- 前端：`http://localhost:5173`
- 后端 API 文档：`http://localhost:8001/docs`

## 当前核心功能

- 字段映射系统：`#/field-mapping`
- 产品管理：`#/product-management`
- 销售看板：`#/sales-dashboard-v3`
- 库存看板：`#/inventory-dashboard-v3`
- 业务概览：`#/business-overview`
- 账号管理：`#/account-management`

## 当前原则

- Dashboard 主链路：`b_class raw -> semantic -> mart -> api -> backend -> frontend`
- PostgreSQL Dashboard 是唯一运行时查询路径
- 不再在当前快速启动流程中启用 `docker-compose.metabase*.yml`
- 不再把 `METABASE_URL`、`METABASE_API_KEY` 视为当前默认必配项

## 历史资料入口

如需查看旧版 Metabase 资料，请只作为历史参考：

- `docs/development/METABASE_LEGACY_ASSET_STATUS.md`
- `docs/development/DASHBOARD_API_POSTGRESQL_RETIREMENT_CHECKLIST.md`
- `archive/metabase/README.md`
