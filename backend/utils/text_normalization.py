from __future__ import annotations

import re


_PLACEHOLDER_RE = re.compile(r"\?{3,}|\(\d+\?\)")
_MOJIBAKE_HINT_RE = re.compile(r"[ÃÅÆÐÑØÞßà-ÿ]")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _score_human_text(value: str | None) -> tuple[int, int, int]:
    text = value or ""
    return (
        len(_CJK_RE.findall(text)),
        -len(_MOJIBAKE_HINT_RE.findall(text)),
        -text.count("?"),
    )


def repair_mojibake_text(value: str | None) -> str | None:
    text = _strip_or_none(value)
    if text is None:
        return None

    try:
        repaired = text.encode("latin1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text

    if _score_human_text(repaired) > _score_human_text(text):
        return repaired.strip() or None
    return text


def is_placeholder_text(value: str | None) -> bool:
    text = _strip_or_none(value)
    if text is None:
        return False
    return bool(_PLACEHOLDER_RE.search(text))


def normalize_human_text(value: str | None) -> str | None:
    text = repair_mojibake_text(value)
    if is_placeholder_text(text):
        return None
    return _strip_or_none(text)


def coalesce_human_text(*values: str | None) -> str | None:
    for value in values:
        normalized = normalize_human_text(value)
        if normalized is not None:
            return normalized
    return None


def normalize_alias_text(value: str | None) -> str | None:
    return normalize_human_text(value)


_ALIAS_PLATFORM_PREFIX_RE = re.compile(
    r"^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*",
    re.IGNORECASE,
)
_ALIAS_SEPARATOR_RE = re.compile(r"[\s_()/-]+")


def normalize_alias_key(value: str | None) -> str:
    """把原始导出标签规范化成匹配键。

    规则必须与 SQL 侧完全一致（剥平台前缀 -> 小写 -> 折叠空白 -> 删分隔符），
    否则「认领了却匹配不上」。唯一真源是本函数；SQL 侧只允许使用存储好的
    ``alias_normalized``，不得再做第二次规范化。

    Args:
        value: 原始标签，例如 ``TK-新加坡-1店``

    Returns:
        规范化后的匹配键，例如 ``新加坡1店``
    """
    text = str(value or "").strip()
    if not text:
        return ""
    text = _ALIAS_PLATFORM_PREFIX_RE.sub("", text, count=1)
    text = text.strip().lower()
    text = _ALIAS_SEPARATOR_RE.sub("", text)
    return text.strip()
