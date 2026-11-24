import unittest

from hotseat_core.personas import MODES, get_persona_set, list_modes


class PersonaTests(unittest.TestCase):
    def test_known_cast_keys(self):
        self.assertEqual(
            [p.key for p in get_persona_set("classic").personas],
            ["audrey", "claib", "vertical"],
        )
        self.assertEqual(
            [p.key for p in get_persona_set("v2").personas],
            ["skeptic1", "skeptic2", "skeptic3", "volunteer"],
        )
        self.assertEqual(
            [p.key for p in get_persona_set("v3").personas],
            ["marlowe", "priya", "zero"],
        )
        self.assertEqual(
            [p.key for p in get_persona_set("v3", "tribunal").personas],
            ["adversary", "reason", "whistleblower", "evangelist", "fixer"],
        )
        self.assertEqual(
            [p.key for p in get_persona_set("bmad").personas],
            ["analyst", "pm", "architect", "builder", "qa"],
        )

    def test_default_variant_and_closer(self):
        panel = get_persona_set("v3")
        self.assertEqual(panel.variant, "panel")
        self.assertIsNone(panel.closer)
        tribunal = get_persona_set("v3", "tribunal")
        self.assertEqual(tribunal.closer, "fixer")

    def test_overrides_change_fields(self):
        persona_set = get_persona_set(
            "classic", overrides={"zero": {"model": "ignored"}, "audrey": {"model": "custom", "temperature": 0.1}}
        )
        audrey = persona_set.by_key("audrey")
        self.assertEqual(audrey.model, "custom")
        self.assertEqual(audrey.temperature, 0.1)
        # Overrides for a persona outside the set are simply unused.
        with self.assertRaises(KeyError):
            persona_set.by_key("zero")

    def test_invalid_override_rejected(self):
        with self.assertRaises(ValueError):
            get_persona_set("classic", overrides={"audrey": {"max_tokens": "lots"}})
        with self.assertRaises(ValueError):
            get_persona_set("classic", overrides={"audrey": {"max_tokens": 0}})

    def test_unknown_mode_and_variant(self):
        with self.assertRaises(ValueError):
            get_persona_set("v9")
        with self.assertRaises(ValueError):
            get_persona_set("v3", "nope")

    def test_modes_are_listed_with_variants(self):
        modes = {entry["mode"]: entry for entry in list_modes()}
        self.assertEqual(set(modes), set(MODES))
        self.assertEqual(modes["v3"]["variants"], ["panel", "tribunal"])
        self.assertEqual(modes["bmad"]["variants"], ["brief"])

    def test_public_payload_hides_system_by_default(self):
        public = get_persona_set("classic").by_key("audrey").public()
        self.assertNotIn("system", public)
        self.assertIn("system", get_persona_set("classic").by_key("audrey").public(include_system=True))


if __name__ == "__main__":
    unittest.main()
