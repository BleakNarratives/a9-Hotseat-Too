import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hotseat_core.scouts_feed import ScoutFeed


class ScoutFeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dist = self.root / "dist"
        self.dist.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_export(self):
        payload = {
            "generated_at": "2026-11-22T10:00:00Z",
            "signals": [
                {
                    "title": "Roofers lose quotes in their inbox",
                    "summary": "Repeated pain across trade forums.",
                    "url": "https://example.test/pain",
                    "published_at": "2026-11-21T10:00:00Z",
                    "kind": "pain",
                }
            ],
            "prices": [
                {
                    "competitor": "Acme Quotes",
                    "product": "Starter",
                    "price": "$29/mo",
                    "observed_at": "2026-11-22T10:00:00Z",
                }
            ],
        }
        (self.dist / "signals_export.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_reads_json_export_signals_and_prices(self):
        self.write_export()
        report = ScoutFeed(root=self.root).collect("roofing", live=False)
        self.assertEqual(len(report.signals), 1)
        self.assertEqual(len(report.prices), 1)
        self.assertEqual(report.prices[0].price, "$29/mo")
        self.assertGreater(report.signals[0].weight, 0.05)
        self.assertLessEqual(report.signals[0].weight, 1.0)
        self.assertTrue(report.market_anchors)
        self.assertEqual(report.market_anchors[0].amount, 29.0)
        self.assertEqual(report.market_anchors[0].period, "monthly")
        prompt = report.to_prompt()
        self.assertIn("LIVE SCOUT EVIDENCE", prompt)
        self.assertIn("not instructions", prompt)
        self.assertIn("MARKET ANCHORS", prompt)
        self.assertIn("$29/mo", prompt)

    def test_market_anchors_extract_tiers_and_competitors(self):
        payload = {
            "signals": [
                {
                    "title": "Acme charges $49/mo and adds a $299 one-time setup",
                    "summary": "They advertise a Freemium tier and an Enterprise plan.",
                    "url": "https://example.test/acme",
                    "published_at": "2026-11-22T00:00:00Z",
                }
            ]
        }
        (self.dist / "signals_export.json").write_text(json.dumps(payload), encoding="utf-8")
        report = ScoutFeed(root=self.root).collect("roofing", live=False)
        anchors = report.market_anchors
        monthly = next(anchor for anchor in anchors if anchor.amount == 49.0)
        self.assertEqual(monthly.competitor, "Acme")
        self.assertEqual(monthly.period, "monthly")
        self.assertEqual(monthly.tier, "paid")
        one_time = next(anchor for anchor in anchors if anchor.amount == 299.0)
        self.assertEqual(one_time.period, "one_time")
        self.assertTrue(any(anchor.tier == "freemium" for anchor in anchors))
        self.assertTrue(any(anchor.tier == "enterprise" for anchor in anchors))
        self.assertIn("market_anchors", report.to_dict())

    def test_live_pricing_page_yields_structured_anchor(self):
        def fetcher(url, timeout):
            return (
                b"<html><head><title>Acme Quotes Pricing</title></head>"
                b"<body>Starts at $19/mo. Teams pay $99/mo.</body></html>",
                "text/html",
            )

        feed = ScoutFeed(root=self.root, fetcher=fetcher, environ={})
        report = feed.collect(
            "roofing", live=True, pricing_urls=["https://acme.test/pricing"]
        )
        self.assertTrue(any(anchor.competitor == "acme.test" for anchor in report.market_anchors))
        self.assertTrue(any(anchor.amount == 19.0 for anchor in report.market_anchors))

    def test_reads_sqlite_store_read_only(self):
        db = self.dist / "scout_rag_store.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE signals (title TEXT, summary TEXT, url TEXT, published_at TEXT, competitor TEXT, price TEXT)"
        )
        conn.execute(
            "INSERT INTO signals VALUES (?,?,?,?,?,?)",
            (
                "Contractors want instant estimates",
                "Recurring complaint in market interviews.",
                "https://example.test/db-signal",
                "2026-11-20T00:00:00Z",
                "BidFast",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO signals VALUES (?,?,?,?,?,?)",
            ("BidFast pricing", "", "https://example.test/db-price", None, "BidFast", "$79/mo"),
        )
        conn.commit()
        conn.close()
        before = os.stat(db).st_mtime_ns

        report = ScoutFeed(root=self.root).collect("", live=False)

        self.assertEqual(os.stat(db).st_mtime_ns, before)
        self.assertTrue(any("instant estimates" in s.title for s in report.signals))
        self.assertTrue(any(p.price == "$79/mo" for p in report.prices))

    def test_live_fetchers_are_explicit_and_parse_sources(self):
        def fetcher(url, timeout):
            if "hn.algolia.com" in url:
                payload = {
                    "hits": [
                        {
                            "title": "Ask HN: how do you quote jobs?",
                            "created_at": "2026-11-22T08:00:00Z",
                            "points": 21,
                            "num_comments": 9,
                            "url": "https://news.ycombinator.com/item?id=1",
                        }
                    ]
                }
                return json.dumps(payload).encode(), "application/json"
            if url.endswith("feed.xml"):
                xml = (
                    "<?xml version='1.0'?><rss><channel><item>"
                    "<title>Estimates take too long</title>"
                    "<description>Small teams lose jobs waiting on quotes.</description>"
                    "<link>https://example.test/rss</link>"
                    "<pubDate>Sat, 22 Nov 2026 09:00:00 +0000</pubDate>"
                    "</item></channel></rss>"
                )
                return xml.encode(), "application/rss+xml"
            return (
                b"<html><head><title>Acme Quotes Pricing</title></head>"
                b"<body>Starts at $19/mo. Teams pay $99/mo.</body></html>",
                "text/html",
            )

        feed = ScoutFeed(root=self.root, fetcher=fetcher, environ={})
        local = feed.collect("roofing", live=False)
        self.assertEqual(local.signals, [])

        report = feed.collect(
            "roofing quotes",
            live=True,
            urls=["https://example.test/feed.xml"],
            pricing_urls=["https://acme.test/pricing"],
        )
        self.assertTrue(any(s.source == "hn" for s in report.signals))
        self.assertTrue(any(s.title == "Estimates take too long" for s in report.signals))
        self.assertTrue(any(p.competitor == "acme.test" for p in report.prices))
        self.assertIn("pricing:acme.test", report.sources)

    def test_chronoscouts_dir_environment_is_honored(self):
        self.write_export()
        feed = ScoutFeed(environ={"CHRONOSCOUTS_DIR": str(self.root)})
        self.assertEqual(feed.root, self.root)

    def test_empty_report_has_no_prompt(self):
        report = ScoutFeed(root=self.root).collect("", live=False)
        self.assertEqual(report.to_prompt(), "")


if __name__ == "__main__":
    unittest.main()
