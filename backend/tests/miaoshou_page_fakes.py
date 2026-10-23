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
- 假对象带一棵**迷你 DOM 树**（`FakeLocator.child_nodes`），用来复现
  2026-10-23 在真实妙手页面取证到的仓库筛选结构（取证结论见
  `modules/platforms/miaoshou/components/inventory_config.py` 的注释）。
- `locator()` 支持**后代组合器**（空格或 `>>` 分隔），例如
  `"[data-field='warehouseIds'] .jx-select__wrapper"`；
  因此新增字段时**不需要**在夹具里硬编码组合选择器字符串。
- `get_attribute()` / `set_attribute()` 读写真实属性（如 `modelvaluegroup`），
  这是层 C「已全选」判据的数据来源。
- `evaluate()` 默认按节点自身状态推导勾选结果（`aria-checked` 属性或 class
  里的 `is-checked`），因此点击 label 翻转 class 之后，回读会自动跟随。

导入约定：`backend/tests` 下没有 `__init__.py`，pytest 会把该目录加入
`sys.path`，因此同目录测试文件用 `from miaoshou_page_fakes import ...`。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

# ── 迷你 CSS / XPath 解析（只覆盖妙手仓库筛选用到的语法）──────────────

_TAG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")
_ATTR_RE = re.compile(
    r"\[([A-Za-z_][\w:.-]*)\s*(?:=\s*(?:'([^']*)'|\"([^\"]*)\"|([^\]]*)))?\]"
)
_CLASS_RE = re.compile(r"\.([A-Za-z_][\w-]*)")

_XPATH_ANCESTOR_TOKEN = re.compile(
    r"^xpath=ancestor::\*\[contains\(concat\(' ', normalize-space\(@class\), ' '\), "
    r"' ([^']+) '\)\]\[1\]$"
)
_XPATH_ANCESTOR_SUBSTR = re.compile(
    r"^xpath=ancestor::\*\[contains\(@class,'([^']+)'\)\]\[1\]$"
)
_XPATH_FOLLOWING = re.compile(r"^xpath=following::\*\[(.+)\]\[1\]$")


@dataclass(frozen=True)
class _Compound:
    """CSS 复合选择器解析结果。"""

    tag: str = ""
    classes: frozenset[str] = frozenset()
    attrs: tuple[tuple[str, str | None], ...] = ()
    pseudos: frozenset[str] = frozenset()
    valid: bool = True


def _parse_compound(compound: str) -> _Compound:
    """解析 CSS 复合选择器（`.a.b`、`[attr='v']`、`tag.a:visible` 等）。"""
    attrs: list[tuple[str, str | None]] = []
    for match in _ATTR_RE.finditer(compound):
        value = match.group(2)
        if value is None:
            value = match.group(3)
        if value is None:
            value = match.group(4)
        attrs.append((match.group(1), value))
    rest = _ATTR_RE.sub("", compound)
    parts = rest.split(":")
    head = parts[0].strip()
    pseudos = {part.split("(", 1)[0].strip() for part in parts[1:] if part.strip()}
    pseudos.discard("")
    tag = ""
    classes: set[str] = set()
    valid = True
    if head:
        tokens = head.split(".")
        first = tokens[0]
        if first == "":
            classes = {token for token in tokens[1:] if token}
        elif _TAG_RE.match(first):
            tag = first
            classes = {token for token in tokens[1:] if token}
        else:
            # `text=...`、`has-text(...)` 之类的 Playwright 专有语法无法用
            # 迷你 CSS 匹配，标记为不可匹配即可（生产代码里它们只用于兜底）。
            valid = False
    return _Compound(tag, frozenset(classes), tuple(attrs), frozenset(pseudos), valid)


def _split_query(query: str) -> list[str]:
    """把查询串拆成后代组合器的各段（`>>` 与空格等价）。"""
    text = query.strip()
    if text.startswith("xpath="):
        return [text]
    return [part for part in text.replace(">>", " ").split() if part]


def _matches_compound(node: "FakeLocator", compound: str) -> bool:
    """判断节点是否命中单个 CSS 复合选择器。"""
    parsed = _parse_compound(compound)
    if not parsed.valid:
        return False
    if parsed.tag and node.tag and node.tag != parsed.tag:
        return False
    if not parsed.classes.issubset(node.class_tokens()):
        return False
    for name, value in parsed.attrs:
        if name not in node.attributes:
            return False
        if value is not None and node.attributes.get(name) != value:
            return False
    for pseudo in parsed.pseudos:
        if pseudo == "visible":
            if not node.effectively_visible:
                return False
        elif pseudo == "hidden":
            if node.effectively_visible:
                return False
        else:
            return False
    return True


