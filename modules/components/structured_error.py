"""平台无关的结构化错误格式。

《规范》§3.5.1 要求「检测应结构化」：关键失败至少保留
``stage / status / reason / current_url / matched_signal / screenshot_path``
六个上下文字段，便于按阶段定位问题，而不是只留一句「失败了」。

边界（上游 spec §5.6「什么不下沉」）：

- **下沉到 `modules/components/`**：结构化错误的**格式与字段命名**（平台无关）
- **不下沉**：各平台的阶段名、失败前缀、选择器文案、截图落盘逻辑
  （留在各平台组件里）

用法::

    error = StructuredError.from_exception(
        exc,
        stage="export_dialog_ready",
        current_url=page.url,
        matched_signal="选择导出字段",
    )
    raise RuntimeError(build_stage_error_message("export_dialog_failed", error))
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StructuredError:
    """结构化错误上下文（字段与《规范》§3.5.1 一致）。"""

    stage: str
    status: str
    reason: str
    current_url: str = ""
    matched_signal: str = ""
    screenshot_path: str = ""

    def to_dict(self) -> dict[str, str]:
        """返回可 JSON 序列化的字典。"""
        return {
            "stage": self.stage,
            "status": self.status,
            "reason": self.reason,
            "current_url": self.current_url,
            "matched_signal": self.matched_signal,
            "screenshot_path": self.screenshot_path,
        }

    def to_message(self) -> str:
        """一行人类可读摘要。"""
        return (
            f"stage={self.stage} status={self.status} reason={self.reason} "
            f"current_url={self.current_url} matched_signal={self.matched_signal} "
            f"screenshot_path={self.screenshot_path}"
        )

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        stage: str,
        status: str = "failed",
        current_url: str = "",
        matched_signal: str = "",
        screenshot_path: str = "",
    ) -> "StructuredError":
        """从异常构造结构化错误（``reason`` 取异常文本，异常无文本时取类名）。"""
        reason = str(exc).strip() or exc.__class__.__name__
        return cls(
            stage=stage,
            status=status,
            reason=reason,
            current_url=str(current_url or ""),
            matched_signal=str(matched_signal or ""),
            screenshot_path=str(screenshot_path or ""),
        )


def build_stage_error_message(prefix: str, error: StructuredError) -> str:
    """阶段失败消息：保留既有失败前缀文案，追加结构化字段。

    ``prefix`` 是各平台既有的失败前缀（如 ``export_dialog_failed``），
    追加部分由 `StructuredError.to_message()` 提供。
    """
    return f"{prefix}: {error.to_message()}"
