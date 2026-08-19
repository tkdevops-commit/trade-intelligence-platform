"""Read-only analysis helpers for the trade intelligence SQLite database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


EXPORT_INDICATOR = "TX.VAL.MRCH.CD.WT"
IMPORT_INDICATOR = "TM.VAL.MRCH.CD.WT"


class TradeAnalytics:
    """Query and derive dashboard-ready views without modifying source records."""

    def __init__(self, database_path: str | Path = "data/trade_intelligence.db") -> None:
        self.database_path = Path(database_path)

    def is_ready(self) -> bool:
        return self.database_path.is_file()

    def overview(self) -> dict[str, Any]:
        row = self._one("""
            SELECT COUNT(*) AS record_count,
                   COUNT(DISTINCT source) AS source_count,
                   COUNT(DISTINCT country) AS country_count,
                   MAX(collected_at) AS last_collected_at
            FROM trade_records
        """)
        return dict(row) if row else {"record_count": 0, "source_count": 0, "country_count": 0, "last_collected_at": None}

    def source_health(self) -> list[dict[str, Any]]:
        return self._all("""
            SELECT source, started_at, finished_at, records_seen, records_inserted, error
            FROM collection_runs
            WHERE id IN (SELECT MAX(id) FROM collection_runs GROUP BY source)
            ORDER BY source
        """)

    def countries(self) -> list[dict[str, str]]:
        rows = self._all("""
            SELECT country, metadata_json FROM trade_records
            WHERE source = 'world_bank_api' AND country IS NOT NULL
            GROUP BY country, metadata_json
            ORDER BY country
        """)
        countries: dict[str, str] = {}
        for row in rows:
            metadata = self._metadata(row["metadata_json"])
            countries[row["country"]] = metadata.get("country_name", row["country"])
        return [{"code": code, "name": name} for code, name in sorted(countries.items(), key=lambda item: item[1])]

    def trade_series(self, country: str) -> list[dict[str, Any]]:
        rows = self._all("""
            SELECT published_at, indicator, value
            FROM trade_records
            WHERE source = 'world_bank_api' AND country = ?
              AND indicator IN (?, ?)
            ORDER BY published_at, indicator
        """, (country, EXPORT_INDICATOR, IMPORT_INDICATOR))
        values: dict[str, dict[str, Any]] = {}
        for row in rows:
            year = str(row["published_at"] or "")[:4]
            if not year:
                continue
            point = values.setdefault(year, {"year": int(year), "exports": None, "imports": None, "trade_balance": None})
            if row["indicator"] == EXPORT_INDICATOR:
                point["exports"] = row["value"]
            else:
                point["imports"] = row["value"]
        for point in values.values():
            if point["exports"] is not None and point["imports"] is not None:
                point["trade_balance"] = point["exports"] - point["imports"]
        return [values[year] for year in sorted(values)]

    def news(self, search: str = "", limit: int = 50) -> list[dict[str, Any]]:
        search = search.strip()
        if search:
            pattern = f"%{search}%"
            return self._all("""
                SELECT title, published_at, url, summary FROM trade_records
                WHERE record_type = 'news' AND (title LIKE ? OR summary LIKE ?)
                ORDER BY published_at DESC LIMIT ?
            """, (pattern, pattern, limit))
        return self._all("""
            SELECT title, published_at, url, summary FROM trade_records
            WHERE record_type = 'news'
            ORDER BY published_at DESC LIMIT ?
        """, (limit,))

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _all(self, query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if not self.is_ready():
            return []
        with self._connection() as connection:
            return [dict(row) for row in connection.execute(query, parameters).fetchall()]

    def _one(self, query: str) -> sqlite3.Row | None:
        if not self.is_ready():
            return None
        with self._connection() as connection:
            return connection.execute(query).fetchone()

    @staticmethod
    def _metadata(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}
