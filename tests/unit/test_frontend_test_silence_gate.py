#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""哑测试 CI 门禁的自测。

**门禁自己最怕变成一个永远绿的摆设** —— 所以这里用真实的坏样本证明它会亮红灯：

1. 静态检查能抓到「引用了不存在的字面量路径」的测试；
2. 运行时检查能从 node --test 输出里认出「压根没跑起来」的失败；
3. 干净的目录不会误报。

不依赖数据库。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "scripts" / "ci_frontend_test_silence_gate.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "ci_frontend_test_silence_gate", GATE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _make_fixture(root: Path, *, broken: bool) -> Path:
    frontend = root / "frontend"
    scripts = frontend / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (frontend / "package.json").write_text(
        '{"name": "fixture", "private": true, "version": "0.0.0"}',
        encoding="utf-8",
    )
    target = (
        "src/domains/data_platform/views/Real.vue" if not broken else "src/Missing.vue"
    )
    (scripts / "sample.test.mjs").write_text(
        "import { readFileSync } from 'node:fs'\n"
        "import test from 'node:test'\n"
        "import assert from 'node:assert/strict'\n"
        "test('sample', () => {\n"
        f"  const source = readFileSync('{target}', 'utf8')\n"
        "  assert.ok(source.length >= 0)\n"
        "})\n",
        encoding="utf-8",
    )
    return frontend


def test_static_check_flags_missing_literal_path(tmp_path: Path):
    frontend = _make_fixture(tmp_path, broken=True)
    problems = gate.check_static_paths(frontend)
    assert problems, "坏样本必须被静态检查抓到"
    assert any("src/Missing.vue" in item for item in problems)


def test_static_check_passes_on_clean_fixture(tmp_path: Path):
    frontend = _make_fixture(tmp_path, broken=False)
    # 干净样本：被引用的文件不存在，但也不该误报成「路径不存在」？
    # —— 正确行为是**要报**，因为它同样是个哑测试。
    problems = gate.check_static_paths(frontend)
    assert any("src/domains/data_platform/views/Real.vue" in item for item in problems)

    # 真正干净的目录：把被引用的文件补上 ⇒ 零问题
    real = frontend / "src/domains/data_platform/views/Real.vue"
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text("<template></template>", encoding="utf-8")
    assert gate.check_static_paths(frontend) == []


def test_runtime_detector_recognizes_test_that_never_ran():
    output = (
        "not ok 1 - scripts/broken.test.mjs\n"
        "  ---\n"
        "  error:\n"
        "    code: 'ENOENT',\n"
        "    syscall: 'open',\n"
        "  ---\n"
        "  1/1 failing\n"
    )
    problems = gate.find_silent_runtime_failures(output)
    assert problems
    assert any("ENOENT" in item for item in problems)


def test_runtime_detector_ignores_ordinary_assertion_failures():
    output = (
        "not ok 1 - my tasks route is no longer admin only\n"
        "  ---\n"
        "  error:\n"
        "    expected: 'admin'\n"
        "    actual: 'user'\n"
        "  ---\n"
        "  1/1 failing\n"
    )
    assert gate.find_silent_runtime_failures(output) == []


def test_ordinary_failures_are_counted_but_not_gating():
    output = (
        "✖ my tasks route is no longer admin only (12ms)\n"
        "✖ visible menu snapshot stays stable for current non-admin roles (8ms)\n"
    )
    stats = gate.summarize_ordinary_failures(output)
    assert stats["ordinary_failures"] == 2
    assert gate.find_silent_runtime_failures(output) == []
