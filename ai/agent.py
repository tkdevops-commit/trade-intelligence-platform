"""A local, source-aware autonomous trade-intelligence agent.

The agent coordinates the project's approved public collectors, reviews the
resulting SQLite data, and writes a human-reviewable briefing.  It never
submits forms, sends messages, bypasses access controls, or expands its source
list without a code/configuration change.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai.analyzer import EXPORT_INDICATOR, IMPORT_INDICATOR, TradeAnalytics
from scraper.scraper import TradeCollector, TradeDatabase


DEFAULT_COUNTRIES = "AUS,USA,CHN,JPN,DEU,IND,IDN,KOR,GBR,CAN,MEX,BRA"
RISK_TERMS = (
    "tariff", "sanction", "export control", "restriction", "trade dispute",
    "subsid", "anti-dumping", "countervailing", "retaliat",
)


@dataclass(frozen=True)
class AgentConfig:
    database: str = "data/trade_intelligence.db"
    reports_directory: str = "reports"
    countries: str = DEFAULT_COUNTRIES
    years: int = 5
    change_alert_percent: float = 15.0
    collect_comtrade_preview: bool = False


class TradeIntelligenceAgent:
    """Run collection, analysis, and official-web monitoring as one workflow."""

    def __init__(self, config: AgentConfig, collector: TradeCollector | None = None) -> None:
        self.config = config
        self.database = collector.database if collector else TradeDatabase(config.database)
        self.collector = collector or TradeCollector(self.database)
        self._owns_database = collector is None

    def run_once(self) -> dict[str, Any]:
        started_at = self._now()
        run_id = self.database.connection.execute(
            "INSERT INTO agent_runs (started_at, status) VALUES (?, ?)", (started_at, "running")
        ).lastrowid
        self.database.connection.commit()
        try:
            collection = self._collect()
            briefing = self._briefing(collection, started_at)
            report_path = self._write_report(briefing)
            self.database.connection.execute(
                "UPDATE agent_runs SET finished_at = ?, status = ?, summary_json = ?, report_path = ? WHERE id = ?",
                (self._now(), "completed", json.dumps(briefing, sort_keys=True), str(report_path), run_id),
            )
            self.database.connection.commit()
            return {**briefing, "report_path": str(report_path)}
        except Exception as error:
            self.database.connection.execute(
                "UPDATE agent_runs SET finished_at = ?, status = ?, error = ? WHERE id = ?",
                (self._now(), "failed", str(error), run_id),
            )
            self.database.connection.commit()
            raise
        finally:
            if self._owns_database:
                self.database.close()

    def _collect(self) -> dict[str, dict[str, int | str]]:
        countries = self.config.countries.split(",")
        result = self.collector.run(
            "wto", countries, self.config.years,
            reporter_code="36", period=str(datetime.now(timezone.utc).year - 1),
        )
        result.update(self.collector.run(
            "world-bank", countries, self.config.years,
            reporter_code="36", period=str(datetime.now(timezone.utc).year - 1),
        ))
        if self.config.collect_comtrade_preview:
            result.update(self.collector.run(
                "comtrade-preview", countries, self.config.years,
                reporter_code="36", period=str(datetime.now(timezone.utc).year - 1),
            ))
        return result

    def _briefing(self, collection: dict[str, dict[str, int | str]], started_at: str) -> dict[str, Any]:
        analytics = TradeAnalytics(self.database.path)
        news = analytics.news(limit=20)
        alerts = self._policy_alerts(news) + self._trade_change_alerts()
        return {
            "generated_at": self._now(),
            "started_at": started_at,
            "collection": collection,
            "overview": analytics.overview(),
            "alerts": alerts,
            "latest_official_news": news[:8],
            "guardrails": "Official RSS/APIs only; collection is rate-limited and no access controls are bypassed.",
        }

    def _policy_alerts(self, articles: list[dict[str, Any]]) -> list[dict[str, str]]:
        alerts: list[dict[str, str]] = []
        for article in articles:
            text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
            matches = [term for term in RISK_TERMS if term in text]
            if matches:
                alerts.append({
                    "kind": "policy_watch",
                    "severity": "review",
                    "message": f"WTO update matches: {', '.join(matches)} — {article['title']}",
                    "url": article.get("url") or "",
                })
        return alerts

    def _trade_change_alerts(self) -> list[dict[str, str]]:
        countries = [country.strip().upper() for country in self.config.countries.split(",") if country.strip()]
        placeholders = ", ".join("?" for _ in countries)
        rows = self.database.connection.execute(
            f"""
            SELECT country, indicator, published_at, value, metadata_json
            FROM trade_records
            WHERE source = 'world_bank_api' AND indicator IN (?, ?) AND country IN ({placeholders}) AND value IS NOT NULL
            ORDER BY country, indicator, published_at DESC
            """, (EXPORT_INDICATOR, IMPORT_INDICATOR, *countries),
        ).fetchall()
        latest: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in rows:
            key = (row["country"], row["indicator"])
            latest.setdefault(key, []).append(row)
        alerts: list[dict[str, str]] = []
        for (country, indicator), observations in latest.items():
            if len(observations) < 2:
                continue
            current, previous = observations[0], observations[1]
            if not previous["value"]:
                continue
            change = ((current["value"] - previous["value"]) / abs(previous["value"])) * 100
            if abs(change) >= self.config.change_alert_percent:
                metadata = json.loads(current["metadata_json"] or "{}")
                direction = "increased" if change > 0 else "decreased"
                label = "exports" if indicator == EXPORT_INDICATOR else "imports"
                alerts.append({
                    "kind": "trade_change",
                    "severity": "review",
                    "message": f"{metadata.get('country_name', country)} {label} {direction} {abs(change):.1f}% between {previous['published_at'][:4]} and {current['published_at'][:4]}.",
                    "url": "",
                })
        return alerts

    def _write_report(self, briefing: dict[str, Any]) -> Path:
        directory = Path(self.config.reports_directory)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"trade-briefing-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        path = directory / filename
        path.write_text(json.dumps(briefing, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


def load_config(path: str | None) -> AgentConfig:
    if not path:
        return AgentConfig()
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        raise ValueError("Agent configuration must be a JSON object.")
    allowed = {field.name for field in AgentConfig.__dataclass_fields__.values()}
    return AgentConfig(**{key: value for key, value in values.items() if key in allowed})


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomously collect and brief official trade intelligence.")
    parser.add_argument("--config", help="Path to an optional JSON configuration file.")
    parser.add_argument("--watch", action="store_true", help="Keep running at the chosen interval.")
    parser.add_argument("--interval-hours", type=float, default=24, help="Hours between watch runs (minimum 1).")
    parser.add_argument("--print-config", action="store_true", help="Print the effective configuration and exit.")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.print_config:
        print(json.dumps(asdict(config), indent=2))
        return
    if args.watch and args.interval_hours < 1:
        parser.error("--interval-hours must be at least 1.")
    while True:
        result = TradeIntelligenceAgent(config).run_once()
        print(json.dumps(result, indent=2))
        if not args.watch:
            break
        time.sleep(args.interval_hours * 3600)


if __name__ == "__main__":
    main()
