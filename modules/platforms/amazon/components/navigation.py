from __future__ import annotations

from typing import Any
from modules.components.base import ExecutionContext
from modules.components.navigation.base import NavigationComponent, NavResult


class AmazonNavigation(NavigationComponent):
    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def run(self, page: Any, target: str | None = None) -> NavResult:  # type: ignore[override]
        if self.logger:
            self.logger.info(f"[AmazonNavigation] skeleton navigate to: {target}")
        return NavResult(success=True, url=page.url if hasattr(page, 'url') else '', message="skeleton")

