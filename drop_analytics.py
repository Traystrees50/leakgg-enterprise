import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, Optional, Tuple, Union

from models import BonusCodeItem

ANALYTICS_DB_PATH = os.getenv("DROP_ANALYTICS_DB", "drop_analytics.db")


class DropAnalytics:
    """Local, dependency-free drop history and notification analytics."""

    def __init__(self, path: str = ANALYTICS_DB_PATH):
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS drop_history (
                    platform TEXT NOT NULL,
                    code TEXT NOT NULL,
                    source_name TEXT,
                    source_url TEXT,
                    amount_value TEXT,
                    wager_requirement TEXT,
                    claims_count TEXT,
                    availability_status TEXT,
                    event_type TEXT,
                    is_highroller INTEGER NOT NULL DEFAULT 0,
                    image_url TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    sightings INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (platform, code)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT,
                    platform TEXT NOT NULL,
                    code TEXT NOT NULL,
                    delivered INTEGER NOT NULL,
                    attempted_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_drop_history_seen ON drop_history(first_seen_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_delivery_guild_attempt ON delivery_history(guild_id, attempted_at)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_drop(self, item: BonusCodeItem, availability_status: str = "UNKNOWN") -> None:
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO drop_history (
                    platform, code, source_name, source_url, amount_value,
                    wager_requirement, claims_count, availability_status,
                    event_type, is_highroller, image_url, first_seen_at,
                    last_seen_at, sightings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(platform, code) DO UPDATE SET
                    source_name = excluded.source_name,
                    source_url = excluded.source_url,
                    amount_value = excluded.amount_value,
                    wager_requirement = excluded.wager_requirement,
                    claims_count = excluded.claims_count,
                    availability_status = CASE
                        WHEN excluded.availability_status = 'UNKNOWN'
                        THEN drop_history.availability_status
                        ELSE excluded.availability_status
                    END,
                    event_type = excluded.event_type,
                    is_highroller = excluded.is_highroller,
                    image_url = excluded.image_url,
                    last_seen_at = excluded.last_seen_at,
                    sightings = drop_history.sightings + 1
                """,
                (
                    item.platform.value,
                    item.clean_code,
                    item.source_name,
                    item.source_url,
                    item.amount_value,
                    item.wager_requirement,
                    item.claims_count,
                    availability_status or "UNKNOWN",
                    item.event_type,
                    int(item.is_highroller),
                    item.image_url,
                    now,
                    now,
                ),
            )

    def record_delivery(
        self,
        item: BonusCodeItem,
        guild_id: Optional[Union[int, str]],
        delivered: bool,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO delivery_history (guild_id, platform, code, delivered, attempted_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(guild_id) if guild_id is not None else None,
                    item.platform.value,
                    item.clean_code,
                    int(delivered),
                    self._now(),
                ),
            )

    def has_successful_delivery(self, item: BonusCodeItem, guild_id: Union[int, str]) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM delivery_history
                WHERE guild_id = ? AND platform = ? AND code = ? AND delivered = 1
                LIMIT 1
                """,
                (str(guild_id), item.platform.value, item.clean_code),
            ).fetchone()
        return row is not None

    def get_stats(self, days: int = 7, guild_id: Optional[Union[int, str]] = None) -> Dict[str, Any]:
        days = max(1, min(int(days), 365))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connection() as connection:
            drops = connection.execute(
                "SELECT * FROM drop_history WHERE first_seen_at >= ? ORDER BY first_seen_at DESC",
                (cutoff,),
            ).fetchall()
            deliveries_query = (
                "SELECT platform, code, delivered FROM delivery_history "
                "WHERE attempted_at >= ?"
            )
            delivery_params: Tuple[Any, ...]
            if guild_id is None:
                delivery_params = (cutoff,)
            else:
                deliveries_query += " AND guild_id = ?"
                delivery_params = (cutoff, str(guild_id))
            deliveries = connection.execute(deliveries_query, delivery_params).fetchall()

        if guild_id is not None:
            delivered_keys = {
                (row["platform"], row["code"])
                for row in deliveries
                if row["delivered"]
            }
            drops = [
                row for row in drops
                if (row["platform"], row["code"]) in delivered_keys
            ]

        by_platform = Counter(row["platform"] for row in drops)
        by_source = Counter(row["source_name"] or "Unknown" for row in drops)
        by_hour = Counter()
        for row in drops:
            try:
                hour = datetime.fromisoformat(row["first_seen_at"].replace("Z", "+00:00"))
                by_hour[hour.strftime("%H:00 UTC")] += 1
            except (TypeError, ValueError):
                continue

        return {
            "period_days": days,
            "guild_id": str(guild_id) if guild_id is not None else None,
            "total_drops": len(drops),
            "platform_breakdown": by_platform.most_common(),
            "source_leaderboard": by_source.most_common(10),
            "hourly_heatmap": dict(sorted(by_hour.items())),
            "reported_value_count": sum(bool(row["amount_value"]) for row in drops),
            "delivered_notifications": sum(bool(row["delivered"]) for row in deliveries),
            "failed_notifications": sum(not bool(row["delivered"]) for row in deliveries),
            "recent_history": [dict(row) for row in drops[:15]],
        }


_default_store: Optional[DropAnalytics] = None


def get_store() -> DropAnalytics:
    global _default_store
    if _default_store is None:
        _default_store = DropAnalytics()
    return _default_store
