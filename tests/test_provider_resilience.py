import json
import os
import tempfile
import threading
import unittest
import urllib.request
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from hotseat_core.bridge import Bridge, serve
from hotseat_core.config import load_config
from hotseat_core.providers import (
    PROVIDERS,
    FallbackClient,
    ProviderClient,
    ProviderError,
    _credential_pool,
    _http_failure,
    available_providers,
    build_client,
    configured_providers,
)
from hotseat_core.runtime import HotseatRuntime
from hotseat_core.storage import SessionStore
from hotseat_core.tuning import clean_response


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


class OutputCleanupTests(unittest.TestCase):
    def test_separator_chrome_and_trailing_ellipsis_are_removed(self):
        cleaned = clean_response("The point stands.\n=====\nPrice = $29\nWait...")
        self.assertIn("The point stands.", cleaned)
        self.assertIn("Price — $29", cleaned)
        self.assertNotIn("====", cleaned)
        self.assertNotIn("...", cleaned)
        self.assertTrue(cleaned.endswith("Wait"))

    def test_ordinary_periods_and_url_queries_survive(self):
        cleaned = clean_response("See https://example.test/?a=b. Keep the period.")
        self.assertIn("https://example.test/?a=b", cleaned)
        self.assertTrue(cleaned.endswith("Keep the period."))


class ProviderFailureClassificationTests(unittest.TestCase):
    @staticmethod
    def failure(code, detail, headers=None):
        error = HTTPError("https://example.test", code, "failure", headers or {}, None)
        return _http_failure("test", error, detail)

    def test_short_429_uses_cooldown_and_retry_after(self):
        error = self.failure(429, "rate limit per minute", {"Retry-After": "12"})
        self.assertEqual(error.kind, "cooldown")
        self.assertEqual(error.cooldown_seconds, 12)
        self.assertFalse(error.exhausted)
        self.assertTrue(error.retryable)

    def test_daily_429_is_marked_exhausted(self):
        error = self.failure(429, "daily token budget exhausted")
        self.assertEqual(error.kind, "daily_limit")
        self.assertTrue(error.exhausted)
        self.assertTrue(error.retryable)

    def test_400_403_429_are_retryable(self):
        for code in (400, 403, 429):
            self.assertTrue(self.failure(code, "no").retryable, code)
        self.assertEqual(self.failure(400, "model not found").kind, "model")
        self.assertEqual(self.failure(403, "invalid api key").kind, "auth")

    def test_server_error_has_a_short_cooldown(self):
        error = self.failure(503, "upstream unavailable", {"Retry-After": "3"})
        self.assertEqual(error.kind, "server")
        self.assertEqual(error.cooldown_seconds, 3)


