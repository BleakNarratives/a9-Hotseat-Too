import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from hotseat_core.bridge import Bridge, serve
from hotseat_core.config import load_config
from hotseat_core.engines.arena import ArenaEngine
from hotseat_core.personas import get_persona_set
from hotseat_core.providers import ProviderClient
from hotseat_core.runtime import HotseatRuntime
from hotseat_core.scouts_feed import ScoutFeed
from hotseat_core.storage import SessionStore


class CaptureClient:
    provider = "capture"

    def __init__(self):
        self.prompts = []

    def complete(self, *, messages, model=None, system=None, sampling=None, on_chunk=None):
        self.prompts.append(messages[-1]["content"])
        if on_chunk:
            on_chunk("ok")
        return "ok"


def request_json(base, path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method or ("POST" if data is not None else "GET"),
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read())


class ArenaEvidenceTests(unittest.TestCase):
    def test_scout_evidence_reaches_every_arena_prompt(self):
        client = CaptureClient()
        engine = ArenaEngine(
            get_persona_set("arena"),
            client,
            options={
                "constraints": "budget $0",
                "scout_context": "SCOUT-EVIDENCE-MARKER: Acme charges $99/mo.",
            },
        )
        turns = engine.run("a roofing quote tool")
        self.assertEqual(len(turns), 5)
        self.assertEqual(len(client.prompts), 5)
        for prompt in client.prompts:
            self.assertIn("SCOUT-EVIDENCE-MARKER", prompt)
            self.assertIn("Live scout evidence", prompt)


class LiveBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.scouts = self.root / "chronoscouts"
        (self.scouts / "dist").mkdir(parents=True)
        (self.scouts / "dist" / "signals_export.json").write_text(
            json.dumps(
                {
                    "signals": [
                        {
                            "title": "Roofers lose quotes in their inbox",
                            "summary": "Repeated pain across trade forums.",
                            "url": "https://example.test/pain",
                            "published_at": "2026-11-21T10:00:00Z",
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
            ),
            encoding="utf-8",
        )
        self.config = load_config(
            root=self.root,
            env={"HOTSEAT_DATA_DIR": str(self.root), "HOTSEAT_PROVIDER": "demo"},
        )
        self.store = SessionStore(self.config.db_path, self.config.session_log)
        self.runtime = HotseatRuntime(
            self.config,
            store=self.store,
            client_factory=lambda provider, model: ProviderClient("demo"),
        )
        self.feed = ScoutFeed(root=self.scouts)
        self.bridge = Bridge(
            self.config, runtime=self.runtime, store=self.store, scout_feed=self.feed
        )

    def tearDown(self):
        self.tmp.cleanup()

    def wait_done(self, job, timeout=10.0):
        if not job.done.wait(timeout):
            raise AssertionError("session did not finish in time")

    def test_refresh_scouts_is_exposed_on_the_bridge(self):
        report = self.bridge.refresh_scouts("roofing", live=False)
        self.assertEqual(report["counts"], {"signals": 1, "prices": 1})
        self.assertEqual(self.bridge.latest_scouts()["prices"][0]["price"], "$29/mo")

    def test_scouts_latest_and_static_assets_over_http(self):
        self.bridge.refresh_scouts("roofing", live=False)
        server = serve(self.bridge, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            status, latest = request_json(base, "/scouts/latest")
            self.assertEqual(status, 200)
            self.assertEqual(latest["report"]["counts"]["signals"], 1)
            self.assertEqual(latest["report"]["prices"][0]["price"], "$29/mo")

            status, refreshed = request_json(
                base, "/scouts/refresh", {"seed": "roofing", "live": False}
            )
            self.assertEqual(status, 200)
            self.assertEqual(refreshed["report"]["counts"]["prices"], 1)

            with urllib.request.urlopen(base + "/", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("text/html", response.headers.get("Content-Type", ""))
                self.assertIn("SCOUT WIRE", response.read().decode("utf-8"))

            with urllib.request.urlopen(base + "/app.js", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("EventSource", response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_session_attaches_scouts_and_threaded_followup(self):
        job = self.bridge.start_session(
            "arena",
            "a roofing quote tool",
            scout_context={"live": False},
        )
        self.wait_done(job)
        self.assertIsNone(job.error)
        self.assertEqual(len(job.result["turns"]), 5)
        self.assertEqual(job.scouts["counts"], {"signals": 1, "prices": 1})
        self.assertIn("scouts", job.public())

        events = job.public()["events"]
        self.assertEqual(events[0]["type"], "session_start")
        self.assertEqual(job.public(since=2)["events"][0], events[2])

        memory_id = job.result["memory_id"]
        self.bridge.continue_session(job.id, "Tighten the brief and defend the price.")
        self.wait_done(job)
        self.assertIsNone(job.error)
        self.assertEqual(len(job.result["turns"]), 6)
        self.assertTrue(job.public()["events"][-1]["follow_up"])
        stored = self.store.get(memory_id)
        self.assertEqual(len(stored["turns"]), 6)
        self.assertEqual(stored["turns"][-1]["persona"], "coroner")

    def test_followup_over_http_and_since_stream(self):
        server = serve(self.bridge, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            status, created = request_json(
                base,
                "/sessions",
                {
                    "mode": "arena",
                    "topic": "a roofing quote tool",
                    "scout_context": {"live": False},
                },
            )
            self.assertEqual(status, 202)
            session_id = created["session_id"]

            document = {}
            deadline = time.time() + 10
            while time.time() < deadline:
                _, document = request_json(base, "/sessions/" + session_id)
                if document.get("done"):
                    break
                time.sleep(0.05)
            self.assertTrue(document.get("done"))
            self.assertEqual(len(document["result"]["turns"]), 5)
            self.assertEqual(document["scouts"]["counts"]["signals"], 1)

            status, accepted = request_json(
                base,
                "/sessions/%s/messages" % session_id,
                {"message": "What would make the niche wedge fail?"},
            )
            self.assertEqual(status, 202)
            self.assertTrue(accepted["accepted"])

            deadline = time.time() + 10
            while time.time() < deadline:
                _, document = request_json(base, "/sessions/" + session_id)
                if document.get("done") and len(document["result"]["turns"]) == 6:
                    break
                time.sleep(0.05)
            self.assertEqual(len(document["result"]["turns"]), 6)
            self.assertEqual(document["events"][-1]["type"], "session_end")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
