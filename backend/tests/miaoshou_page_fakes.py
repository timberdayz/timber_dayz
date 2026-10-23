"""妙手采集组件测试用的 Playwright 假对象。

设计要点：
- `click()` **必须支持 `force=` 关键字**。真实 Playwright 的
  `Locator.click(timeout=..., force=...)` 是公开 API；早期版本的假对象
  没有这个参数，导致生产代码里的 `force=True` 在测试里抛 TypeError，
  再被 `except Exception` 吞掉（spec §2.3 记录的踩坑点）。这里一次性对齐。
- `force=True` 会**穿透遮挡**（跳过 actionability 检查），普通 click 会被
  覆盖层拦截而超时——这是层 B 的行为测试能成立的前提。
- `wait_for()` 在「不可见」或「数量为 0」时抛 TimeoutError，对应真实页面
  「元素不存在 / 不可见」时 Playwright 的等待超时。
- `locator()` / `get_by_role()` / `get_by_text()` 是**按字符串分发的查表**，
  不是真实 DOM 树。真实页面上 `get_by_label("仓库")` 命中的是 `.jx-select`
  内部的 `<input role="combobox">`，而 `.jx-select` 容器是它的**祖先**；
  假对象里容器配成被选中元素的**子节点**，调用形状一致、方向相反。

导入约定：`backend/tests` 下没有 `__init__.py`，pytest 会把该目录加入
`sys.path`，因此同目录测试文件用 `from miaoshou_page_fakes import ...`。
"""

from __future__ import annotations

from typing import Any


class FakeTag:
    """单个 .jx-tag 文本节点。"""

    def __init__(self, text: str) -> None:
        self._text = text

    async def text_content(self) -> str:
        return self._text


class FakeTagList:
    """.jx-tag 集合：count() 返回标签数，nth(i) 返回第 i 个标签。"""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)

    async def count(self) -> int:
        return len(self._texts)

    def nth(self, index: int) -> FakeTag:
        return FakeTag(self._texts[index])


class FakeSelectedItem:
    """jx-select 的选中项容器（.jx-select__selected-item）。"""

    def __init__(self, tags: list[str]) -> None:
        self._tags = list(tags)

    @property
    def first(self) -> "FakeSelectedItem":
        return self

    async def count(self) -> int:
        return 1 if self._tags else 0

    def locator(self, query: str) -> Any:
        if query == ".jx-tag":
            return FakeTagList(self._tags)
        raise AssertionError(f"unexpected selected-item.locator({query!r})")


class FakeJxSelect:
    """妙手 jx-select 组件根节点。"""

    def __init__(self, tags: list[str]) -> None:
        self._tags = list(tags)

    def locator(self, query: str) -> Any:
        if query == ".jx-select__selected-item":
            return FakeSelectedItem(self._tags)
        raise AssertionError(f"unexpected jx-select.locator({query!r})")


class FakeJxSelectList:
    """page.locator('.jx-select') 返回的集合。"""

    def __init__(self, selects: list[FakeJxSelect]) -> None:
        self._selects = list(selects)

    async def count(self) -> int:
        return len(self._selects)

    def nth(self, index: int) -> FakeJxSelect:
        return self._selects[index]


class FakeLocator:
    """通用 Locator 替身。"""

    def __init__(
        self,
        *,
        text: str = "",
        visible: bool = True,
        count: int = 1,
        checked: bool = False,
        evaluate_checked: bool | None = None,
        intercept_clicks: bool = False,
        fail_clicks: int = 0,
        children: dict[str, Any] | None = None,
    ) -> None:
        self.text = text
        self.visible = visible
        self._count = count
        self.checked = checked
        self.evaluate_checked = evaluate_checked
        self.intercept_clicks = intercept_clicks
        self.fail_clicks = fail_clicks
        self.children: dict[str, Any] = children or {}
        self.clicked = 0
        self.click_calls: list[tuple[int | None, bool | None]] = []
        self.wait_calls: list[tuple[str, int | None]] = []

    # ── Locator 协议 ────────────────────────────────────────────────
    @property
    def first(self) -> "FakeLocator":
        return self

    @property
    def last(self) -> "FakeLocator":
        return self

    def nth(self, index: int) -> "FakeLocator":
        return self

    def locator(self, query: str) -> Any:
        return self.children.get(query, FakeLocator(count=0))

    def filter(self, **kwargs: Any) -> "FakeLocator":
        return self

    def get_by_role(self, role: str, name: Any = None) -> Any:
        return self.children.get(f"role:{role}:{name}", FakeLocator(count=0))

    def get_by_text(self, text: str, exact: bool = False) -> Any:
        return self.children.get(f"text:{text}", FakeLocator(count=0))

    async def count(self) -> int:
        return self._count

    async def wait_for(
        self, state: str = "visible", timeout: int | None = None
    ) -> None:
        self.wait_calls.append((state, timeout))
        if not self.visible or self._count == 0:
            raise TimeoutError(f"locator not available ({state}, count={self._count})")

    async def is_visible(self) -> bool:
        return self.visible and self._count > 0

    async def is_checked(self) -> bool:
        return self.checked

    async def evaluate(self, script: str) -> bool:
        if self.evaluate_checked is None:
            raise RuntimeError("evaluate not configured")
        return self.evaluate_checked

    async def text_content(self) -> str:
        return self.text

    async def focus(self, timeout: int | None = None) -> None:
        self.wait_calls.append(("focus", timeout))

    async def click(
        self, timeout: int | None = None, force: bool | None = None
    ) -> None:
        self.click_calls.append((timeout, force))
        if self.fail_clicks > 0:
            self.fail_clicks -= 1
            raise TimeoutError("locator.click: Timeout 1500ms exceeded")
        if self.intercept_clicks and not force:
            # 真实 Playwright 语义：命中测试被覆盖层拦截时普通 click 会超时，
            # 而 force=True 会跳过 actionability 检查从而穿透遮挡。
            raise TimeoutError(
                "locator.click: Timeout 1500ms exceeded\nCall log:\n"
                '  - <div class="jx-select__selected-item jx-select__placeholder is-transparent">'
                " intercepts pointer events"
            )
        self.clicked += 1


class FakeKeyboard:
    """键盘替身：记录按过的键。"""

    def __init__(self) -> None:
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class FakePage:
    """Page 替身：按选择器字符串分发到 FakeLocator。"""

    def __init__(self, *, locators: dict[str, Any] | None = None) -> None:
        self.locators: dict[str, Any] = locators or {}
        self.keyboard = FakeKeyboard()
        self.waits: list[tuple[str, int | None]] = []

    def locator(self, query: str) -> Any:
        return self.locators.get(query, FakeLocator(count=0))

    def get_by_role(self, role: str, name: Any = None) -> Any:
        return self.locators.get(f"role:{role}:{name}", FakeLocator(count=0))

    def get_by_text(self, text: str, exact: bool = False) -> Any:
        return self.locators.get(f"text:{text}", FakeLocator(count=0))

    def get_by_label(self, text: Any) -> Any:
        return self.locators.get("label:仓库", FakeLocator(count=0))

    async def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(("timeout", ms))
