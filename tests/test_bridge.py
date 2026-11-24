import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from hotseat_core.bridge import Bridge, serve
from hotseat_core.config import load_config
from hotseat_core.providers import ProviderClient
from hotseat_core.runtime import HotseatRuntime
from hotseat_core.storage import SessionStore


def wait_done(job, timeout=10.0):
    if not job.done.wait(timeout):
        raise AssertionError("session did not finish in time")


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
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
        self.bridge = Bridge(self.config, runtime=self.runtime, store=self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_session_lifecycle_and_events(self):
        job = self.bridge.start_session("classic", "a bridge idea")
        wait_done(job)
        self.assertIsNone(job.error)
        self.assertIsNotNone(job.result)
        self.assertEqual(len(job.result["turns"]), 3)
        types = [event["type"] for event in job.public()["events"]]
        self.assertEqual(types[0], "session_start")
        self.assertTrue(any(event["type"] == "token_chunk" for event in job.public()["events"]))
        self.assertIn("memory_saved", types)
        self.assertEqual(types[-1], "session_end")

    def test_injection_is_applied_to_a_later_turn(self):
        prompts = []
        first_started = threading.Event()
        release = threading.Event()

        class Gated:
            provider = "gated"

            def complete(self, *, messages, model=None, system=None, sampling=None, on_chunk=None):
                prompts.append(messages[-1]["content"])
                if len(prompts) == 1:
                    first_started.set()
                    release.wait(5)
                if on_chunk:
                    on_chunk("ok")
                return "ok"

        runtime = HotseatRuntime(
            self.config,
            store=self.store,
            client_factory=lambda provider, model: Gated(),
        )
        bridge = Bridge(self.config, runtime=runtime, store=self.store)
        job = bridge.start_session("classic", "queued note")
        self.assertTrue(first_started.wait(5))
        bridge.inject(job.id, "price it at ten dollars")
        release.set()
        wait_done(job)
        self.assertTrue(any("price it at ten dollars" in prompt for prompt in prompts[1:]))

    def test_inject_and_stop_reject_unknown_or_finished_sessions(self):
        with self.assertRaises(KeyError):
            self.bridge.inject("nope", "hi")
        job = self.bridge.start_session("classic", "finished")
        wait_done(job)
        with self.assertRaises(ValueError):
            self.bridge.inject(job.id, "too late")
        self.bridge.stop(job.id)  # idempotent, no raise

    def test_persona_editing(self):
        updated = self.bridge.update_persona("classic", "audrey", {"model": "custom-model"})
        self.assertEqual(updated["model"], "custom-model")
        self.assertIn("system", updated)
        listed = self.bridge.personas("classic")
        audrey = next(p for p in listed["personas"] if p["key"] == "audrey")
        self.assertEqual(audrey["model"], "custom-model")
        with self.assertRaises(KeyError):
            self.bridge.update_persona("classic", "nobody", {"model": "x"})
        with self.assertRaises(ValueError):
            self.bridge.update_persona("classic", "audrey", {"max_tokens": 0})

    def test_http_endpoints_and_token(self):
        bridge = Bridge(
            self.config,
            runtime=self.runtime,
            store=self.store,
            token="secret",
            allowed_origins=("http://localhost:3000",),
        )
        server = serve(bridge, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            request = urllib.request.Request(base + "/health")
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=5)
            self.assertEqual(caught.exception.code, 401)
            caught.exception.close()

            request = urllib.request.Request(
                base + "/health", headers={"Authorization": "Bearer secret"}
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(json.loads(response.read())["status"], "ok")

            request = urllib.request.Request(
                base + "/modes", headers={"Authorization": "Bearer secret"}
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                modes = json.loads(response.read())["modes"]
            self.assertEqual(
                {m["mode"] for m in modes}, {"classic", "v2", "v3", "bmad", "arena"}
            )

            payload = json.dumps({"mode": "v2", "topic": "http idea"}).encode()
            request = urllib.request.Request(
                base + "/sessions",
                data=payload,
                headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 202)
                created = json.loads(response.read())
            session_id = created["session_id"]

            deadline = time.time() + 10
            document = None
            while time.time() < deadline:
                request = urllib.request.Request(
                    base + f"/sessions/{session_id}",
                    headers={"Authorization": "Bearer secret"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    document = json.loads(response.read())
                if document["done"]:
                    break
                time.sleep(0.05)
            self.assertTrue(document and document["done"])
            self.assertIsNone(document["error"])
            self.assertEqual(len(document["result"]["turns"]), 4)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_mobile_companion_assets_over_http(self):
        server = serve(self.bridge, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            checks = [
                ("/m", "text/html", "THE HOT SEAT", "COMPANION"),
                ("/m/", "text/html", "mobile.css", "mobile.js"),
                ("/mobile.css", "text/css", "safe-area-inset-bottom", "prefers-reduced-motion"),
                ("/mobile.js", "text/javascript", "EventSource", "CONVENE THE ROOM"),
            ]
            for path, content_type, first, second in checks:
                with urllib.request.urlopen(base + path, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(content_type, response.headers.get("Content-Type", ""))
                    body = response.read().decode("utf-8")
                    self.assertIn(first, body)
                    self.assertIn(second, body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_non_loopback_bind_requires_token(self):
        bridge = Bridge(self.config, runtime=self.runtime, store=self.store)
        with self.assertRaises(ValueError):
            serve(bridge, host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
