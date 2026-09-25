import tempfile
import unittest
import urllib.parse
from pathlib import Path

from scraper.scraper import HttpClient, TradeCollector, TradeDatabase, TradeRecord
from ai.analyzer import TradeAnalytics
from ai.agent import AgentConfig, TradeIntelligenceAgent


class FakeClient(HttpClient):
    def __init__(self):
        self.last_url = ""

    def get_bytes(self, url):
        return b"""<?xml version='1.0'?><rss><channel><item><title>Trade update</title><link>https://example.test/item</link><pubDate>Tue, 01 Jan 2025 00:00:00 GMT</pubDate><description>Summary</description></item></channel></rss>"""

    def get_json(self, url):
        self.last_url = url
        if "comtradeapi.un.org" in url:
            return {"data": [{
                "period": "2024", "reporterCode": 36, "reporterDesc": "Australia",
                "partnerCode": 156, "partnerDesc": "China", "flowCode": "X",
                "flowDesc": "Export", "cmdCode": "2701", "cmdDesc": "Coal",
                "primaryValue": 1250000, "netWgt": 5000, "qty": 5000, "qtyUnit": "kg",
            }]}
        return [{}, [{"date": "2024", "value": 12.5, "country": {"id": "AUS", "value": "Australia"}}]]


class ScraperTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = TradeDatabase(Path(self.tempdir.name) / "test.db")

    def tearDown(self):
        self.database.close()
        self.tempdir.cleanup()

    def test_records_are_deduplicated(self):
        record = TradeRecord(source="test", record_type="news", title="Title", url="https://example.test")
        self.assertEqual((1, 1), self.database.insert_records([record]))
        self.assertEqual((1, 0), self.database.insert_records([record]))

    def test_wto_feed_is_normalised(self):
        records = TradeCollector(self.database, FakeClient()).collect_wto_news()
        self.assertEqual(1, len(records))
        self.assertEqual("wto_rss", records[0].source)
        self.assertEqual("Trade update", records[0].title)

    def test_world_bank_records_include_both_trade_indicators(self):
        records = TradeCollector(self.database, FakeClient()).collect_world_bank_trade(["AUS"], years=1)
        self.assertEqual(2, len(records))
        self.assertEqual({"TX.VAL.MRCH.CD.WT", "TM.VAL.MRCH.CD.WT"}, {record.indicator for record in records})

    def test_comtrade_preview_accepts_partner_commodity_and_flow(self):
        client = FakeClient()
        records = TradeCollector(self.database, client).collect_comtrade_preview("36", "2024", "156", "2701", "X")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(client.last_url).query)
        self.assertEqual({"36"}, set(query["reporterCode"]))
        self.assertEqual({"156"}, set(query["partnerCode"]))
        self.assertEqual({"2701"}, set(query["cmdCode"]))
        self.assertEqual("trade_value_X", records[0].indicator)
        self.assertEqual("China", records[0].metadata["partnerDesc"])

    def test_analytics_calculates_trade_balance(self):
        self.database.insert_records([
            TradeRecord(source="world_bank_api", record_type="indicator", title="Exports", country="AUS", indicator="TX.VAL.MRCH.CD.WT", published_at="2024-12-31", value=120.0, metadata={"country_name": "Australia"}),
            TradeRecord(source="world_bank_api", record_type="indicator", title="Imports", country="AUS", indicator="TM.VAL.MRCH.CD.WT", published_at="2024-12-31", value=100.0, metadata={"country_name": "Australia"}),
        ])
        series = TradeAnalytics(self.database.path).trade_series("AUS")
        self.assertEqual([{"year": 2024, "exports": 120.0, "imports": 100.0, "trade_balance": 20.0}], series)
        self.assertEqual([{
            "country": "AUS", "country_name": "Australia", "year": 2024,
            "exports": 120.0, "imports": 100.0, "trade_balance": 20.0,
            "trade_volume": 220.0,
        }], TradeAnalytics(self.database.path).world_trade_snapshot())

    def test_agent_detects_material_trade_change(self):
        self.database.insert_records([
            TradeRecord(source="world_bank_api", record_type="indicator", title="Exports", country="AUS", indicator="TX.VAL.MRCH.CD.WT", published_at="2024-12-31", value=120.0, metadata={"country_name": "Australia"}),
            TradeRecord(source="world_bank_api", record_type="indicator", title="Exports", country="AUS", indicator="TX.VAL.MRCH.CD.WT", published_at="2023-12-31", value=100.0, metadata={"country_name": "Australia"}),
        ])
        agent = TradeIntelligenceAgent(AgentConfig(change_alert_percent=15), TradeCollector(self.database, FakeClient()))
        alerts = agent._trade_change_alerts()
        self.assertEqual(1, len(alerts))
        self.assertIn("increased 20.0%", alerts[0]["message"])


if __name__ == "__main__":
    unittest.main()
