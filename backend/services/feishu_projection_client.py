from __future__ import annotations

import os
from typing import Any

import httpx


class FeishuProjectionClient:
    def __init__(self) -> None:
        self.app_id = os.getenv("FEISHU_PRODUCT_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_PRODUCT_APP_SECRET", "")
        self.base_token = os.getenv("FEISHU_PRODUCT_BASE_TOKEN", "")
        self.base_url = os.getenv("FEISHU_OPEN_BASE_URL", "https://open.feishu.cn")

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret and self.base_token)

    async def _tenant_token(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") not in (0, None) or not payload.get("tenant_access_token"):
            raise RuntimeError(f"Feishu tenant token request failed: {payload.get('msg', 'unknown error')}")
        return payload["tenant_access_token"]

    async def upsert_record(self, table_id: str, key_field: str, key_value: str, fields: dict[str, Any]) -> None:
        if not self.is_configured():
            raise RuntimeError("Feishu product projection credentials are not configured")
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await self._tenant_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            base = f"{self.base_url}/open-apis/bitable/v1/apps/{self.base_token}/tables/{table_id}/records"
            search = await client.post(
                f"{base}/search",
                headers=headers,
                json={
                    "page_size": 1,
                    "filter": {
                        "conjunction": "and",
                        "conditions": [{"field_name": key_field, "operator": "is", "value": [key_value]}],
                    },
                },
            )
            search.raise_for_status()
            search_data = search.json().get("data", {})
            items = search_data.get("items", [])
            if items:
                response = await client.put(f"{base}/{items[0]['record_id']}", headers=headers, json={"fields": fields})
            else:
                response = await client.post(base, headers=headers, json={"fields": fields})
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") not in (0, None):
                raise RuntimeError(f"Feishu record upsert failed: {payload.get('msg', 'unknown error')}")

    async def create_table(self, name: str, fields: list[dict[str, Any]]) -> str:
        if not self.is_configured():
            raise RuntimeError("Feishu product projection credentials are not configured")
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await self._tenant_token(client)
            response = await client.post(
                f"{self.base_url}/open-apis/bitable/v1/apps/{self.base_token}/tables",
                headers={"Authorization": f"Bearer {token}"},
                json={"table": {"name": name, "fields": fields}},
            )
            response.raise_for_status()
            payload = response.json()
            table_id = payload.get("data", {}).get("table_id") or payload.get("data", {}).get("table", {}).get("table_id")
            if payload.get("code") not in (0, None) or not table_id:
                raise RuntimeError(f"Feishu table create failed: {payload.get('msg', 'unknown error')}")
            return table_id
