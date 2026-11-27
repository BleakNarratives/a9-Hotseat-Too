import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hotseat_core.providers import ProviderClient
from hotseat_core.vault_loader import get_secret


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault.json"
        self.env_file = self.root / ".env"

    def tearDown(self):
        self.tmp.cleanup()

    def write_vault(self, payload):
        self.vault.write_text(json.dumps(payload), encoding="utf-8")

    def secret(self, name):
        return get_secret(
            name,
            environ={},
            env_file=self.root / "missing.env",
            vault_path=self.vault,
        )

    def test_nested_keys_and_provider_sections(self):
        self.write_vault(
            {
                "version": 3,
                "keys": {"OPENROUTER_KEY": "or-key"},
                "mistral": {"api_key": "mistral-key"},
                "providers": {"anthropic": {"token": "anthropic-key"}},
                "secrets": [{"name": "CEREBRAS_API_KEY", "value": "cerebras-key"}],
                "groq": "groq-key",
            }
        )
        self.assertEqual(self.secret("OPENROUTER_API_KEY"), "or-key")
        self.assertEqual(self.secret("MISTRAL_API_KEY"), "mistral-key")
        self.assertEqual(self.secret("ANTHROPIC_API_KEY"), "anthropic-key")
        self.assertEqual(self.secret("CEREBRAS_API_KEY"), "cerebras-key")
        self.assertEqual(self.secret("GROQ_API_KEY"), "groq-key")

    def test_case_insensitive_keys_and_alias(self):
        self.write_vault({"Keys": {"OpenRouter_Key": "mixed-case"}})
        self.assertEqual(self.secret("OPENROUTER_API_KEY"), "mixed-case")

    def test_dotenv_fallback_and_environment_precedence(self):
        self.write_vault({"keys": {"MISTRAL_API_KEY": "vault-key"}})
        self.env_file.write_text(
            "export MISTRAL_API_KEY=dotenv-key\nGROQ_KEY='groq-dotenv'\n", encoding="utf-8"
        )
        self.assertEqual(
            get_secret(
                "MISTRAL_API_KEY", environ={}, env_file=self.env_file, vault_path=self.vault
            ),
            "dotenv-key",
        )
        self.assertEqual(
            get_secret(
                "GROQ_API_KEY", environ={}, env_file=self.env_file, vault_path=self.vault
            ),
            "groq-dotenv",
        )
        self.assertEqual(
            get_secret(
                "MISTRAL_API_KEY",
                environ={"MISTRAL_API_KEY": "env-key"},
                env_file=self.env_file,
                vault_path=self.vault,
            ),
            "env-key",
        )

    def test_missing_everywhere_returns_default(self):
        self.write_vault({})
        self.assertEqual(self.secret("OPENROUTER_API_KEY"), "")
        self.assertEqual(
            get_secret(
                "OPENROUTER_API_KEY",
                "fallback",
                vault_path=self.vault,
                env_file=self.root / "missing.env",
                environ={},
            ),
            "fallback",
        )

    def test_provider_client_resolves_vault_without_exports(self):
        self.write_vault({"mistral": {"api_key": "mistral-secret"}})
        with mock.patch.dict("os.environ", {}, clear=True):
            client = ProviderClient(
                "mistral",
                secret_loader=lambda key, default: get_secret(
                    key,
                    default,
                    environ={},
                    env_file=self.root / "missing.env",
                    vault_path=self.vault,
                ),
            )
        self.assertEqual(client.api_key, "mistral-secret")


if __name__ == "__main__":
    unittest.main()
