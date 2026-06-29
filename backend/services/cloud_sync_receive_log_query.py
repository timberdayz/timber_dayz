from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, text


class CloudSyncReceiveLogQuery:
    """Read cloud-side receive ledger for runtime health and metrics."""

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or os.getenv("CLOUD_DATABASE_URL")

    def _engine(self):
        if not self.database_url:
            raise RuntimeError("CLOUD_DATABASE_URL is not configured")
        return create_engine(self.database_url)

    def get_latest_receive_summary(self) -> dict[str, Any]:
        engine = self._engine()
        try:
            with engine.connect() as conn:
                latest = conn.execute(
                    text(
                        """
                        SELECT created_at
                        FROM ops.cloud_sync_receive_log
                        WHERE status = 'completed'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    )
                ).scalar()
                rows = conn.execute(
                    text(
                        """
                        SELECT DISTINCT ON (source_table_name)
                            source_table_name,
                            created_at
                        FROM ops.cloud_sync_receive_log
                        WHERE status = 'completed'
                        ORDER BY source_table_name, created_at DESC
                        """
                    )
                ).mappings().all()
        finally:
            engine.dispose()

        return {
            "available": True,
            "last_receive_at": self._serialize_dt(latest),
            "table_receives": {
                row["source_table_name"]: self._serialize_dt(row["created_at"])
                for row in rows
            },
        }

    @staticmethod
    def _serialize_dt(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
