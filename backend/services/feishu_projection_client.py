from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

# 飞书批量新增记录的单次上限。
#
# ⚠️ **base/v3 的上限是 200**（实测 + 官方文档），比旧版 bitable/v1 的 500 小。
# 超限时飞书会直接拒掉整批，代价是丢整批而不是丢一半——所以宁可保守。
FEISHU_BATCH_CREATE_LIMIT = 200

# 同一个数据表**不支持并发调用写接口**（错误码 1254291 Write conflict）。
# 批次之间必须留间隔，否则大批量写入会大面积冲突失败。
FEISHU_BATCH_WRITE_INTERVAL_SECONDS = 0.6


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

    async def batch_create_records(
        self,
        table_id: str,
        records: list[dict[str, Any]],
        base_token: str | None = None,
    ) -> int:
        """批量新增记录——**只新增，不 upsert**。

        用于「调价记录表」：每次最低售价变化就写一行新记录，
        行归档由飞书机器人负责，ERP 不查也不改已有的行。

        ⚠️ **端点必须是 base/v3**：旧版 `bitable/v1` 在当前的多维表格上会直接被拒
        （错误码 `99992402 field validation failed`），连只带主字段的最小请求都过不去。
        这是 2026-10-23 对真实表实测出来的，不是推测。

        `base_token` 允许覆盖默认的 base：「调价记录表」可能和三张状态镜像表
        **不在同一个多维表格**里，各自配置更安全。

        飞书侧的硬约束（实测 + 官方文档）：
        - 单次调用最多新增 **200** 条（base/v3 的上限，比旧版 bitable/v1 的 500 小）
        - 批量新增接口频率 50 次/秒
        - **同一张表不支持并发写**（1254291）→ 必须串行、批次间留间隔
        """
        if not (self.app_id and self.app_secret):
            # ⚠️ 不能用 `is_configured()`：它要求 `self.base_token` 非空，
            # 而调价记录表有自己的 base token，不一定和镜像表那个一样。
            raise RuntimeError("Feishu app credentials are not configured")
        if not records:
            return 0

        target_base = base_token or self.base_token
        if not target_base:
            raise RuntimeError("Feishu base token is not configured")

        created = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            token = await self._tenant_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            url = (
                f"{self.base_url}/open-apis/base/v3/bases/{target_base}"
                f"/tables/{table_id}/records/batch_create"
            )
            for offset in range(0, len(records), FEISHU_BATCH_CREATE_LIMIT):
                chunk = records[offset:offset + FEISHU_BATCH_CREATE_LIMIT]
                response = await client.post(
                    url, headers=headers, json={"create_records": chunk}
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") not in (0, None):
                    raise RuntimeError(
                        f"Feishu batch create failed: {payload.get('msg', 'unknown error')}"
                    )
                created += len(payload.get("data", {}).get("records") or chunk)
                # 同表不可并发写 → 批次之间必须留间隔
                if offset + FEISHU_BATCH_CREATE_LIMIT < len(records):
                    await asyncio.sleep(FEISHU_BATCH_WRITE_INTERVAL_SECONDS)
        return created

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