def _collect_descendants(node: "FakeLocator", out: list["FakeLocator"]) -> None:
    """按文档顺序收集所有后代节点。"""
    for child in node.child_nodes:
        out.append(child)
        _collect_descendants(child, out)


def _document_order(node: "FakeLocator") -> list["FakeLocator"]:
    """返回节点所在树的文档顺序列表（根在前）。"""
    root = node
    while root.parent is not None:
        root = root.parent
    ordered: list[FakeLocator] = []
    _collect_descendants(root, ordered)
    return ordered


def _following_nodes(node: "FakeLocator") -> list["FakeLocator"]:
    """返回文档顺序上位于节点之后、且不属于其后代的节点。"""
    order = _document_order(node)
    if node not in order:
        return []
    descendants: list[FakeLocator] = []
    _collect_descendants(node, descendants)
    descendant_ids = {id(item) for item in descendants}
    start = order.index(node)
    return [item for item in order[start + 1 :] if id(item) not in descendant_ids]


def _xpath_predicate_matches(node: "FakeLocator", predicate: str) -> bool:
    """判断节点是否满足 xpath 谓词（只实现仓库筛选用到的两种）。"""
    compact = predicate.replace(" ", "")
    if compact == "@role='combobox'orself::input":
        return node.attributes.get("role") == "combobox" or node.tag == "input"
    role_match = re.match(r"^@role='([^']*)'$", compact)
    if role_match:
        return node.attributes.get("role") == role_match.group(1)
    if compact.startswith("self::"):
        return node.tag == compact[len("self::") :]
    return False


def _nearest_ancestor(
    node: "FakeLocator", *, token: str | None = None, needle: str | None = None
) -> "FakeLocator | None":
    """向上找最近的匹配祖先（class token 精确匹配或子串包含）。"""
    current = node.parent
    while current is not None:
        if token is not None and token in current.class_tokens():
            return current
        if needle is not None and needle in " ".join(sorted(current.class_tokens())):
            return current
        current = current.parent
    return None


