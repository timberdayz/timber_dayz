"""
Component core abstractions

Purpose:
- Provide base classes and common types for all collection components
- Unify logging, timeout, retry, and result typing across platforms

This file only defines abstract interfaces (no side effects).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, Union


class ComponentError(RuntimeError):
    """Base error for component execution."""


@dataclass
class ResultBase:
    """Base result type returned by components."""

    success: bool
    message: str = ""
    details: Optional[dict[str, Any]] = None


class SupportsLogger(Protocol):  # narrowing for injected loggers
    def info(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def error(self, msg: str, *args: Any, **kwargs: Any) -> None: ...


@dataclass
class ExecutionContext:
    """Lightweight execution context delivered to components.

    Attributes:
        platform: Platform identifier (e.g., "shopee")
        account: Opaque account dict (must include login_url for web flows)
        logger: Optional structured logger
        config: Arbitrary extra config map
        step_callback: Optional callback for step progress (v4.8.0)
        step_prefix: Step ID prefix for nested components (v4.8.0)
        is_test_mode: Whether running in test mode (v4.8.0)
    """

    platform: str
    account: dict[str, Any]
    logger: Optional[SupportsLogger] = None
    config: Optional[dict[str, Any]] = None
    # v4.8.0: Step callback for test progress reporting
    step_callback: Optional[Callable[[str, dict[str, Any]], Any]] = None
    # v4.8.0: Step ID prefix for nested component calls (e.g., "parent.child.")
    step_prefix: str = ""
    # v4.8.0: Test mode flag
    is_test_mode: bool = False


async def call_step_callback(
    ctx: ExecutionContext,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Safely call step callback (supports sync and async, catches exceptions).
    
    v4.8.0: Utility function for step progress reporting.
    
    Args:
        ctx: Execution context containing the callback
        event_type: Event type ('step_start', 'step_success', 'step_failed')
        data: Event data (step_id, action, duration_ms, error, etc.)
    
    Note:
        - Callback errors are caught and logged, never propagated
        - Step IDs are automatically prefixed with ctx.step_prefix
        - Supports both sync and async callbacks
    """
    if not ctx.step_callback:
        return
    
    try:
        # Apply step prefix to step_id
        if 'step_id' in data and ctx.step_prefix:
            data = data.copy()
            data['step_id'] = f"{ctx.step_prefix}{data['step_id']}"
        
        # Handle both sync and async callbacks
        if asyncio.iscoroutinefunction(ctx.step_callback):
            await ctx.step_callback(event_type, data)
        else:
            ctx.step_callback(event_type, data)
    except Exception as e:
        # Callback errors should never affect component execution
        if ctx.logger:
            ctx.logger.warning(f"Step callback error (ignored): {e}")


class ComponentBase(ABC):
    """Abstract base class for all components.

    Concrete implementations should be side‑effect free on import.
    """

    def __init__(self, ctx: ExecutionContext) -> None:
        self.ctx = ctx

    @property
    def logger(self) -> Optional[SupportsLogger]:
        return self.ctx.logger
    
    async def report_step(
        self,
        event_type: str,
        step_id: str,
        action: str = "",
        duration_ms: int = 0,
        error: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Report step progress via callback (v4.8.0).
        
        Convenience method for components to report step progress.
        
        Args:
            event_type: 'step_start', 'step_success', or 'step_failed'
            step_id: Unique step identifier within this component
            action: Human-readable action description
            duration_ms: Step duration in milliseconds (for success/failed)
            error: Error message (for step_failed)
            **extra: Additional data to include
        """
        data = {
            'step_id': step_id,
            'action': action,
            **extra,
        }
        if duration_ms > 0:
            data['duration_ms'] = duration_ms
        if error:
            data['error'] = error
        
        await call_step_callback(self.ctx, event_type, data)

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> ResultBase:  # pragma: no cover - interface only
        """Execute component main action and return a ResultBase.

        Implementations should:
        - Use explicit waits over sleeps where possible
        - Provide meaningful messages and details
        - Raise ComponentError for unrecoverable errors
        """
        raise NotImplementedError

