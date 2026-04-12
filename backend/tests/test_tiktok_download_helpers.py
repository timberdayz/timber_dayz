from __future__ import annotations

from pathlib import Path

import pytest

from modules.platforms.tiktok.components._download_helpers import (  # type: ignore[import-not-found]
    cleanup_download_capture,
    create_download_capture,
    resolve_export_timeout_ms,
    save_download_to_target,
)


class _FakeEmitter:
    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}

    def on(self, event: str, handler) -> None:  # noqa: ANN001
        self.handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler) -> None:  # noqa: ANN001
        self.handlers[event] = [existing for existing in self.handlers.get(event, []) if existing is not handler]

    def emit(self, event: str, payload) -> None:  # noqa: ANN001
        for handler in list(self.handlers.get(event, [])):
            handler(payload)


class _FakePage(_FakeEmitter):
    def __init__(self) -> None:
        super().__init__()
        self.context = _FakeEmitter()


class _FakeDownload:
    def __init__(self, *, content: str = "dummy") -> None:
        self.content = content

    async def save_as(self, path: str) -> None:
        Path(path).write_text(self.content, encoding="utf-8")


def test_resolve_export_timeout_ms_prefers_explicit_config() -> None:
    timeout = resolve_export_timeout_ms({"export_timeout_ms": 240000})

    assert timeout == 240000


def test_resolve_export_timeout_ms_uses_tiktok_safe_default_without_config() -> None:
    timeout = resolve_export_timeout_ms({})

    assert timeout == 90000


def test_create_download_capture_records_context_level_download_event() -> None:
    page = _FakePage()
    capture = create_download_capture(page)
    download = object()

    page.context.emit("download", download)

    assert capture.latest_download is download

    cleanup_download_capture(page, capture)


@pytest.mark.asyncio
async def test_save_download_to_target_requires_non_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "empty.xlsx"

    saved = await save_download_to_target(_FakeDownload(content=""), target)

    assert saved is None