def _resolve_xpath(scope: "FakeLocator", expression: str) -> "FakeLocator | None":
    """解析 `ancestor::*` / `following::*` 形式的 xpath（相对 scope 元素）。"""
    match = _XPATH_ANCESTOR_TOKEN.match(expression)
    if match:
        return _nearest_ancestor(scope, token=match.group(1))
    match = _XPATH_ANCESTOR_SUBSTR.match(expression)
    if match:
        return _nearest_ancestor(scope, needle=match.group(1))
    match = _XPATH_FOLLOWING.match(expression)
    if match:
        for node in _following_nodes(scope):
            if _xpath_predicate_matches(node, match.group(1)):
                return node
    return None


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
    """通用 Locator 替身（可作集合，也可作单个元素）。

    - **集合形态**（`locator()` / `get_by_*()` 的返回值）：
      `first` / `last` / `nth()` 取出命中的节点，`count()` 返回命中数量。
    - **元素形态**：直接承载 `visible` / `checked` / `text` / `attributes` 等状态。
    """

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
        nth_children: dict[int, "FakeLocator"] | None = None,
        check_on_click: bool = False,
        selector: str = "",
        attributes: dict[str, str] | None = None,
        label_text: str = "",
        on_click: Callable[[], None] | None = None,
        matches: list["FakeLocator"] | None = None,
        parent: "FakeLocator | None" = None,
    ) -> None:
        self.text = text
        self.visible = visible
        self._count = count
        self.checked = checked
        self.evaluate_checked = evaluate_checked
        self.intercept_clicks = intercept_clicks
        self.fail_clicks = fail_clicks
        self.children: dict[str, Any] = children or {}
        # nth(i) 的分派表：未登记的下标仍返回自身（保持旧行为）
        self.nth_children: dict[int, "FakeLocator"] = nth_children or {}
        # 点击后自动变为勾选态（模拟真实页面的复选框交互）
        self.check_on_click = check_on_click
        self.clicked = 0
        self.click_calls: list[tuple[int | None, bool | None]] = []
        self.wait_calls: list[tuple[str, int | None]] = []

        # ── DOM 树相关状态 ──
        self.selector = selector
        parsed = _parse_compound(selector) if selector else _Compound()
        self.tag = parsed.tag
        self.class_names: set[str] = set(parsed.classes)
        self.attributes: dict[str, str] = dict(attributes or {})
        self.label_text = label_text
        self.on_click = on_click
        self.child_nodes: list["FakeLocator"] = []
        self.parent = parent
        self._matches: list["FakeLocator"] | None = (
            list(matches) if matches is not None else None
        )

    # ── DOM 辅助 ────────────────────────────────────────────────────
    def class_tokens(self) -> set[str]:
        """节点的 class token 集合（selector + class 属性 + 显式设置）。"""
        tokens = set(self.class_names)
        tokens.update(t for t in self.attributes.get("class", "").split() if t)
        return tokens

    @property
    def effectively_visible(self) -> bool:
        """节点及其**所有祖先**都可见才算可见（对齐真实 CSS 的可见性继承）。

        真实页面上浮层收起时，浮层里的 listbox / header 也一起不可见；
        假对象若不继承，生产代码的「浮层是否已经打开」预检会误判。
        """
        node: "FakeLocator | None" = self
        while node is not None:
            if not node.visible:
                return False
            node = node.parent
        return True

    def add_child(self, child: "FakeLocator") -> "FakeLocator":
        """挂一个子节点（自动记录父子关系，供 xpath ancestor 使用）。"""
        child.parent = self
        self.child_nodes.append(child)
        return child

    def _iter_child_locators(self) -> Iterator[tuple[str, "FakeLocator"]]:
        """产出 (键, 子节点)：兼容 legacy children 字典与 DOM 树。"""
        for key, child in self.children.items():
            if isinstance(child, FakeLocator):
                yield key, child
        for child in self.child_nodes:
            yield child.selector, child

    def _search_compound(
        self, compound: str, scope: "FakeLocator | None" = None
    ) -> list["FakeLocator"]:
        """在 scope 的后代里查找命中 compound 的节点（文档顺序）。"""
        base = self if scope is None else scope
        results: list[FakeLocator] = []
        for key, child in base._iter_child_locators():
            if key == compound or _matches_compound(child, compound):
                results.append(child)
            results.extend(self._search_compound(compound, scope=child))
        return results

    def _search_chain(self, compounds: list[str]) -> list["FakeLocator"]:
        """按后代组合器逐段下钻，返回最终命中的节点。"""
        if len(compounds) == 1:
            compound = compounds[0]
            if compound.startswith("xpath="):
                node = _resolve_xpath(self, compound)
                return [node] if node is not None else []
            return self._search_compound(compound)
        return self._descend(self, compounds)

    def _descend(
        self, scope: "FakeLocator", compounds: list[str]
    ) -> list["FakeLocator"]:
        """在 scope 的后代里，按剩余复合选择器继续逐段下钻。

        ⚠️ 必须逐段收窄：`A B C` 命中的是「A 的后代里的 B 的后代里的 C」，
        只查前两段会把 B（更宽的元素）误当成最终结果。
        """
        results: list[FakeLocator] = []
        for node in self._search_compound(compounds[0], scope=scope):
            if len(compounds) == 1:
                results.append(node)
            else:
                results.extend(self._descend(node, compounds[1:]))
        return results

    # ── Locator 协议 ────────────────────────────────────────────────
    @property
    def first(self) -> "FakeLocator":
        if self._matches is not None:
            return self._matches[0] if self._matches else FakeLocator(count=0)
        return self.nth_children.get(0, self)

    @property
    def last(self) -> "FakeLocator":
        if self._matches is not None:
            return self._matches[-1] if self._matches else FakeLocator(count=0)
        return self

    def nth(self, index: int) -> "FakeLocator":
        if self._matches is not None:
            if 0 <= index < len(self._matches):
                return self._matches[index]
            return FakeLocator(count=0)
        return self.nth_children.get(index, self)

    def locator(self, query: str) -> Any:
        legacy = self.children.get(query)
        if legacy is not None:
            # 精确键命中：保持 legacy 语义（直接返回该节点/集合）
            return legacy
        results = self._search_chain(_split_query(query))
        return FakeLocator(matches=results, visible=any(r.visible for r in results))

    def filter(self, **kwargs: Any) -> "FakeLocator":
        return self

    def get_by_role(self, role: str, name: Any = None) -> Any:
        results = [
            node
            for node in self._descendants()
            if node.attributes.get("role") == role and _name_matches(node, name)
        ]
        if results:
            return FakeLocator(matches=results, visible=any(r.visible for r in results))
        legacy = self.children.get(f"role:{role}:{name}")
        if legacy is not None:
            return legacy
        return FakeLocator(count=0)

    def get_by_text(self, text: str, exact: bool = False) -> Any:
        results = [
            node for node in self._descendants() if _text_matches(node, text, exact)
        ]
        if results:
            return FakeLocator(matches=results, visible=any(r.visible for r in results))
        legacy = self.children.get(f"text:{text}")
        if legacy is not None:
            return legacy
        return FakeLocator(count=0)

    def _descendants(self) -> list["FakeLocator"]:
        """按文档顺序返回全部后代节点。"""
        ordered: list[FakeLocator] = []
        _collect_descendants(self, ordered)
        for key, child in self.children.items():
            if isinstance(child, FakeLocator):
                ordered.append(child)
        return ordered

    async def count(self) -> int:
        if self._matches is not None:
            return len(self._matches)
        return self._count

    async def wait_for(
        self, state: str = "visible", timeout: int | None = None
    ) -> None:
        self.wait_calls.append((state, timeout))
        if self._matches is not None:
            if not any(node.effectively_visible for node in self._matches):
                raise TimeoutError("locator not available (empty match)")
            return
        if not self.effectively_visible or self._count == 0:
            raise TimeoutError(f"locator not available ({state}, count={self._count})")

    async def is_visible(self) -> bool:
        if self._matches is not None:
            return any(node.effectively_visible for node in self._matches)
        return self.effectively_visible and self._count > 0

    async def is_checked(self) -> bool:
        """勾选状态：只有真正的复选框元素才有意义，其余按 Playwright 抛错。"""
        is_checkbox = self.tag == "input" and self.attributes.get("type") == "checkbox"
        if not is_checkbox:
            raise RuntimeError("not a checkbox or radio button")
        return self.checked

    async def evaluate(self, script: str) -> bool:
        """按节点自身状态推导勾选结果（对应真实页面的 class / aria 判定）。"""
        if self.evaluate_checked is not None:
            return self.evaluate_checked
        if self.attributes.get("aria-checked") == "true":
            return True
        if any("checked" in token for token in self.class_tokens()):
            return True
        return bool(self.checked)

    async def text_content(self) -> str:
        return self.text

    async def get_attribute(self, name: str) -> str | None:
        """读取节点属性（不存在返回 None，对齐真实 Playwright）。"""
        return self.attributes.get(name)

    def set_attribute(self, name: str, value: str) -> None:
        """设置节点属性。"""
        self.attributes[name] = value

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
        if self.check_on_click:
            # 真实页面：点击复选框后其勾选态变为 true
            self.checked = True
        if self.on_click is not None:
            self.on_click()


