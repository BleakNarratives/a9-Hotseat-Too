import json
import os
import tempfile
import threading
import unittest
import urllib.request
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hotseat_core.bridge import Bridge, serve
from hotseat_core.config import load_config
from hotseat_core.providers import (
    FallbackClient,
    ProviderClient,
    ProviderError,
    available_providers,
    build_client,
    configured_providers,
)
from hotseat_core.runtime import HotseatRuntime
from hotseat_core.storage import SessionStore


class FailingClient:
    def __init__(self, provider="primary", *, status=429, retryable=True):
        self.provider = provider
        self.status = status
        self.retryable = retryable
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        raise ProviderError(
            f"{self.provider} failed",
            status_code=self.status,
            retryable=self.retryable,
        )


class WorkingClient:
    def __init__(self, provider="backup"):
        self.provider = provider
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return "backup answer"


class ProviderFallbackTests(unittest.TestCase):
    def test_429_falls_back_with_the_backup_default_model(self):
        primary = FailingClient()
        backup = WorkingClient()
        client = FallbackClient([primary, backup])
        result = client.complete(messages=[{"role": "user", "content": "hello"}], model="primary-model")
        self.assertEqual(result, "backup answer")
        self.assertEqual(client.provider, "backup")
        self.assertTrue(client.fallback_used)
        self.assertIsNone(backup.calls[0]["model"])
        self.assertIn("primary failed", client.last_error)

    def test_timeout_is_retryable(self):
        primary = FailingClient(status=None, retryable=True)
        backup = WorkingClient()
        client = FallbackClient([primary, backup])
        self.assertEqual(client.complete(messages=[]), "backup answer")

    def test_billing_failure_falls_back(self):
        primary = FailingClient(status=402)
        backup = WorkingClient()
        client = FallbackClient([primary, backup])
        self.assertEqual(client.complete(messages=[]), "backup answer")
        self.assertTrue(client.fallback_used)
        self.assertTrue(ProviderError("billing", status_code=402).retryable)

    def test_non_retryable_failure_does_not_fall_back(self):
        primary = FailingClient(status=401, retryable=False)
        backup = WorkingClient()
        client = FallbackClient([primary, backup])
        with self.assertRaises(ProviderError):
            client.complete(messages=[])
        self.assertEqual(backup.calls, [])
        self.assertFalse(client.fallback_used)

    def test_build_client_chains_configured_cloud_keys(self):
        keys = {
            "OPENROUTER_API_KEY": "or-key",
            "MISTRAL_API_KEY": "mistral-key",
        }

        def loader(key, default=""):
            return keys.get(key, default)

        client = build_client("openrouter", "strong-model", secret_loader=loader)
        self.assertIsInstance(client, FallbackClient)
        self.assertEqual(client.provider, "openrouter")
        names = [item.provider for item in client.clients]
        self.assertEqual(names[0], "openrouter")
        self.assertIn("mistral", names)
        self.assertIn("gemini", names)

    def test_openai_requests_cap_tokens_and_identify_the_app(self):
        client = ProviderClient("openrouter", api_key="test-key")
        request = client._build_request(
            [{"role": "user", "content": "hello"}],
            "openai/gpt-4o-mini",
            None,
            {},
            stream=False,
        )
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["max_tokens"], 1024)
        self.assertIn("Hotseat", request.get_header("User-agent", ""))

    def test_status_never_exposes_secret_values(self):
        secrets = {
            "OPENROUTER_API_KEY": "sk-or-secret-value",
            "MISTRAL_API_KEY": "mistral-secret-value",
        }

        def loader(key, default=""):
            return secrets.get(key, default)

        with patch.dict(os.environ, {}, clear=True):
            rows = configured_providers(loader)
        by_name = {row["name"]: row for row in rows}
        self.assertTrue(by_name["openrouter"]["configured"])
        self.assertTrue(by_name["mistral"]["configured"])
        self.assertFalse(by_name["anthropic"]["configured"])
        self.assertTrue(by_name["demo"]["configured"])
        serialized = json.dumps(rows)
        self.assertNotIn("sk-or-secret-value", serialized)
        self.assertNotIn("mistral-secret-value", serialized)


class RoleModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = load_config(
            root=self.root,
            env={"HOTSEAT_DATA_DIR": str(self.root), "HOTSEAT_PROVIDER": "demo"},
        )
        self.store = SessionStore(self.config.db_path, self.config.session_log)

    def tearDown(self):
        self.tmp.cleanup()

    def test_per_role_models_reach_each_turn(self):
        models = []

        class Capture:
            provider = "capture"

            def complete(self, *, messages, model=None, system=None, sampling=None, on_chunk=None):
                models.append(model)
                return "ok"

        runtime = HotseatRuntime(
            self.config,
            store=self.store,
            client_factory=lambda provider, model: Capture(),
        )
        result = runtime.run_session(
            "arena",
            "a roofing quote tool",
            role_models={"producer": "fast-model", "coroner": "deep-model"},
            save=False,
        )
        self.assertEqual(len(result.turns), 5)
        self.assertEqual(models[0], "fast-model")
        self.assertEqual(models[-1], "deep-model")
        self.assertNotEqual(models[1], "fast-model")

    def test_manifest_role_models_are_applied(self):
        models = []

        class Capture:
            provider = "capture"

            def complete(self, *, messages, model=None, system=None, sampling=None, on_chunk=None):
                models.append(model)
                return "ok"

        config = replace(self.config, role_models={"arena": {"producer": "configured-fast"}})
        runtime = HotseatRuntime(
            config,
            store=self.store,
            client_factory=lambda provider, model: Capture(),
        )
        runtime.run_session("arena", "seed", save=False)
        self.assertEqual(models[0], "configured-fast")

    def test_unknown_role_is_rejected(self):
        runtime = HotseatRuntime(self.config, store=self.store)
        with self.assertRaises(ValueError):
            runtime.run_session(
                "arena",
                "a roofing quote tool",
                role_models={"nobody": "model"},
                save=False,
            )


class ProviderStatusBridgeTests(unittest.TestCase):
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
        self.secrets = {"OPENROUTER_API_KEY": "sk-or-secret-value"}

        def loader(key, default=""):
            return self.secrets.get(key, default)

        self.bridge = Bridge(
            self.config,
            runtime=self.runtime,
            store=self.store,
            secret_loader=loader,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_http_provider_status_reports_credentials_without_values(self):
        self.assertEqual(len(available_providers()), len(self.bridge.provider_status()["providers"]))
        server = serve(self.bridge, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            with patch.dict(os.environ, {}, clear=True):
                with urllib.request.urlopen(base + "/providers/status", timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    payload = json.loads(response.read())
            self.assertIn("openrouter", payload["configured"])
            self.assertIn("demo", payload["configured"])
            rows = {row["name"]: row for row in payload["providers"]}
            self.assertTrue(rows["openrouter"]["configured"])
            self.assertFalse(rows["anthropic"]["configured"])
            self.assertNotIn("sk-or-secret-value", json.dumps(payload))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
