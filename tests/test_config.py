import json
import tempfile
import unittest
from pathlib import Path

from hotseat_core.config import DEFAULT_DATA_DIR, load_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_without_manifest(self):
        config = load_config(root=self.root)
        self.assertIsNone(config.manifest_path)
        self.assertEqual(config.provider, "auto")
        self.assertEqual(config.data_dir, DEFAULT_DATA_DIR)
        self.assertEqual(config.db_path, DEFAULT_DATA_DIR / "memory.db")
        self.assertEqual(config.bridge_host, "127.0.0.1")
        self.assertEqual(config.bridge_port, 8765)

    def test_manifest_core_section_and_relative_paths(self):
        (self.root / "manifest.json").write_text(
            json.dumps(
                {
                    "meta": {"name": "test"},
                    "hotseat_core": {
                        "provider": "ollama",
                        "model": "tinyllama:latest",
                        "styles": "nosyco, terse",
                        "data_dir": "state",
                        "personas": {"classic": {"audrey": {"model": "m"}}},
                        "bridge": {"host": "0.0.0.0", "port": 9999},
                    },
                }
            ),
            encoding="utf-8",
        )
        config = load_config(root=self.root, env={})
        self.assertEqual(config.provider, "ollama")
        self.assertEqual(config.model, "tinyllama:latest")
        self.assertEqual(config.styles, ("nosyco", "terse"))
        self.assertEqual(config.data_dir, self.root / "state")
        self.assertEqual(config.db_path, self.root / "state" / "memory.db")
        self.assertEqual(config.session_log, self.root / "state" / "sessions.log")
        self.assertEqual(config.bridge_host, "0.0.0.0")
        self.assertEqual(config.bridge_port, 9999)
        self.assertEqual(config.persona_overrides("classic")["audrey"]["model"], "m")
        self.assertEqual(config.persona_overrides("v3"), {})

    def test_environment_overrides_manifest(self):
        (self.root / "manifest.json").write_text(
            json.dumps({"hotseat_core": {"provider": "ollama", "data_dir": "state"}}),
            encoding="utf-8",
        )
        config = load_config(
            root=self.root,
            env={"HOTSEAT_PROVIDER": "demo", "HOTSEAT_STYLES": "terse", "HOTSEAT_BRIDGE_PORT": "7000"},
        )
        self.assertEqual(config.provider, "demo")
        self.assertEqual(config.styles, ("terse",))
        self.assertEqual(config.bridge_port, 7000)

    def test_persona_override_layouts(self):
        (self.root / "manifest.json").write_text(
            json.dumps(
                {
                    "hotseat_core": {
                        "personas": {
                            "v3:tribunal": {"fixer": {"model": "small"}},
                            "classic": {"audrey": {"model": "classic-model"}},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        config = load_config(root=self.root, env={})
        self.assertEqual(config.persona_overrides("v3", "tribunal")["fixer"]["model"], "small")
        self.assertEqual(config.persona_overrides("classic")["audrey"]["model"], "classic-model")

    def test_invalid_manifest_raises(self):
        (self.root / "manifest.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_config(root=self.root, env={})

    def test_invalid_port_raises(self):
        (self.root / "manifest.json").write_text(
            json.dumps({"hotseat_core": {"bridge": {"port": "nope"}}}), encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            load_config(root=self.root, env={})


if __name__ == "__main__":
    unittest.main()