def _name_matches(node: FakeLocator, name: Any) -> bool:
    """无障碍名字匹配（支持正则；名字取节点文本）。"""
    if name is None:
        return True
    if isinstance(name, re.Pattern):
        return name.search(node.text) is not None
    return str(name) in node.text


def _text_matches(node: FakeLocator, text: Any, exact: bool) -> bool:
    """文本匹配（支持正则；`exact=True` 要求完全相等）。"""
    if isinstance(text, re.Pattern):
        return text.search(node.text) is not None
    if exact:
        return node.text == text
    return str(text) in node.text


class FakeDownload:
    """下载对象替身：save_as 落一个非空文件。"""

    def __init__(
        self,
        suggested_filename: str = "inventory_snapshot.xlsx",
        content: bytes = b"fake-export-bytes",
    ) -> None:
        self.suggested_filename = suggested_filename
        self._content = content
        self.saved_paths: list[str] = []

    async def save_as(self, path: str) -> None:
        self.saved_paths.append(path)
        with open(path, "wb") as handle:
            handle.write(self._content)


class FakeKeyboard:
    """键盘替身：记录按过的键。"""

    def __init__(self) -> None:
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class FakePage:
    """Page 替身：按选择器字符串分发到 FakeLocator。

    带 `root` 时走迷你 DOM 树解析（支持后代组合器）；没有 `root` 时退回
    `locators` 字典的精确字符串匹配（兼容早期测试写法）。
    """

    def __init__(
        self,
        *,
        locators: dict[str, Any] | None = None,
        url: str = "",
        root: FakeLocator | None = None,
    ) -> None:
        self.locators: dict[str, Any] = locators or {}
        self.root = root
        self.keyboard = FakeKeyboard()
        self.waits: list[tuple[str, int | None]] = []
        self.url = url
        self.goto_calls: list[str] = []
        self.screenshots: list[str] = []

    def locator(self, query: str) -> Any:
        if self.root is not None:
            results = self.root._search_chain(_split_query(query))
            if results:
                return FakeLocator(
                    matches=results, visible=any(r.visible for r in results)
                )
            return FakeLocator(count=0)
        return self.locators.get(query, FakeLocator(count=0))

    def get_by_role(self, role: str, name: Any = None) -> Any:
        if self.root is not None:
            results = [
                node
                for node in self.root._descendants()
                if node.attributes.get("role") == role and _name_matches(node, name)
            ]
            return FakeLocator(matches=results, visible=any(r.visible for r in results))
        return self.locators.get(f"role:{role}:{name}", FakeLocator(count=0))

    def get_by_text(self, text: str, exact: bool = False) -> Any:
        if self.root is not None:
            results = [
                node
                for node in self.root._descendants()
                if _text_matches(node, text, exact)
            ]
            return FakeLocator(matches=results, visible=any(r.visible for r in results))
        return self.locators.get(f"text:{text}", FakeLocator(count=0))

    def get_by_label(self, text: Any) -> Any:
        if self.root is not None:
            results = [
                node for node in self.root._descendants() if _label_matches(node, text)
            ]
            if results:
                return FakeLocator(
                    matches=results, visible=any(r.visible for r in results)
                )
            return FakeLocator(count=0)
        return self.locators.get(f"label:{text}", FakeLocator(count=0))

    async def goto(
        self, url: str, wait_until: str | None = None, timeout: int | None = None
    ) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def screenshot(self, path: str = "", **kwargs: Any) -> None:
        self.screenshots.append(path)
        if path:
            with open(path, "wb") as handle:
                handle.write(b"fake-screenshot")

    async def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(("timeout", ms))


