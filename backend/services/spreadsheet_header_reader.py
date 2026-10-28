"""统一读表头入口 (SSOT)

为什么
----
「这个文件的列是什么」在系统里曾经有四套读法:

1. ``backend/services/data_sync_service.py`` —— ``_safe_resolve_path`` +
   ``_resolve_runtime_spreadsheet_path`` + ``ExcelParser.read_excel``
2. ``backend/services/data_ingestion_service.py`` —— **另抄一份**同名方法
3. ``backend/domains/data_platform/routers/data_sync.py`` —— 自用
   ``detect_file_format`` + ``normalize_for_runtime`` + ``read_excel``,
   **没有做安全路径解析**(直接拿 ``catalog_files.file_path`` 的相对路径)
4. ``backend/services/data_ingestion_service.py`` 入库 —— 额外允许
   ``header_row < 0`` 表示「无表头行」

四套规则**不完全一致**:

* 允许根目录不同(``temp`` vs ``temp/outputs``)
* 绝对路径是否校验不同(判定路径直接放行, 入库路径校验后抛错)
* 是否做运行时格式归一不同
* 表头行语义不同(``<0`` 在一处表示「无表头」, 另一处直接当 0-based 行号用)

⇒ 治理面板读出来的列, 与入库时实际读出来的列可能不是同一批。
「判定说 ready、入库却失败」或反过来, 是**系统性问题**而不是偶发问题。

本模块是唯一入口, 统一四件事:

1. **安全路径解析** —— 允许根目录 + 环境迁移兼容(绝对路径回退相对路径)
   + ``DATA_SYNC_ALLOWED_ROOTS`` 额外允许根
2. **运行时格式归一** —— ``xls`` / ``xlsx_with_ole`` / ``html`` 走
   ``normalize_for_runtime`` 产出的标准化副本
3. **表头行口径** —— ``header_row < 0`` 表示「无表头行」(pandas ``header=None``),
   其余为 0-based 精确行
4. **CPU 密集隔离** —— 大文件读取不阻塞事件循环

关于「严格模式」
----------------
判定链路(读不到就报 parse_failed)默认宽松: 路径不在允许根内只记日志放行;
入库链路严格: 不在允许根内直接抛错。两者共用同一套**允许根集合与解析规则**,
差别只在越界时是放行还是拒绝(由 ``DATA_SYNC_STRICT_ALLOWED_ROOTS`` 控制)。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from modules.core.logger import get_logger

logger = get_logger(__name__)


# 表头行口径: <0 表示「无表头行」(pandas header=None), 其余为 0-based 精确行
HEADER_ROW_NO_HEADER = -1

# 运行时需要格式归一的文件类型(旧版 xls / OLE 包裹的 xlsx / html 伪表格)
RUNTIME_NORMALIZATION_FORMATS = frozenset({"xls", "xlsx_with_ole", "html"})

# 允许根目录内可识别的关键路径片段(用于绝对路径回退相对路径)
_RELATIVE_KEY_PATHS = (
    "data/raw/",
    "data/input/",
    "downloads/",
    "temp/outputs/",
)


@dataclass
class SpreadsheetHeader:
    """读表头结果。"""

    runtime_path: str = ""
    columns: List[str] = field(default_factory=list)
    dataframe: Any = None
    header_row_used: Optional[int] = None
    source_format: Optional[str] = None
    normalized: bool = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.dataframe is not None


class SpreadsheetHeaderReader:
    """按模板表头行读取文件列 —— 唯一入口。"""

    def __init__(
        self,
        *,
        strict_allowed_roots: Optional[bool] = None,
        log_prefix: str = "Header",
        executor_manager_factory: Optional[Any] = None,
        use_cpu_executor: bool = True,
    ):
        """
        Args:
            strict_allowed_roots: 路径越界时是否拒绝(None = 读 ``DATA_SYNC_STRICT_ALLOWED_ROOTS``)
            log_prefix: 日志前缀, 便于区分调用方
            executor_manager_factory: 执行器工厂(默认取模块级 ``get_executor_manager``)。
                调用方传入自己的模块级符号, 既能统一 CPU 隔离策略, 又保留可打桩的接缝。
            use_cpu_executor: True = 进程池(批量链路, 隔离 CPU 密集读取);
                False = 线程池(请求处理链路, 不派生进程)
        """
        self._strict = strict_allowed_roots
        self.log_prefix = log_prefix
        self._executor_manager_factory = executor_manager_factory
        self.use_cpu_executor = use_cpu_executor

    def _get_executor_manager(self):
        if self._executor_manager_factory is not None:
            return self._executor_manager_factory()
        from backend.services.executor_manager import get_executor_manager

        return get_executor_manager()

    # ------------------------------------------------------------------
    # 路径解析
    # ------------------------------------------------------------------
    @property
    def strict(self) -> bool:
        if self._strict is not None:
            return self._strict
        return os.getenv("DATA_SYNC_STRICT_ALLOWED_ROOTS", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _allowed_roots() -> List[Path]:
        from modules.core.path_manager import (
            get_data_input_dir,
            get_data_raw_dir,
            get_project_root,
        )

        project_root = get_project_root()
        roots = [
            get_data_input_dir(),
            get_data_raw_dir(),
            project_root / "downloads",
            project_root / "temp" / "outputs",
        ]

        extra_allowed = os.getenv("DATA_SYNC_ALLOWED_ROOTS", "").strip()
        if extra_allowed:
            for token in [
                part.strip() for part in extra_allowed.split(";") if part.strip()
            ]:
                candidate = Path(token)
                roots.append(
                    candidate if candidate.is_absolute() else (project_root / token)
                )
        return roots

    @staticmethod
    def _is_within_allowed_roots(resolved: Path, allowed_roots: List[Path]) -> bool:
        for root in allowed_roots:
            try:
                resolved.relative_to(Path(root).resolve())
                return True
            except (ValueError, OSError):
                continue
        return False

    @staticmethod
    def _contains_allowed_root_name(resolved_str: str, allowed_roots: List[Path]) -> bool:
        """额外检查: 路径中包含允许目录名(兼容路径拼写差异)。"""
        lowered = resolved_str.lower().replace("\\", "/")
        for root in allowed_roots:
            root_normalized = str(root).lower().replace("\\", "/").rstrip("/")
            if root_normalized and root_normalized in lowered:
                return True
        return False

    def _reject_or_pass(
        self,
        file_path: str,
        resolved_str: str,
        allowed_roots: List[Path],
    ) -> str:
        """路径越界时的处理: 严格模式抛错, 宽松模式记日志放行。"""
        if self.strict:
            raise ValueError(
                f"[SafePath] 文件路径不在允许的目录中: {file_path} -> {resolved_str} "
                f"(允许目录: {[str(root) for root in allowed_roots]})"
            )
        logger.info(
            "[%s] 文件路径不在允许根目录内(已放行): %s -> %s",
            self.log_prefix,
            file_path,
            resolved_str,
        )
        return resolved_str

    def resolve_safe_path(self, file_path: str) -> str:
        """安全解析文件路径。

        支持:
        - 绝对路径存在: 校验允许根后使用
        - 绝对路径不存在: 尝试从路径中提取相对部分(兼容云端部署与环境迁移)
        - 相对路径: 从项目根目录解析
        - 路径安全校验: 限制在允许的根目录内(严格模式抛错, 宽松模式放行)
        """
        from modules.core.path_manager import get_project_root

        project_root = get_project_root()
        path_obj = Path(file_path)
        allowed_roots = self._allowed_roots()

        if path_obj.is_absolute():
            if path_obj.exists():
                resolved = path_obj.resolve()
                if self._is_within_allowed_roots(resolved, allowed_roots):
                    return str(resolved)
                if self._contains_allowed_root_name(str(resolved), allowed_roots):
                    return str(resolved)
                return self._reject_or_pass(file_path, str(resolved), allowed_roots)

            # 绝对路径不存在: 尝试提取相对部分(兼容旧数据和环境迁移)
            path_str = str(file_path).replace("\\", "/")
            for key_path in _RELATIVE_KEY_PATHS:
                if key_path in path_str:
                    idx = path_str.find(key_path)
                    candidate = (project_root / path_str[idx:]).resolve()
                    if candidate.exists() and self._is_within_allowed_roots(
                        candidate, allowed_roots
                    ):
                        logger.info(
                            "[%s] 从绝对路径提取相对路径: %s -> %s",
                            self.log_prefix,
                            file_path,
                            candidate,
                        )
                        return str(candidate)

            logger.warning(
                "[%s] 绝对路径不存在且无法提取相对路径: %s", self.log_prefix, file_path
            )
            return self._reject_or_pass(file_path, str(file_path), allowed_roots)

        # 相对路径: 从项目根目录解析
        normalized = str(file_path).replace("\\", "/")
        resolved = (project_root / normalized).resolve()
        if self._is_within_allowed_roots(resolved, allowed_roots):
            return str(resolved)
        if self._contains_allowed_root_name(str(resolved), allowed_roots):
            return str(resolved)
        return self._reject_or_pass(file_path, str(resolved), allowed_roots)

    def resolve_runtime_path(self, file_path: str) -> str:
        """解析出「运行时可读」的表格路径(必要时产出标准化副本)。"""
        return self.normalize_runtime_path(self.resolve_safe_path(file_path))

    def normalize_runtime_path(self, resolved_path: str) -> str:
        """把已解析的路径转成「运行时可读」的表格路径(必要时产出标准化副本)。

        与 :meth:`resolve_runtime_path` 分开是为了保留
        ``_safe_resolve_path`` 这个可打桩的接缝 —— 调用方先解析再归一,
        测试可以只替换解析部分。
        """
        from backend.services.excel_parser import ExcelParser
        from backend.services.spreadsheet_normalization_service import (
            get_spreadsheet_normalization_service,
        )

        source_format = ExcelParser.detect_file_format(Path(resolved_path))
        if source_format in RUNTIME_NORMALIZATION_FORMATS:
            normalized = get_spreadsheet_normalization_service().normalize_for_runtime(
                resolved_path,
                source_format=source_format,
            )
            logger.info(
                "[%s] 使用标准化副本读取文件: %s -> %s (converter=%s, cache_hit=%s)",
                self.log_prefix,
                Path(resolved_path).name,
                normalized.path.name,
                normalized.converter,
                normalized.cache_hit,
            )
            return str(normalized.path)
        return str(resolved_path)

    # ------------------------------------------------------------------
    # 读表头
    # ------------------------------------------------------------------
    async def read_header(
        self,
        file_path: str,
        *,
        header_row: Optional[int] = 0,
        nrows: Optional[int] = 5,
    ) -> SpreadsheetHeader:
        """按表头行读取文件列(自行完成路径解析与格式归一)。

        Args:
            file_path: 文件路径(相对或绝对)
            header_row: 0-based 表头行; ``< 0`` 表示「无表头行」
            nrows: 读取行数限制
        """
        try:
            runtime_path = self.resolve_runtime_path(file_path)
        except Exception as exc:  # noqa: BLE001
            return SpreadsheetHeader(error=str(exc))
        return await self.read_columns(
            runtime_path, header_row=header_row, nrows=nrows
        )

    async def read_columns(
        self,
        runtime_path: str,
        *,
        header_row: Optional[int] = 0,
        nrows: Optional[int] = 5,
    ) -> SpreadsheetHeader:
        """从**已解析**的路径读取文件列。

        调用方如果已经做过路径解析(例如需要保留可打桩的解析接缝),
        用这个方法, 避免重复解析。
        """
        from backend.services.excel_parser import ExcelParser

        header_param = None if header_row is not None and header_row < 0 else header_row

        try:
            source_format = ExcelParser.detect_file_format(Path(runtime_path))
        except Exception:  # noqa: BLE001
            source_format = None

        try:
            executor_manager = self._get_executor_manager()
            runner = (
                executor_manager.run_cpu_intensive
                if self.use_cpu_executor
                else executor_manager.run_io_intensive
            )
            df = await runner(
                ExcelParser.read_excel,
                runtime_path,
                header=header_param,
                nrows=nrows,
            )
        except Exception as exc:  # noqa: BLE001
            return SpreadsheetHeader(
                runtime_path=runtime_path,
                source_format=source_format,
                error=str(exc),
            )

        columns: List[str] = []
        if df is not None:
            try:
                columns = [str(column) for column in df.columns.tolist()]
            except Exception:  # noqa: BLE001
                columns = []

        return SpreadsheetHeader(
            runtime_path=runtime_path,
            columns=columns,
            dataframe=df,
            header_row_used=header_param,
            source_format=source_format,
            normalized=bool(source_format in RUNTIME_NORMALIZATION_FORMATS),
        )


def get_spreadsheet_header_reader(
    *,
    strict_allowed_roots: Optional[bool] = None,
    log_prefix: str = "Header",
    executor_manager_factory: Optional[Any] = None,
    use_cpu_executor: bool = True,
) -> SpreadsheetHeaderReader:
    """获取统一读表头入口实例。"""
    return SpreadsheetHeaderReader(
        strict_allowed_roots=strict_allowed_roots,
        log_prefix=log_prefix,
        executor_manager_factory=executor_manager_factory,
        use_cpu_executor=use_cpu_executor,
    )
