from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.logger import get_logger

logger = get_logger(__name__)

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)
ServiceType = TypeVar("ServiceType")
ServiceType = TypeVar("ServiceType")


class OptimisticLockError(Exception):
    """乐观锁冲突异常。"""

    def __init__(self, model_name: str, record_id: Any) -> None:
        self.model_name = model_name
        self.record_id = record_id
        super().__init__(
            f"[CONFLICT] {model_name}(id={record_id}) has been modified by another transaction"
        )


class AsyncCRUDService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    通用异步 CRUD 服务基类。

    特性:
    - 仅支持 AsyncSession, 符合项目 async-first 规范
    - 自动软删除过滤: 模型含 deleted_at 字段时, get/get_multi 默认排除已删除记录
    - 可选审计钩子: on_after_create/on_after_update/on_after_delete
    - 可选乐观锁: 使用 version 字段进行并发控制
    """

    def __init__(
        self,
        model: Type[ModelType],
        db: AsyncSession,
        *,
        enable_audit: bool = False,
        enable_optimistic_lock: bool = False,
    ) -> None:
        self.model = model
        self.db = db
        self.enable_audit = enable_audit
        self.enable_optimistic_lock = enable_optimistic_lock

        mapper = inspect(self.model)
        column_keys = {c.key for c in mapper.column_attrs}
        self._has_deleted_at = "deleted_at" in column_keys
        self._has_version = "version" in column_keys

    def _apply_soft_delete_filter(
        self, stmt: Select[Any], *, include_deleted: bool = False
    ) -> Select[Any]:
        if self._has_deleted_at and not include_deleted:
            stmt = stmt.where(getattr(self.model, "deleted_at").is_(None))
        return stmt

    async def get(
        self,
        id: Any,
        *,
        include_deleted: bool = False,
    ) -> Optional[ModelType]:
        stmt = select(self.model).where(self.model.id == id)
        stmt = self._apply_soft_delete_filter(stmt, include_deleted=include_deleted)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> List[ModelType]:
        stmt: Select[Any] = select(self.model).offset(skip).limit(limit)
        stmt = self._apply_soft_delete_filter(stmt, include_deleted=include_deleted)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        obj_data = obj_in.model_dump()
        db_obj = self.model(**obj_data)
        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)

        if self.enable_audit:
            await self.on_after_create(db_obj)

        return db_obj

    async def update(
        self,
        id: Any,
        obj_in: UpdateSchemaType,
        *,
        expected_version: Optional[int] = None,
    ) -> Optional[ModelType]:
        db_obj = await self.get(id)
        if db_obj is None:
            return None

        if self.enable_optimistic_lock and self._has_version:
            if expected_version is not None and getattr(db_obj, "version", None) != expected_version:
                raise OptimisticLockError(self.model.__name__, id)

        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        if self._has_version:
            current_version = getattr(db_obj, "version", 0) or 0
            setattr(db_obj, "version", current_version + 1)

        await self.db.flush()
        await self.db.refresh(db_obj)

        if self.enable_audit:
            await self.on_after_update(db_obj)

        return db_obj

    async def remove(
        self,
        id: Any,
        *,
        expected_version: Optional[int] = None,
    ) -> Optional[ModelType]:
        db_obj = await self.get(id)
        if db_obj is None:
            return None

        if self.enable_optimistic_lock and self._has_version:
            if expected_version is not None and getattr(db_obj, "version", None) != expected_version:
                raise OptimisticLockError(self.model.__name__, id)

        await self.db.delete(db_obj)
        await self.db.flush()

        if self.enable_audit:
            await self.on_after_delete(db_obj)

        return db_obj

    async def soft_delete(self, id: Any) -> Optional[ModelType]:
        if not self._has_deleted_at:
            raise NotImplementedError(
                f"{self.model.__name__} does not have deleted_at column"
            )

        db_obj = await self.get(id)
        if db_obj is None:
            return None

        setattr(db_obj, "deleted_at", datetime.now(timezone.utc))

        if self._has_version:
            current_version = getattr(db_obj, "version", 0) or 0
            setattr(db_obj, "version", current_version + 1)

        await self.db.flush()
        await self.db.refresh(db_obj)

        if self.enable_audit:
            await self.on_after_delete(db_obj)

        return db_obj

    async def on_after_create(self, obj: ModelType) -> None:
        logger.info("[AUDIT] Created %s(id=%s)", self.model.__name__, getattr(obj, "id", None))

    async def on_after_update(self, obj: ModelType) -> None:
        logger.info("[AUDIT] Updated %s(id=%s)", self.model.__name__, getattr(obj, "id", None))

    async def on_after_delete(self, obj: ModelType) -> None:
        logger.info("[AUDIT] Deleted %s(id=%s)", self.model.__name__, getattr(obj, "id", None))


def provide_service(service_cls: Type[ServiceType], *args: Any, **kwargs: Any):
    """
    创建 FastAPI 依赖注入工厂。

    用法示例::

        from backend.services.base_service import provide_service
        from backend.services.hr_income_calculation_service import HRIncomeCalculationService

        hr_income_service_dep = provide_service(HRIncomeCalculationService)

        @router.post("/income/calculate")
        async def calculate_income_c_class(
            ...,
            service: HRIncomeCalculationService = Depends(hr_income_service_dep),
        ):
            result = await service.calculate_month(year_month)
            ...

    这样在测试中可以通过 ``app.dependency_overrides[hr_income_service_dep]`` 注入 mock 实现。
    """
    try:
        from fastapi import Depends as _Depends  # type: ignore
        from backend.models.database import get_async_db as _get_async_db  # type: ignore
    except Exception:  # pragma: no cover - 非 Web 运行环境下跳过
        async def _fallback_dep(*_args: Any, **_kwargs: Any) -> ServiceType:  # type: ignore[return-type]
            return service_cls(*args, **kwargs)  # type: ignore[misc]

        return _fallback_dep

    async def _get_service(
        db: AsyncSession = _Depends(_get_async_db),  # type: ignore[arg-type]
    ) -> ServiceType:
        return service_cls(db, *args, **kwargs)  # type: ignore[misc]

    return _get_service


__all__ = [
    "AsyncCRUDService",
    "OptimisticLockError",
    "provide_service",
]

