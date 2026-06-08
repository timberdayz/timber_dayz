from __future__ import annotations

import re
from pathlib import Path

from backend.services.semantic_field_registry import SEMANTIC_FIELD_META


def test_frontend_semantic_registry_keys_match_backend_contract():
    frontend_registry = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "domains"
        / "data_platform"
        / "utils"
        / "headerBindings.js"
    )
    source = frontend_registry.read_text(encoding="utf-8")
    match = re.search(
        r"export const SEMANTIC_FIELD_META = \{(?P<body>.*?)\n\}",
        source,
        re.S,
    )
    assert match, "frontend SEMANTIC_FIELD_META export was not found"

    frontend_keys = set(re.findall(r"^\s{2}([a-z][a-z0-9_]*):\s*\{", match.group("body"), re.M))
    for assign_body in re.findall(
        r"Object\.assign\(SEMANTIC_FIELD_META,\s*\{(?P<body>.*?)\n\}\)",
        source,
        re.S,
    ):
        frontend_keys.update(re.findall(r"^\s{2}([a-z][a-z0-9_]*):\s*\{", assign_body, re.M))

    assert frontend_keys == set(SEMANTIC_FIELD_META)
