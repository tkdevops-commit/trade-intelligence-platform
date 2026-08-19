"""Polite, source-aware collectors for public trade intelligence data.

This module intentionally uses official RSS feeds and documented public APIs. It
does not bypass authentication, robots directives, CAPTCHAs, or terms of use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

LOG = logging.getLogger(__name__)
USER_AGENT = "TradeIntelligencePlatform/0.1 (public-data collector)"


@dataclass(frozen=True)
class TradeRecord:
    """A normalised article, policy event, or numeric trade observation."""

    source: str
    record_type: str
    title: str
    published_at: str | None = None
    url: str | None = None
    country: str | None = None
    indicator: str | None = None
    value: float | None = None
    unit: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def fingerprint(self) -> str:
        identity = "|".join(
            str(value or "")
            for value in (self.source, self.record_type, self.url, self.country, self.indicator, self.published_at, self.title)
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class TradeDatabase:
    """Small SQLite persistence layer with idempotent inserts."""

    def __init__(self, path: str | Path = "data/trade_intelligence.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialise()

    def _initialise(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trade_records (
                id INTEGER PRIMARY KEY,
                fingerprint TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                record_type TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT,
                url TEXT,
                country TEXT,
                indicator TEXT,
                value REAL,
                unit TEXT,
                summary TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                collected_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trade_records_source ON trade_records(source);
            CREATE INDEX IF NOT EXISTS idx_trade_records_published_at ON trade_records(published_at);
            CREATE TABLE IF NOT EXISTS collection_runs (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                records_seen INTEGER NOT NULL DEFAULT 0,
                records_inserted INTEGER NOT NULL DEFAULT 0,
                error TEXT
            );
            """
        )
        self.connection.commit()

    def insert_records(self, records: Iterable[TradeRecord]) -> tuple[int, int]:
        seen = inserted = 0
        collected_at = datetime.now(timezone.utc).isoformat()
        for record in records:
            seen += 1
            cursor = self.connection.execute(
                """
                INSERT OR IGNORE INTO trade_records
                (fingerprint, source, record_type, title, published_at, url, country,
                 indicator, value, unit, summary, metadata_json, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.fingerprint, record.source, record.record_type, record.title,
                    record.published_at, record.url, record.country, record.indicator,
                    record.value, record.unit, record.summary,
                    json.dumps(record.metadata or {}, sort_keys=True), collected_at,
                ),
            )
            inserted += cursor.rowcount
        self.connection.commit()
        return seen, inserted

    def close(self) -> None:
        self.connection.close()


class HttpClient:
    """A deliberately conservative HTTP client for public endpoints."""

    def __init__(self, minimum_interval_seconds: float = 1.0, timeout_seconds: int = 30) -> None:
        self.minimum_interval_seconds = minimum_interval_seconds
        self.timeout_seconds = timeout_seconds
        self._last_request_at = 0.0

    def get_bytes(self, url: str) -> bytes:
        delay = self.minimum_interval_seconds - (time.monotonic() - self._last_request_at)
        if delay > 0:
            time.sleep(delay)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, application/xml, text/xml"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                self._last_request_at = time.monotonic()
                return response.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"HTTP {error.code} from {url}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Could not reach {url}: {error.reason}") from error

    def get_json(self, url: str) -> Any:
        return json.loads(self.get_bytes(url).decode("utf-8"))


class TradeCollector:
    """Collect a curated set of official trade news and macro-trade indicators."""

    WTO_RSS_URL = "https://www.wto.org/library/rss/latest_news_e.xml"
    WORLD_BANK_BASE_URL = "https://api.worldbank.org/v2"
    COMTRADE_PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"

    def __init__(self, database: TradeDatabase, client: HttpClient | None = None) -> None:
        self.database = database
        self.client = client or HttpClient()

    def collect_wto_news(self) -> list[TradeRecord]:
        root = ET.fromstring(self.client.get_bytes(self.WTO_RSS_URL))
        records: list[TradeRecord] = []
        for item in root.findall(".//item"):
            title = self._xml_text(item, "title")
            link = self._xml_text(item, "link")
            if not title or not link:
                continue
            records.append(TradeRecord(
                source="wto_rss", record_type="news", title=title, url=link,
                published_at=self._xml_text(item, "pubDate"),
                summary=self._xml_text(item, "description"),
                metadata={"publisher": "World Trade Organization"},
            ))
        return records

    def collect_world_bank_trade(self, countries: Iterable[str], years: int = 3) -> list[TradeRecord]:
        current_year = datetime.now(timezone.utc).year
        start_year = current_year - years
        country_list = ";".join(code.lower() for code in countries)
        indicators = {
            "TX.VAL.MRCH.CD.WT": "Merchandise exports (current US$)",
            "TM.VAL.MRCH.CD.WT": "Merchandise imports (current US$)",
        }
        records: list[TradeRecord] = []
        for code, name in indicators.items():
            parameters = {"format": "json", "date": f"{start_year}:{current_year}", "per_page": 1000}
            endpoint = f"{self.WORLD_BANK_BASE_URL}/country/{country_list}/indicator/{code}"
            payload = self.client.get_json(f"{endpoint}?{urllib.parse.urlencode(parameters)}")
            payloads = [payload]
            page_count = int(payload[0].get("pages", 1)) if isinstance(payload, list) and payload and isinstance(payload[0], dict) else 1
            for page in range(2, page_count + 1):
                payloads.append(self.client.get_json(f"{endpoint}?{urllib.parse.urlencode({**parameters, 'page': page})}"))
            for page_payload in payloads:
                if not isinstance(page_payload, list) or len(page_payload) < 2 or not page_payload[1]:
                    continue
                for observation in page_payload[1]:
                    if observation.get("value") is None:
                        continue
                    records.append(TradeRecord(
                        source="world_bank_api", record_type="indicator", title=name,
                        published_at=f"{observation['date']}-12-31",
                        country=observation["country"]["id"], indicator=code,
                        value=float(observation["value"]), unit="current USD",
                        metadata={"country_name": observation["country"]["value"], "source": "World Development Indicators"},
                    ))
        return records

    def collect_comtrade_preview(self, reporter_code: str, period: str) -> list[TradeRecord]:
        """Collect a small preview only; use a subscribed API for production volumes."""
        query = urllib.parse.urlencode({"flowCode": "X", "reporterCode": reporter_code, "period": period})
        payload = self.client.get_json(f"{self.COMTRADE_PREVIEW_URL}?{query}")
        data = payload.get("data", []) if isinstance(payload, dict) else []
        records: list[TradeRecord] = []
        for row in data:
            title = row.get("cmdDesc") or row.get("cmdCode") or "UN Comtrade observation"
            records.append(TradeRecord(
                source="un_comtrade_preview", record_type="trade_flow", title=str(title),
                published_at=str(row.get("period") or period), country=str(row.get("reporterCode") or reporter_code),
                indicator="export_value", value=self._number(row.get("primaryValue")), unit="current USD",
                metadata={key: row.get(key) for key in ("flowCode", "partnerCode", "cmdCode", "cmdDesc", "reporterDesc", "partnerDesc")},
            ))
        return records

    def run(self, source: str, countries: Iterable[str], years: int, reporter_code: str, period: str) -> dict[str, dict[str, int | str]]:
        collectors = {
            "wto": self.collect_wto_news,
            "world-bank": lambda: self.collect_world_bank_trade(countries, years),
            "comtrade-preview": lambda: self.collect_comtrade_preview(reporter_code, period),
        }
        selected = collectors.keys() if source == "all" else [source]
        results: dict[str, dict[str, int | str]] = {}
        for name in selected:
            if name not in collectors:
                raise ValueError(f"Unknown source: {name}")
            started_at = datetime.now(timezone.utc).isoformat()
            run_id = self.database.connection.execute("INSERT INTO collection_runs (source, started_at) VALUES (?, ?)", (name, started_at)).lastrowid
            try:
                seen, inserted = self.database.insert_records(collectors[name]())
                self.database.connection.execute("UPDATE collection_runs SET finished_at = ?, records_seen = ?, records_inserted = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), seen, inserted, run_id))
                self.database.connection.commit()
                results[name] = {"seen": seen, "inserted": inserted}
            except Exception as error:
                self.database.connection.execute("UPDATE collection_runs SET finished_at = ?, error = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), str(error), run_id))
                self.database.connection.commit()
                LOG.exception("Collection failed for %s", name)
                results[name] = {"error": str(error)}
        return results

    @staticmethod
    def _xml_text(element: ET.Element, name: str) -> str | None:
        child = element.find(name)
        return child.text.strip() if child is not None and child.text else None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public trade intelligence into SQLite.")
    parser.add_argument("--source", choices=("all", "wto", "world-bank", "comtrade-preview"), default="all")
    parser.add_argument("--database", default="data/trade_intelligence.db")
    parser.add_argument("--countries", default="all", help="Comma-separated ISO-3 country codes, or 'all', for World Bank data.")
    parser.add_argument("--years", type=int, default=3, help="Number of completed/recent years to request.")
    parser.add_argument("--reporter-code", default="36", help="UN M49 reporter code for Comtrade preview (36 = Australia).")
    parser.add_argument("--period", default=str(datetime.now(timezone.utc).year - 1), help="UN Comtrade annual period.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    database = TradeDatabase(args.database)
    try:
        result = TradeCollector(database).run(args.source, args.countries.split(","), args.years, args.reporter_code, args.period)
        print(json.dumps(result, indent=2))
    finally:
        database.close()


if __name__ == "__main__":
    main()
