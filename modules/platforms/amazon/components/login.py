from __future__ import annotations

from typing import Any
from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent, LoginResult


class AmazonLogin(LoginComponent):
    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def run(self, page: Any) -> LoginResult:  # type: ignore[override]
        if self.logger:
            self.logger.info("[AmazonLogin] skeleton login (no-op)")
        return LoginResult(success=True, message="skeleton")

