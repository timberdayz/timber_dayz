#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def test_services_component_metadata_contract() -> None:
    from modules.platforms.shopee.components.services_export import ShopeeServicesExport
    from modules.platforms.shopee.components.services_ai_assistant_export import (
        ShopeeServicesAiAssistantExport,
    )
    from modules.platforms.shopee.components.services_agent_export import (
        ShopeeServicesAgentExport,
    )

    assert ShopeeServicesExport.platform == "shopee"
    assert ShopeeServicesExport.component_type == "export"
    assert ShopeeServicesExport.data_domain == "services"

    assert ShopeeServicesAiAssistantExport.data_domain == "services"
    assert ShopeeServicesAiAssistantExport.sub_domain == "ai_assistant"

    assert ShopeeServicesAgentExport.data_domain == "services"
    assert ShopeeServicesAgentExport.sub_domain == "agent"


def test_services_export_rejects_today_realtime_contract() -> None:
    from modules.components.base import ExecutionContext
    from modules.platforms.shopee.components.services_ai_assistant_export import (
        ShopeeServicesAiAssistantExport,
    )

    export_component = ShopeeServicesAiAssistantExport(
        ExecutionContext(platform="shopee", account={}, config={})
    )

    try:
        export_component._target_date_label({"preset": "today_realtime"})
    except ValueError as exc:
        assert "today_realtime" in str(exc)
        return

    raise AssertionError("services export should reject today_realtime preset")


if __name__ == "__main__":
    try:
        test_services_component_metadata_contract()
        test_services_export_rejects_today_realtime_contract()
        print("[services-contract-tests] all passed")
        sys.exit(0)
    except AssertionError as exc:
        print(f"[services-contract-tests] assertion failed: {exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"[services-contract-tests] unexpected error: {exc}")
        sys.exit(2)