def _label_matches(node: FakeLocator, text: Any) -> bool:
    """表单 label 匹配（取无障碍标签文本，支持正则）。"""
    label = node.label_text or node.attributes.get("aria-label", "")
    if isinstance(text, re.Pattern):
        return text.search(label) is not None
    return str(text) == label


class FakeDownloadInfo:
    """``expect_download`` 的 dl_info 替身：``value`` 是 awaitable。

    ``download=None`` 时 Future 永不 resolve（模拟干等的下载），
    ``download=<obj>`` 时立即 resolve（模拟下载先到）。
    """

    def __init__(self, download: Any = None) -> None:
        self._future: asyncio.Future = asyncio.Future()
        if download is not None:
            self._future.set_result(download)

    @property
    def value(self) -> Any:
        return self._future


class _FakeExpectDownload:
    """``expect_download`` 上下文管理器替身。"""

    def __init__(self, page: "FakeDownloadPage") -> None:
        self._page = page

    async def __aenter__(self) -> FakeDownloadInfo:
        return self._page.dl_info

    async def __aexit__(self, *args: Any) -> bool:
        return False


class FakeDownloadPage(FakePage):
    """带 pageerror 事件与 expect_download 的 page 替身。"""

    def __init__(self, *, download: Any = None, url: str = "") -> None:
        super().__init__(url=url)
        self.handlers: dict[str, Any] = {}
        self.dl_info = FakeDownloadInfo(download)

    def on(self, event_name: str, handler: Any) -> None:
        self.handlers[event_name] = handler

    def remove_listener(self, event_name: str, handler: Any) -> None:
        if self.handlers.get(event_name) is handler:
            self.handlers.pop(event_name, None)

    def expect_download(self, *, timeout: int | None = None) -> _FakeExpectDownload:
        return _FakeExpectDownload(self)

    def emit_pageerror(self, error: Any) -> None:
        """触发 pageerror 事件（模拟页面 JS 抛错）。"""
        handler = self.handlers.get("pageerror")
        if handler is not None:
            handler(error)
