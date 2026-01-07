from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from modules.components.base import ComponentBase, ResultBase


@dataclass
class LoginResult(ResultBase):
    profile_path: Optional[str] = None


class LoginComponent(ComponentBase):
    """Abstract login component.

    Implementations should take account.login_url as the only entry URL.
    """

    def run(self, page: Any) -> LoginResult:  # type: ignore[override]
        raise NotImplementedError