class KeyRingTests(unittest.TestCase):
    def test_key_ring_reads_numbered_and_comma_separated_values(self):
        secrets = {
            "OPENROUTER_API_KEY": "one, two",
            "OPENROUTER_API_KEY_2": "three",
            "OPENROUTER_KEYS": "four",
        }

        def loader(key, default=""):
            return secrets.get(key, default)

        with patch.dict(os.environ, {}, clear=True):
            pool = _credential_pool(PROVIDERS["openrouter"], loader)
        self.assertEqual(pool, ["one", "two", "three", "four"])

    def test_new_byok_providers_are_listed(self):
        names = {row["name"] for row in available_providers()}
        for name in ("openai", "anthropic", "fireworks", "zen", "custom"):
            self.assertIn(name, names)

    def test_byok_endpoints_are_openai_compatible(self):
        self.assertEqual(ProviderClient("openai", api_key="x").base_url, "https://api.openai.com/v1")
        self.assertEqual(ProviderClient("zen", api_key="x").base_url, "https://opencode.ai/zen/v1")
        self.assertEqual(
            ProviderClient("fireworks", api_key="x").base_url,
            "https://api.fireworks.ai/inference/v1",
        )

    def test_custom_provider_requires_an_endpoint(self):
        with patch.dict(os.environ, {"CUSTOM_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(ProviderError):
                ProviderClient("custom")
        with patch.dict(
            os.environ,
            {"CUSTOM_API_KEY": "test-key", "CUSTOM_BASE_URL": "https://example.test/v1"},
            clear=True,
        ):
            self.assertEqual(ProviderClient("custom").base_url, "https://example.test/v1")

    def test_build_client_adds_the_next_key_for_the_same_provider(self):
        secrets = {
            "OPENROUTER_API_KEY": "first",
            "OPENROUTER_API_KEY_2": "second",
        }

        def loader(key, default=""):
            return secrets.get(key, default)

        with patch.dict(os.environ, {}, clear=True):
            client = build_client("openrouter", "model", secret_loader=loader)
        self.assertIsInstance(client, FallbackClient)
        self.assertEqual([c.provider for c in client.clients], ["openrouter", "openrouter"])
        self.assertEqual([c.key_label for c in client.clients], ["key 1", "key 2"])


class ProviderFallbackTests(unittest.TestCase):
    def test_successful_ring_rotates_to_the_next_client(self):
        first = WorkingClient(provider="first")
        second = WorkingClient(provider="second")
        client = FallbackClient([first, second])
        self.assertEqual(client.complete(messages=[]), "backup answer")
        self.assertEqual(client.provider, "first")
        self.assertEqual(client.complete(messages=[]), "backup answer")
        self.assertEqual(client.provider, "second")
        self.assertEqual(len(first.calls), 1)
        self.assertEqual(len(second.calls), 1)

    def test_default_models_are_the_live_ones(self):
        self.assertEqual(PROVIDERS["groq"].default_model, "openai/gpt-oss-120b")
        self.assertEqual(PROVIDERS["cerebras"].default_model, "gpt-oss-120b")

    def test_fallback_trail_names_the_failed_key_and_provider(self):
        primary = FailingClient(provider="openrouter", status=429)
        primary.key_label = "key 1"
        backup = WorkingClient(provider="groq")
        backup.key_label = "key 2"
        client = FallbackClient([primary, backup])
        self.assertEqual(client.complete(messages=[]), "backup answer")
        self.assertEqual(client.provider, "groq")
        self.assertEqual(client.key_label, "key 2")
        self.assertTrue(any("openrouter key 1" in item for item in client.fallback_trail))

    def test_cooling_key_is_skipped_without_being_called(self):
        class Cooling:
            provider = "openrouter"
            key_label = "key 1"

            def __init__(self):
                self.calls = 0

            def available(self):
                return False

            def complete(self, **kwargs):
                self.calls += 1
                return "wrong"

        primary = Cooling()
        backup = WorkingClient()
        client = FallbackClient([primary, backup])
        self.assertEqual(client.complete(messages=[]), "backup answer")
        self.assertEqual(primary.calls, 0)
        self.assertTrue(any("skipped" in item for item in client.fallback_trail))

    def test_a_failed_stream_is_not_released_before_the_winner(self):
        class Partial:
            provider = "openrouter"
            key_label = "key 1"

            def complete(self, *, on_chunk=None, **kwargs):
                if on_chunk:
                    on_chunk("partial")
                raise ProviderError("limit", status_code=429, retryable=True, kind="cooldown")

        class Whole:
            provider = "groq"
            key_label = "key 1"

            def complete(self, *, on_chunk=None, **kwargs):
                if on_chunk:
                    on_chunk("whole")
                return "whole"

        pieces = []
        client = FallbackClient([Partial(), Whole()])
        self.assertEqual(client.complete(messages=[], on_chunk=pieces.append), "whole")
        self.assertEqual(pieces, ["whole"])

    def test_model_failure_tries_the_next_model_before_the_next_provider(self):
        class ModelFail:
            provider = "openrouter"
            key_label = "key 1"

            def __init__(self):
                self.calls = []

            def default_model(self):
                return "primary-model"

            def fallback_models(self):
                return ("backup-model",)

            def complete(self, *, model=None, **kwargs):
                self.calls.append(model)
                if model == "primary-model":
                    raise ProviderError(
                        "model not found",
                        status_code=400,
                        retryable=True,
                        kind="model",
                    )
                return "model answer"

        primary = ModelFail()
        client = FallbackClient([primary])
        self.assertEqual(client.complete(messages=[]), "model answer")
        self.assertEqual(primary.calls, ["primary-model", "backup-model"])
        self.assertEqual(client.model, "backup-model")

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

    def test_seat_router_can_pick_the_session_provider_and_model(self):
        captured = []

        class Capture:
            provider = "capture"

            def complete(self, **_kwargs):
                return "ok"

        runtime = HotseatRuntime(
            self.config,
            store=self.store,
            client_factory=lambda provider, model: captured.append((provider, model))
            or Capture(),
        )
        with patch.dict(os.environ, {"HOTSEAT_SEAT_ROUTER": "1"}), patch(
            "hotseat_core.moe_router.pick_seat_route",
            return_value=("groq", "route-model"),
        ):
            runtime.build_engine("classic", provider="auto")
        self.assertEqual(captured[0], ("groq", "route-model"))

    def test_provider_failure_never_leaves_a_blank_or_status_code_card(self):
        class AlwaysFail:
            provider = "openrouter"
            key_label = "key 1"

            def complete(self, *, messages, model=None, system=None, sampling=None, on_chunk=None):
                raise ProviderError(
                    "Provider returned HTTP 429.",
                    status_code=429,
                    retryable=True,
                    kind="cooldown",
                )

        events = []
        runtime = HotseatRuntime(
            self.config,
            store=self.store,
            client_factory=lambda provider, model: AlwaysFail(),
        )
        with patch("hotseat_core.engines.base.time.sleep", return_value=None):
            result = runtime.run_session(
                "classic", "a provider outage", emit=events.append, save=False
            )
        self.assertEqual(len(result.turns), 3)
        for turn in result.turns:
            self.assertTrue(turn.content.strip())
            self.assertNotIn("HTTP", turn.content)
            self.assertNotIn("429", turn.content)
            self.assertNotIn("[no response]", turn.content)
        self.assertFalse(any(event["type"] == "error" for event in events))

    def test_session_end_carries_the_answering_key_and_trail(self):
        class TrailClient:
            provider = "groq"
            key_label = "key 2"
            model = "fallback-model"
            fallback_used = True
            attempts = ["openrouter key 1: HTTP 429 (cooldown 30s)"]

            def complete(self, *, messages, model=None, system=None, sampling=None, on_chunk=None):
                if on_chunk:
                    on_chunk("ok")
                return "ok"

        events = []
        runtime = HotseatRuntime(
            self.config,
            store=self.store,
            client_factory=lambda provider, model: TrailClient(),
        )
        result = runtime.run_session("classic", "a trail", emit=events.append, save=False)
        self.assertEqual(result.provider, "groq")
        self.assertEqual(result.key, "key 2")
        self.assertEqual(result.model, "fallback-model")
        self.assertIn("openrouter key 1", result.fallback_trail[0])
        end = next(event for event in events if event["type"] == "session_end")
        self.assertEqual(end["key"], "key 2")
        self.assertEqual(end["fallback_trail"], result.fallback_trail)


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
